"""Which doc lines does a code change break? (`mindmap impact`)

For each changed code file: the names it no longer defines (functions,
classes, constants, `--flags`) that no other code file still has, and for a
deleted or renamed file, its path. Then every doc line that still mentions
one of them. Fast enough for a hook: one `git diff`/`git show` per file and
two `git grep` runs over the docs, no full scan.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

from .codeindex import BAT_LABEL, GENERIC_DEF, JS_DEF, PS_FUNC, PY_ASSIGN, PY_DEF
from .doctype import classify
from .files import kind_of, run_git
from .mdscan import code_spans

FLAG_LIT = re.compile(r"""["'](--[A-Za-z][A-Za-z0-9_-]{2,})["'=]""")
DOC_SPECS = ["*.md", "*.markdown", "*.mdx"]
COMMON_BASENAMES = {"readme.md", "index.js", "index.ts", "main.py", "__init__.py", "__main__.py",
                    "app.py", "cli.py", "config.py", "utils.py", "setup.py", "run.bat", "run.sh"}


@dataclass
class Hit:
    doc: str            # scan-root relative
    line: int
    term: str
    kind: str           # symbol | flag | file-deleted | file-renamed
    code_file: str
    note: str = ""
    plan: bool = False
    text: str = ""


def _identifier_like(name: str) -> bool:
    core = name.strip("_")
    return ("_" in core or bool(re.search(r"[a-z][A-Z]|[A-Z]{2,}[a-z]", name))     # snake, camelCase, CORSMiddleware
            or (name.isupper() and len(name) > 3))


def defs_of(text: str, rel: str) -> dict:
    """name -> kind for what a code file defines (and the --flags it parses)."""
    out: dict[str, str] = {}
    low = rel.lower()
    if low.endswith((".py", ".pyi", ".pyw")):
        for m in PY_DEF.finditer(text):
            out[m.group(1) or m.group(2)] = "symbol"
        for m in PY_ASSIGN.finditer(text):
            name = m.group(1)
            if name.isupper() or "_" in name.strip("_"):
                out.setdefault(name, "symbol")
    elif low.endswith((".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte")):
        for m in JS_DEF.finditer(text):
            name = next((g for g in m.groups() if g), None)
            if name:
                out[name] = "symbol"
    elif low.endswith((".ps1", ".psm1")):
        for m in PS_FUNC.finditer(text):
            out[m.group(1)] = "symbol"
    elif low.endswith((".bat", ".cmd")):
        for m in BAT_LABEL.finditer(text):
            out[m.group(1)] = "symbol"
    elif kind_of(rel) == "code":
        for m in GENERIC_DEF.finditer(text):
            out[m.group(1)] = "symbol"
    for m in FLAG_LIT.finditer(text):
        out.setdefault(m.group(1), "flag")
    return {k: v for k, v in out.items() if len(k) >= 3}


def _top(path: Path) -> Path | None:
    out = run_git(["rev-parse", "--show-toplevel"], path if path.is_dir() else path.parent, timeout=20)
    return Path(out.decode("utf-8", "replace").strip()) if out else None


def _rel(p: Path, base: Path) -> str | None:
    try:
        return Path(os.path.relpath(p, base)).as_posix()
    except ValueError:
        return None


def changed_files(top: Path, since: str) -> list:
    """[(status, old_rel, new_rel)] of code files changed in the working tree vs `since`."""
    out = run_git(["diff", "-M", "--name-status", "-z", since, "--"], top, timeout=60)
    items = (out or b"").split(b"\0")
    res = []
    i = 0
    while i < len(items):
        st = items[i].decode("ascii", "replace")
        if not st:
            i += 1
            continue
        if st[0] in "RC" and i + 2 < len(items):
            old, new = items[i + 1].decode("utf-8", "replace"), items[i + 2].decode("utf-8", "replace")
            res.append(("R" if st[0] == "R" else "A", old, new))
            i += 3
        elif i + 1 < len(items):
            p = items[i + 1].decode("utf-8", "replace")
            res.append((st[0], p, p))
            i += 2
        else:
            break
    return [r for r in res if kind_of(r[1]) == "code" or kind_of(r[2]) == "code"]


def _still_in_code(top: Path, names: list) -> set:
    """Names some code file in the working tree still contains."""
    found: set = set()
    names = sorted(set(names))
    for i in range(0, len(names), 60):
        chunk = names[i:i + 60]
        args = ["grep", "-I", "-o", "-h", "-w", "-F", "--untracked"]
        for n in chunk:
            args += ["-e", n]
        args += ["--", ".", *[f":(exclude){s}" for s in DOC_SPECS]]
        out = run_git(args, top, timeout=60, ok_codes=(0, 1))
        for raw in (out or b"").decode("utf-8", "replace").split("\n"):
            raw = raw.strip()
            if raw:
                found.add(raw)
    return found


def _grep_docs(top: Path, terms: list, words: bool) -> list:
    """[(top-relative doc, line, text, term)]"""
    hits = []
    terms = sorted(set(t for t in terms if t))
    for i in range(0, len(terms), 60):
        chunk = terms[i:i + 60]
        args = ["grep", "-n", "-I", "-F", "--untracked", "--no-color"] + (["-w"] if words else [])
        for t in chunk:
            args += ["-e", t]
        args += ["--", *DOC_SPECS]
        out = run_git(args, top, timeout=60, ok_codes=(0, 1))
        for raw in (out or b"").decode("utf-8", "replace").split("\n"):
            m = re.match(r"(.*?):(\d+):(.*)$", raw)
            if not m:
                continue
            text = m.group(3)
            for t in chunk:
                if t in text:
                    hits.append((m.group(1), int(m.group(2)), text, t))
    return hits


def _mentions_name(text: str, name: str) -> bool:
    pat = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
    for _, content in code_spans(text):
        if pat.search(content):
            return True
    return _identifier_like(name) and bool(pat.search(text))


def impact(root, files: list | None = None, since: str = "HEAD") -> list:
    """Doc lines that mention what the given (or all changed) code files lost."""
    from .checks import GONE_WORDS
    root = Path(root).resolve()
    by_top: dict[Path, list] = {}
    if files:
        for f in files:
            p = (root / f).resolve() if not Path(f).is_absolute() else Path(f).resolve()
            top = _top(p)
            if top is None:
                continue
            rel = _rel(p, top)
            if rel is None or rel.startswith(".."):
                continue
            exists = p.exists()
            status = "M" if exists else "D"
            by_top.setdefault(top, []).append((status, rel, rel))
    else:
        top = _top(root)
        if top is not None:
            by_top[top] = changed_files(top, since)

    hits: list[Hit] = []
    for top, changes in by_top.items():
        lost: dict[str, tuple] = {}         # term -> (kind, code_file, note)
        paths: dict[str, tuple] = {}
        for status, old_rel, new_rel in changes:
            if kind_of(old_rel) != "code":
                continue
            old = run_git(["show", f"{since}:{old_rel}"], top, timeout=30)
            old_text = old.decode("utf-8", "replace") if old else ""
            if status == "D":
                new_text = ""
            else:
                try:
                    new_text = (top / new_rel).read_text(encoding="utf-8", errors="replace")
                except OSError:
                    new_text = ""
            if not old_text:
                continue
            gone = {n: k for n, k in defs_of(old_text, old_rel).items() if n not in defs_of(new_text, new_rel)}
            for n, k in gone.items():
                lost[n] = (k, new_rel if status != "D" else old_rel, "")
            if status in ("D", "R"):
                note = new_rel if status == "R" else ""
                kind = "file-renamed" if status == "R" else "file-deleted"
                paths[old_rel] = (kind, old_rel, note)
                base = old_rel.rsplit("/", 1)[-1]
                if base.lower() not in COMMON_BASENAMES:
                    paths.setdefault(base, (kind, old_rel, note))
        if lost:
            alive = _still_in_code(top, list(lost))
            lost = {n: v for n, v in lost.items() if n not in alive}
        found = []
        if lost:
            found += [(d, ln, text, t, True) for d, ln, text, t in _grep_docs(top, list(lost), words=True)]
        if paths:
            found += [(d, ln, text, t, False) for d, ln, text, t in _grep_docs(top, list(paths), words=False)]
        seen = set()
        for d, ln, text, term, is_name in found:
            doc = _rel(top / d, root)
            if doc is None or doc.startswith(".."):
                continue
            kind_doc = classify(doc)
            if kind_doc == "history" or GONE_WORDS.search(text):
                continue
            if is_name and not _mentions_name(text, term):
                continue
            key = (doc, ln, term)
            if key in seen:
                continue
            seen.add(key)
            kind, code_file, note = lost[term] if is_name else paths[term]
            code_rel = _rel(top / code_file, root) or code_file
            hits.append(Hit(doc, ln, term, kind, code_rel, note, kind_doc == "plan", text.strip()[:200]))
    hits.sort(key=lambda h: (h.plan, h.doc, h.line))
    return hits


def describe(h: Hit, lang: str = "en") -> str:
    if h.kind == "file-deleted":
        return (f"`{h.term}` was deleted" if lang != "vi" else f"`{h.term}` đã bị xóa")
    if h.kind == "file-renamed":
        return (f"`{h.term}` was renamed to `{h.note}`" if lang != "vi" else f"`{h.term}` đã đổi thành `{h.note}`")
    what = "option" if h.kind == "flag" else "name"
    if lang == "vi":
        return f"`{h.term}` vừa bị bỏ khỏi `{h.code_file}` và không còn ở file code nào"
    return f"`{h.term}` ({what}) was removed from `{h.code_file}` and no code has it any more"


def render(hits: list, lang: str = "en") -> str:
    if not hits:
        return ("No doc mentions what these changes removed.\n" if lang != "vi"
                else "Không tài liệu nào nhắc thứ vừa bị bỏ.\n")
    lines = []
    for h in hits:
        tag = " (plan)" if h.plan and lang != "vi" else (" (kế hoạch)" if h.plan else "")
        lines.append(f"{h.doc}:{h.line}{tag}  {describe(h, lang)}")
    return "\n".join(lines) + "\n"


def cli(a) -> int:
    root = Path(a.root).resolve() if a.root else Path.cwd()
    hits = impact(root, a.files or None, a.since)
    from .engine import load_config
    lang = a.lang or load_config(root).get("lang") or "en"
    if a.format == "json":
        print(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=1))
    else:
        text = render(hits, lang)
        try:
            print(text, end="")
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode(), end="")
    return 1 if any(not h.plan for h in hits) else 0
