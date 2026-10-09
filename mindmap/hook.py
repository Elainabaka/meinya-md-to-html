"""Claude Code hook: right after an agent edits a file, tell it which docs went stale.

- PostToolUse on Edit/Write/MultiEdit of a code file: doc lines that still
  mention a name or file the edit just removed (see impact.py).
- PostToolUse on a .md file: the problems in that doc (light check).
- SessionStart: stale lines in the instruction files the agent just loaded
  (CLAUDE.md, AGENTS.md...).

The text goes back to the agent as `additionalContext`. The hook never blocks
an edit and never fails loudly: any problem means exit 0 and no output.

.claude/settings.json (the user installs it; this tool never does). A hook
runs inside whatever project is open, so call the installed `mindmap` command
(or `python -I /path/to/run_mindmap.py hook`), not `python -m mindmap`: with
`-m` the files of that project could shadow Python modules.
{
  "hooks": {
    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit",
                     "hooks": [{"type": "command", "command": "mindmap hook", "timeout": 30}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "mindmap hook", "timeout": 30}]}]
  }
}
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from .files import is_private, kind_of

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
AGENT_FILES = ("CLAUDE.md", "AGENTS.md", "GEMINI.md", ".claude/CLAUDE.md", "CLAUDE.local.md",
               ".github/copilot-instructions.md", ".cursorrules", ".windsurfrules")
MAX_ITEMS = 10


def _lang(root: Path) -> str:
    from .engine import load_config
    try:
        return load_config(root).get("lang") or "en"
    except Exception:
        return "en"


def _rel(path: Path, root: Path) -> str | None:
    try:
        rel = Path(os.path.relpath(path, root)).as_posix()
    except ValueError:
        return None
    return None if rel.startswith("..") else rel


def _finding_lines(findings: list, limit: int = MAX_ITEMS) -> list:
    out = []
    for f in findings[:limit]:
        line = f"- {f.path}:{f.line} {f.message}"
        if f.suggestion:
            line += f" ({f.suggestion})"
        out.append(line)
    if len(findings) > limit:
        out.append(f"- ... {len(findings) - limit} more")
    return out


def post_tool(root: Path, data: dict) -> str:
    if data.get("tool_name") not in EDIT_TOOLS:
        return ""
    ti = data.get("tool_input") or {}
    fp = ti.get("file_path") or ti.get("notebook_path")
    if not fp:
        return ""
    path = Path(fp)
    path = path if path.is_absolute() else root / path
    rel = _rel(path.resolve(), root)
    if rel is None or is_private(rel):
        return ""
    lang = _lang(root)
    kind = kind_of(rel)
    if kind == "doc":
        from .engine import run
        res = run(root, focus=[rel], light=True, lang=lang)
        bad = [f for f in res.findings if f.severity != "info" and f.path == rel]
        if not bad:
            return ""
        head = (f"Mind Map checked {rel}: {len(bad)} line(s) disagree with the code or git history:"
                if lang != "vi" else
                f"Mind Map vừa soát {rel}: {len(bad)} dòng không khớp code hoặc lịch sử git:")
        return "\n".join([head, *_finding_lines(bad)])
    if kind == "code":
        from .impact import describe, impact
        hits = [h for h in impact(root, files=[str(path)]) if not h.plan]
        if not hits:
            return ""
        head = (f"Mind Map: your change to {rel} removed things that docs still mention. "
                f"Update these lines (or say why not):"
                if lang != "vi" else
                f"Mind Map: thay đổi ở {rel} vừa bỏ những thứ tài liệu còn nhắc. Sửa các dòng này (hoặc nói lý do):")
        lines = [f"- {h.doc}:{h.line} {describe(h, lang)}" for h in hits[:MAX_ITEMS]]
        if len(hits) > MAX_ITEMS:
            lines.append(f"- ... {len(hits) - MAX_ITEMS} more")
        return "\n".join([head, *lines])
    return ""


def session_start(root: Path) -> str:
    focus = [p for p in AGENT_FILES if (root / p).is_file()]
    if not focus:
        return ""
    from .engine import run
    lang = _lang(root)
    res = run(root, focus=focus, light=True, lang=lang)
    bad = [f for f in res.findings if f.severity != "info" and f.path in focus]
    if not bad:
        return ""
    head = (f"Mind Map: {len(bad)} line(s) in the instruction files you just read are out of date; "
            f"trust the code over them:"
            if lang != "vi" else
            f"Mind Map: {len(bad)} dòng trong file hướng dẫn vừa nạp đã cũ; tin code hơn các dòng này:")
    return "\n".join([head, *_finding_lines(bad)])


def main(event: str = "auto", root: str | None = None) -> int:
    try:
        raw = sys.stdin.buffer.read()
        data = json.loads(raw.decode("utf-8", "replace") or "{}")
        if not isinstance(data, dict):
            return 0
    except Exception:
        return 0
    try:
        name = data.get("hook_event_name") or ""
        ev = event if event != "auto" else ("session-start" if name == "SessionStart" else "post-tool")
        base = Path(root or data.get("cwd") or os.getcwd()).resolve()
        text = session_start(base) if ev == "session-start" else post_tool(base, data)
        if text:
            out = {"hookSpecificOutput": {
                "hookEventName": "SessionStart" if ev == "session-start" else "PostToolUse",
                "additionalContext": text}}
            sys.stdout.buffer.write(json.dumps(out, ensure_ascii=False).encode("utf-8"))
            sys.stdout.flush()
    except Exception:
        return 0
    return 0
