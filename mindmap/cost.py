"""What the instruction files agents load cost, and how much of them is stale (`mindmap cost`).

Root-level CLAUDE.md / AGENTS.md / GEMINI.md are read at every session start;
the same names in subfolders are read when an agent works there. Tokens are an
estimate (about 4 characters per token for English, fewer for accented text).
"""

from __future__ import annotations

import json
import posixpath
from pathlib import Path

AGENT_NAMES = {"claude.md", "agents.md", "gemini.md", "claude.local.md"}
AGENT_PATHS = {".github/copilot-instructions.md", ".cursorrules", ".windsurfrules"}


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for ch in text if ord(ch) < 128)
    return round(ascii_chars / 4 + (len(text) - ascii_chars) / 1.5)


def agent_files(inv) -> list:
    out = []
    for p in sorted(inv.files):
        low = p.lower()
        name = low.rsplit("/", 1)[-1]
        if name in AGENT_NAMES or low in AGENT_PATHS or (low.startswith(".cursor/rules/") and low.endswith(".mdc")):
            out.append(p)
    return out


def measure(root) -> list:
    from .engine import run
    from .files import Inventory
    root = Path(root).resolve()
    inv = Inventory(root)
    files = agent_files(inv)
    if not files:
        return []
    res = run(root, focus=files, light=True)
    stale: dict = {}
    for f in res.findings:
        if f.severity != "info":
            stale.setdefault(f.path, set()).add(f.line)
    rows = []
    for p in files:
        text = inv.text(p) or ""
        d = posixpath.dirname(p)
        rows.append({"file": p, "tokens": estimate_tokens(text), "lines": text.count("\n") + 1,
                     "loaded": "every session" if not d or d in (".github", ".claude") else f"when working in {d}/",
                     "stale_lines": sorted(stale.get(p, ()))})
    rows.sort(key=lambda r: (r["loaded"] != "every session", -r["tokens"]))
    return rows


def render(rows: list, lang: str = "en") -> str:
    if not rows:
        return "No agent instruction files found.\n" if lang != "vi" else "Không thấy file hướng dẫn cho agent.\n"
    always = sum(r["tokens"] for r in rows if r["loaded"] == "every session")
    lines = [f"{'tokens':>7}  {'stale':>5}  file  (loaded)"]
    for r in rows:
        lines.append(f"{r['tokens']:>7}  {len(r['stale_lines']):>5}  {r['file']}  ({r['loaded']})")
    lines.append(f"~{always} tokens are read at the start of every session; "
                 f"{sum(len(r['stale_lines']) for r in rows)} stale lines in total.")
    return "\n".join(lines) + "\n"


def cli(a) -> int:
    rows = measure(Path(a.path))
    if a.format == "json":
        print(json.dumps(rows, ensure_ascii=False, indent=1))
    else:
        text = render(rows)
        try:
            print(text, end="")
        except UnicodeEncodeError:
            print(text.encode("ascii", "replace").decode(), end="")
    return 0
