"""What kind of doc is this? It decides how strict the checks are.

- history: changelogs, decision logs, lessons, archives. They describe the
  past on purpose, so stale references are expected; only decision ids are
  checked.
- plan: plans, proposals, drafts, task tickets. They describe intent at a
  point in time; drift is reported as info only.
- live: everything else (README, AGENTS.md, CLAUDE.md, guides...). Full checks.

Overridable with `history`, `plans` and `live` globs in .mindmap.toml, and in
the doc itself with `<!-- mindmap: history -->` (or `plan`, `live`), which wins
over both: an old prompt or a pasted chat says what kind it is where it is.
"""

from __future__ import annotations

import re

from .globs import match_any

HISTORY_NAME = re.compile(
    r"(?:^|[_\-. ])(?:changelog|changes|history|releases?|release[-_ ]?notes|news|decisions?|"
    r"decision[-_ ]?log|lessons?(?:[-_ ]learned)?|postmortem|post[-_]mortem|retro(?:spective)?|"
    r"journal|diary|devlog|bai[-_ ]?hoc|luu[-_ ]?tru|nhat[-_ ]?ky|handover|ban[-_ ]?giao|"
    r"results?|reports?|ket[-_ ]?qua|bao[-_ ]?cao)(?:[_\-. ]|$)", re.I)
HISTORY_DIR = re.compile(
    r"(?:^|/)(?:archive|archived|_archive|attic|old|legacy|deprecated|history|luu[-_ ]?tru|_cu[^/]*|"
    r"adr|adrs|decisions|decision-records|research|pinned|vendor|third[-_]?party|jobs|runs|"
    r"experiments?|thi[-_]?nghiem|fixtures?|testdata|templates?|scaffold|boilerplate|prompts?|\d{4}-\d{2}-\d{2}[^/]*)/", re.I)
POST_DIR = re.compile(r"(?:^|/)(?:blogs?|news|posts|_posts|articles|announcements?)/", re.I)
PLAN_NAME = re.compile(
    r"(?:^|[_\-. ])(?:plan|plans|proposal|rfc|draft|todo|ideas?|spike|brainstorm|wip|"
    r"ke[-_ ]?hoach|de[-_ ]?xuat|y[-_ ]?tuong|phieu|brief)(?:[_\-. \d]|$)", re.I)
PLAN_PATH = re.compile(r"(?:^|/)(?:tasks?|tickets?|plans?|proposals?|rfcs?|drafts?|ideas?|y[-_]?tuong|backlog)/|(?:^|/)T\d+[a-z]?[-_][^/]*$", re.I)


def is_post(path: str) -> bool:
    """A dated post (a blog entry, an announcement): its links are still checked, its figures are of its day."""
    return POST_DIR.search(path) is not None


def classify(path: str, cfg: dict | None = None, mark: str = "") -> str:
    if mark in ("live", "plan", "history"):
        return mark
    cfg = cfg or {}
    if cfg.get("live") and match_any(path, cfg["live"]):
        return "live"
    if cfg.get("history") and match_any(path, cfg["history"]):
        return "history"
    if cfg.get("plans") and match_any(path, cfg["plans"]):
        return "plan"
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if HISTORY_DIR.search(path) or HISTORY_NAME.search(stem):
        return "history"
    if PLAN_NAME.search(stem) or PLAN_PATH.search(path):
        return "plan"
    return "live"
