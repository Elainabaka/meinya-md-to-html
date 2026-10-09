"""Run the whole pipeline: inventory -> docs -> code index -> claims -> checks."""

from __future__ import annotations

import json
import posixpath
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from pathlib import Path

from .checks import Checker
from .claims import Extractor
from .codeindex import CodeIndex
from .decisions import ADR_FILE, LOG_NAME, Decisions
from .doctype import classify, old_versions
from .files import Inventory, git_trouble
from .gitinfo import Git
from .mdscan import scan
from .model import ERROR, INFO, SEVERITY_RANK, WARNING

CONFIG_NAMES = (".mindmap.toml", "mindmap.toml")


@dataclass
class Result:
    root: str
    findings: list
    claims: list
    docs: dict
    doc_stats: dict
    stats: dict
    timings: dict = field(default_factory=dict)
    suppressed: int = 0
    lang: str = "en"        # the language the messages were written in (flag, else config, else English)


def load_config(root: Path) -> dict:
    """Settings from .mindmap.toml (top level) or pyproject.toml [tool.mindmap]."""
    try:
        import tomllib
    except ImportError:
        return {}
    for name in CONFIG_NAMES:
        p = root / name
        if p.is_file():
            try:
                data = tomllib.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
            return data.get("mindmap", data)
    p = root / "pyproject.toml"
    if p.is_file():
        try:
            data = tomllib.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return (data.get("tool") or {}).get("mindmap") or {}
    return {}


def load_baseline(path: Path) -> set:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    return set(data.get("fingerprints", []))


def save_baseline(path: Path, findings: list) -> None:
    data = {"version": 1, "fingerprints": sorted({f.fingerprint for f in findings})}
    path.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")


def in_scope(path: str, focus: list | None) -> bool:
    if not focus:
        return True
    return any(path == f or path.startswith(f.rstrip("/") + "/") for f in focus)


def run(root, *, lang: str | None = None, use_git: bool = True, nested: bool | None = None,
        exclude: list | None = None, focus: list | None = None, baseline: Path | None = None,
        light: bool = False) -> Result:
    """light=True (with focus): read only the focused docs and the decision
    logs, skip the cross-doc checks. Used by the hook and MCP for one doc."""
    timings = {}
    t0 = time.perf_counter()
    git_trouble(reset=True)
    root = Path(root).resolve()
    cfg = load_config(root)
    lang = lang or cfg.get("lang") or "en"
    nested = cfg.get("nested", True) if nested is None else nested
    excl = list(exclude or []) + list(cfg.get("exclude") or [])
    inv = Inventory(root, use_git=use_git, nested=nested, exclude=excl)
    timings["inventory"] = time.perf_counter() - t0

    t = time.perf_counter()
    light = light and bool(focus)
    wanted = [p for p in inv.docs if not light or in_scope(p, focus)
              or LOG_NAME.match(posixpath.basename(p)) or ADR_FILE.search(p)]
    if len(wanted) > 16:
        with ThreadPoolExecutor(max_workers=8) as pool:     # the first read of many files: see CodeIndex._read_all
            list(pool.map(inv.text, wanted))
    docs = {p: scan(p, inv.text(p) or "") for p in wanted}
    timings["docs"] = time.perf_counter() - t

    t = time.perf_counter()
    index = CodeIndex.cached(inv)
    timings["index"] = time.perf_counter() - t

    gits = {}
    if use_git:
        for prefix, top in inv.repos.items():
            gits[prefix] = Git(top, root)
    dec = Decisions()
    dec.load(docs)

    older = old_versions(inv.docs)
    kinds = {p: classify(p, cfg, d.kind_mark, p in older) for p, d in docs.items()}
    t = time.perf_counter()
    ext = Extractor(dec.regex, dec.logs, root_abs=str(root))
    claims = []
    for p, d in docs.items():
        if not in_scope(p, focus):
            continue
        found = ext.extract(d)
        if kinds[p] == "history":
            found = [c for c in found if c.kind == "decision"]
        claims.extend(found)
    timings["claims"] = time.perf_counter() - t

    t = time.perf_counter()
    checker = Checker(inv, index, gits, dec, docs, lang, kinds, light=light,
                      load_doc=lambda p: scan(p, inv.text(p) or "") if p in inv.docs else None)
    findings = checker.run(claims)
    fresh = checker.freshness(claims)
    timings["checks"] = time.perf_counter() - t
    if focus:
        findings = [f for f in findings if in_scope(f.path, focus)
                    or any(in_scope(e.get("path", ""), focus) for e in f.evidence if e.get("kind") == "doc")]

    suppressed = 0
    if baseline is not None and baseline.is_file():
        known = load_baseline(baseline)
        kept = [f for f in findings if f.fingerprint not in known]
        suppressed = len(findings) - len(kept)
        findings = kept

    findings.sort(key=lambda f: (-SEVERITY_RANK[f.severity], f.path, f.line, f.col))
    doc_stats = {}
    for p, d in docs.items():
        if not in_scope(p, focus):
            continue
        doc_stats[p] = {"claims": 0, "ok": 0, "broken": 0, "error": 0, "warning": 0, "info": 0,
                        "newer": [], "type": kinds[p],
                        "title": d.headings[0].text if d.headings else posixpath.basename(p)}
    for c in claims:
        s = doc_stats.get(c.doc)
        if s is None:
            continue
        s["claims"] += 1
        if c.status == "ok":
            s["ok"] += 1
        elif c.status == "broken":
            s["broken"] += 1
    for f in findings:
        s = doc_stats.get(f.path)
        if s is not None:
            s[f.severity] += 1
    for p, info in fresh.items():
        if p in doc_stats:
            doc_stats[p]["newer"] = [f for f, _ in info["newer"][:5]]
    for s in doc_stats.values():
        s["color"] = ("red" if s["error"] else "yellow" if (s["warning"] or s["newer"])
                      else "green" if s["claims"] else "gray")

    checked = [c for c in claims if c.status in ("ok", "broken")]
    stats = {
        "docs": len(doc_stats), "code_files": len(index.files), "claims": len(claims),
        "checked": len(checked), "verified": sum(1 for c in claims if c.status == "ok"),
        ERROR: sum(1 for f in findings if f.severity == ERROR),
        WARNING: sum(1 for f in findings if f.severity == WARNING),
        INFO: sum(1 for f in findings if f.severity == INFO),
        "repos": len(inv.repos), "git": bool(gits), "decisions": len(dec.items),
        "git_unanswered": sum(git_trouble().values()),      # not 0: git ran out of time, findings are missing
    }
    timings["total"] = time.perf_counter() - t0
    return Result(str(root), findings, claims, docs, doc_stats, stats, timings, suppressed, lang)
