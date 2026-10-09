"""Glob patterns over posix paths: `*` = one segment, `**` = any depth."""

from __future__ import annotations

import re
from functools import lru_cache


@lru_cache(maxsize=512)
def compile_glob(pattern: str) -> re.Pattern:
    pat = pattern.strip().replace("\\", "/")
    anchored = pat.startswith("/")
    pat = pat.lstrip("/")
    if pat.endswith("/"):
        pat += "**"
    out = []
    i = 0
    while i < len(pat):
        c = pat[i]
        if pat.startswith("**/", i):
            out.append("(?:.*/)?")
            i += 3
        elif pat.startswith("**", i):
            out.append(".*")
            i += 2
        elif c == "*":
            out.append("[^/]*")
            i += 1
        elif c == "?":
            out.append("[^/]")
            i += 1
        else:
            out.append(re.escape(c))
            i += 1
    body = "".join(out)
    # A pattern without a slash matches the name at any depth (gitignore style).
    if not anchored and "/" not in pattern.strip().strip("/"):
        body = "(?:.*/)?" + body
    return re.compile("^" + body + "(?:/.*)?$", re.IGNORECASE)


def match_any(path: str, patterns: list[str]) -> bool:
    return any(compile_glob(p).match(path) for p in patterns)
