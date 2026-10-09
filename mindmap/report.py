"""Output formats: text, json, github, sarif, md, html."""

from __future__ import annotations

import json
import os
import sys

from . import __version__
from .model import ERROR, INFO, SEVERITY_RANK, WARNING

LABEL = {
    "en": {ERROR: "error", WARNING: "warning", INFO: "info"},
    "vi": {ERROR: "lỗi", WARNING: "cảnh báo", INFO: "ghi nhận"},
}


def filter_findings(findings: list, min_sev: str) -> list:
    floor = SEVERITY_RANK[min_sev]
    return [f for f in findings if SEVERITY_RANK[f.severity] >= floor]


def _color(enabled: bool):
    codes = {ERROR: "\033[31m", WARNING: "\033[33m", INFO: "\033[36m", "dim": "\033[2m", "end": "\033[0m"}
    return (lambda k: codes[k]) if enabled else (lambda k: "")


def evidence_text(e: dict) -> str:
    bits = []
    if e.get("rev"):
        bits.append(e["rev"] + (f" {e['date']}" if e.get("date") else ""))
    if e.get("path"):
        bits.append(e["path"] + (f":{e['line']}" if e.get("line") else ""))
    if e.get("note"):
        bits.append(e["note"])
    if e.get("text"):
        bits.append(f"\"{e['text']}\"")
    return " · ".join(bits)


def incomplete(result, lang: str = "en") -> str:
    """One line when git left questions unanswered: such a report is missing findings and has to say so."""
    n = result.stats.get("git_unanswered", 0)
    if not n:
        return ""
    if lang == "vi":
        return f"git không trả lời kịp {n} câu hỏi: báo cáo này có thể thiếu phát hiện, hãy chạy lại"
    return (f"git gave no answer in time to {n} question" + ("" if n == 1 else "s")
            + ": findings may be missing from this report, run it again")


def text(result, findings: list, lang: str = "en", color: bool | None = None, stream=None) -> str:
    if color is None:
        stream = stream or sys.stdout
        color = hasattr(stream, "isatty") and stream.isatty() and os.environ.get("NO_COLOR") is None
    c = _color(color)
    lab = LABEL.get(lang, LABEL["en"])
    out = []
    by_path: dict[str, list] = {}
    for f in findings:
        by_path.setdefault(f.path, []).append(f)
    # one block per doc, the docs with the worst problem first
    for path in sorted(by_path, key=lambda p: (-max(SEVERITY_RANK[f.severity] for f in by_path[p]), p)):
        out.append("")
        out.append(path)
        for f in sorted(by_path[path], key=lambda f: (f.line, f.col)):
            out.append(f"  {f.line}:{f.col}  {c(f.severity)}{lab[f.severity]}{c('end')}  {f.message}  {c('dim')}[{f.rule}]{c('end')}")
            for e in f.evidence[:3]:
                out.append(f"      {c('dim')}↳ {evidence_text(e)}{c('end')}")
            if f.suggestion:
                out.append(f"      → {f.suggestion}")
    s = result.stats
    if lang == "vi":
        summary = (f"{s['docs']} tài liệu, {s['claims']} điều kiểm được, {s['verified']} khớp · "
                   f"{s[ERROR]} lỗi, {s[WARNING]} cảnh báo, {s[INFO]} ghi nhận · {result.timings.get('total', 0):.1f}s")
    else:
        def n(count: int, word: str) -> str:
            return f"{count} {word}" + ("" if count == 1 else "s")
        summary = (f"{n(s['docs'], 'doc')}, {n(s['claims'], 'claim')}, {s['verified']} verified · "
                   f"{n(s[ERROR], 'error')}, {n(s[WARNING], 'warning')}, {s[INFO]} info · "
                   f"{result.timings.get('total', 0):.1f}s")
    if result.suppressed:
        summary += f" · baseline: {result.suppressed}"
    out.append("")
    note = incomplete(result, lang)
    if note:
        out.append(f"{c(WARNING)}! {note}{c('end')}")
    out.append(summary)
    return "\n".join(out).lstrip("\n") + "\n"


def to_json(result, findings: list) -> str:
    data = {
        "tool": "meinya-mind-map", "version": __version__, "root": result.root,
        "stats": result.stats, "timings": {k: round(v, 3) for k, v in result.timings.items()},
        "findings": [f.to_dict() for f in findings],
        "docs": result.doc_stats,
    }
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"


def github(findings: list) -> str:
    """GitHub Actions workflow commands: annotations on the PR diff."""
    lines = []
    for f in findings:
        level = {"error": "error", "warning": "warning", "info": "notice"}[f.severity]
        msg = f.message + (f" → {f.suggestion}" if f.suggestion else "")
        msg = msg.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
        path = f.path.replace(",", "%2C").replace(":", "%3A")
        lines.append(f"::{level} file={path},line={f.line},col={f.col},title=mindmap {f.rule}::{msg}")
    return "\n".join(lines) + ("\n" if lines else "")


def sarif(result, findings: list) -> str:
    rules = sorted({f.rule for f in findings})
    data = {
        "$schema": "https://json.schemastore.org/sarif-2.1.0.json",
        "version": "2.1.0",
        "runs": [{
            "tool": {"driver": {
                "name": "Meinya Mind Map", "version": __version__,
                "informationUri": "https://github.com/Elainabaka/meinya-mind-map",
                "rules": [{"id": r, "shortDescription": {"text": r.replace("-", " ")}} for r in rules],
            }},
            "results": [{
                "ruleId": f.rule,
                "level": {"error": "error", "warning": "warning", "info": "note"}[f.severity],
                "message": {"text": f.message + (f" → {f.suggestion}" if f.suggestion else "")},
                "locations": [{"physicalLocation": {
                    "artifactLocation": {"uri": f.path},
                    "region": {"startLine": max(1, f.line), "startColumn": max(1, f.col)},
                }}],
                "partialFingerprints": {"mindmap/v1": f.fingerprint},
            } for f in findings],
        }],
    }
    return json.dumps(data, ensure_ascii=False, indent=1) + "\n"
