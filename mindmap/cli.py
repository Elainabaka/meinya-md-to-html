"""Command line: `python -m mindmap <command>`.

Exit codes: 0 = nothing at or above --fail-on, 1 = findings at or above it,
2 = usage or internal error.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import __version__
from .model import SEVERITY_RANK


def _out(text: str, path: str | None) -> None:
    if path:
        Path(path).write_text(text, encoding="utf-8")
    else:
        try:
            sys.stdout.write(text)
        except UnicodeEncodeError:
            sys.stdout.buffer.write(text.encode("utf-8", "replace"))


def cmd_check(a) -> int:
    from . import engine, report
    root = Path(a.path).resolve()
    focus = None
    if root.is_file():
        focus_file = root
        root = Path(a.root).resolve() if a.root else _repo_root(root.parent)
        focus = [focus_file.relative_to(root).as_posix()]
    elif a.root:
        r = Path(a.root).resolve()
        focus = [root.relative_to(r).as_posix()] if root != r else None
        root = r
    baseline = Path(a.baseline) if a.baseline else None
    if baseline is not None and not baseline.is_absolute():
        baseline = root / baseline
    res = engine.run(root, lang=a.lang, use_git=not a.no_git, nested=not a.no_nested,
                     exclude=a.exclude, focus=focus,
                     baseline=None if a.update_baseline else baseline,
                     sure_only=not (a.all or a.update_baseline))
    lang = res.lang
    if a.update_baseline:
        target = baseline or (root / ".mindmap-baseline.json")
        engine.save_baseline(target, res.findings)
        print(f"baseline: {len(res.findings)} findings -> {target}")
        return 0
    shown = report.filter_findings(res.findings, a.severity)
    fmt = a.format
    if report.incomplete(res, lang) and (fmt != "text" or a.out):       # the text report says it itself
        print("mindmap: " + report.incomplete(res, lang), file=sys.stderr)
    if fmt == "text":
        _out(report.text(res, shown, lang), a.out)
    elif fmt == "json":
        _out(report.to_json(res, shown), a.out)
    elif fmt == "github":
        _out(report.github(shown), a.out)
    elif fmt == "sarif":
        _out(report.sarif(res, shown), a.out)
    elif fmt in ("md", "html"):
        from . import htmlreport
        body = htmlreport.markdown(res, shown, lang) if fmt == "md" else htmlreport.html(res, shown, lang)
        _out(body, a.out)
    if a.fail_on == "never":
        return 0
    floor = SEVERITY_RANK[a.fail_on]
    return 1 if any(SEVERITY_RANK[f.severity] >= floor for f in res.findings) else 0


def _repo_root(start: Path) -> Path:
    from .files import run_git
    out = run_git(["rev-parse", "--show-toplevel"], start, timeout=20)
    return Path(out.decode().strip()) if out else start


def cmd_mcp(a) -> int:
    from . import mcp
    return mcp.serve(Path(a.root or os.getcwd()))


def cmd_hook(a) -> int:
    from . import hook
    return hook.main(a.event, a.root)


def cmd_impact(a) -> int:
    from . import impact
    return impact.cli(a)


def cmd_cost(a) -> int:
    from . import cost
    return cost.cli(a)


def cmd_context(a) -> int:
    from . import context
    return context.cli(a)


def cmd_claims(a) -> int:
    from . import engine
    doc = Path(a.doc).resolve()
    root = Path(a.root).resolve() if a.root else _repo_root(doc.parent)
    rel = doc.relative_to(root).as_posix()
    res = engine.run(root, lang=a.lang, focus=[rel])
    for c in res.claims:
        if c.doc != rel:
            continue
        mark = {"ok": "ok", "broken": "BROKEN", "external": "ext", "skipped": "skip"}.get(c.status, c.status)
        where = f"  -> {c.where}" if c.where else ""
        _out(f"{c.line:>5}  {mark:<8} {c.kind:<10} {c.text[:80]}{where}\n", None)
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="mindmap", description="Meinya Mind Map: check what your docs claim about your code.")
    p.add_argument("--version", action="version", version=f"meinya-mind-map {__version__}")
    sub = p.add_subparsers(dest="command")

    c = sub.add_parser("check", help="check docs against the code (default)")
    c.add_argument("path", nargs="?", default=".", help="repo, folder or one .md file")
    c.add_argument("--root", help="repo root when PATH is inside it")
    c.add_argument("--format", "-f", default="text", choices=["text", "json", "github", "sarif", "md", "html"])
    c.add_argument("--out", "-o", help="write the report to a file")
    c.add_argument("--severity", default="warning", choices=["error", "warning", "info"], help="lowest level to show")
    c.add_argument("--fail-on", default="error", choices=["error", "warning", "info", "never"])
    c.add_argument("--all", action="store_true",
                   help="also report the findings that are a reading of the text (a name or a path that seems "
                        "gone or made up), shown as notes otherwise")
    c.add_argument("--lang", choices=["en", "vi"], help="message language (default: config or en)")
    c.add_argument("--baseline", help="ignore findings recorded in this file")
    c.add_argument("--update-baseline", action="store_true", help="record current findings as the baseline")
    c.add_argument("--exclude", action="append", default=[], help="glob to skip (repeatable)")
    c.add_argument("--no-git", action="store_true", help="do not use git history")
    c.add_argument("--no-nested", action="store_true", help="skip nested git repositories")
    c.set_defaults(func=cmd_check)

    cl = sub.add_parser("claims", help="list every claim found in one doc and its status")
    cl.add_argument("doc")
    cl.add_argument("--root")
    cl.add_argument("--lang", choices=["en", "vi"])
    cl.set_defaults(func=cmd_claims)

    im = sub.add_parser("impact", help="docs affected by your code changes (vs HEAD or --since)")
    im.add_argument("files", nargs="*")
    im.add_argument("--since", default="HEAD")
    im.add_argument("--root")
    im.add_argument("--format", "-f", default="text", choices=["text", "json"])
    im.add_argument("--lang", choices=["en", "vi"])
    im.set_defaults(func=cmd_impact)

    co = sub.add_parser("cost", help="token cost of the instruction files agents load")
    co.add_argument("path", nargs="?", default=".")
    co.add_argument("--format", "-f", default="text", choices=["text", "json"])
    co.set_defaults(func=cmd_cost)

    cx = sub.add_parser("context", help="smallest verified doc context for a task")
    cx.add_argument("query")
    cx.add_argument("--root", default=".")
    cx.add_argument("--budget", type=int, default=2000, help="token budget")
    cx.set_defaults(func=cmd_context)

    m = sub.add_parser("mcp", help="run the MCP server on stdio")
    m.add_argument("--root")
    m.set_defaults(func=cmd_mcp)

    h = sub.add_parser("hook", help="Claude Code hook entry (reads the event JSON on stdin)")
    h.add_argument("--event", default="auto", choices=["auto", "post-tool", "session-start"])
    h.add_argument("--root")
    h.set_defaults(func=cmd_hook)
    return p


def _safe_stdout() -> None:
    """Redirected output on Windows defaults to the ANSI code page: the first `→` or accented path
    would stop the run. Write UTF-8 there, unless the user chose an encoding; never raise on a character."""
    out = sys.stdout
    try:
        chosen = os.environ.get("PYTHONIOENCODING") or (out.encoding or "").lower().replace("-", "") == "utf8"
        out.reconfigure(encoding=None if chosen else "utf-8", errors="replace")
    except Exception:
        pass        # a captured or missing stream: leave it as it is


def main(argv: list | None = None) -> int:
    _safe_stdout()
    parser = build_parser()
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] not in {"check", "claims", "impact", "cost", "context", "mcp", "hook", "-h", "--help", "--version"}:
        argv = ["check", *argv]
    a = parser.parse_args(argv)
    try:
        return a.func(a)
    except KeyboardInterrupt:
        return 2
    except BrokenPipeError:
        return 0
