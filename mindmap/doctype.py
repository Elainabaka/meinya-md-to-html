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
    r"experiments?|thi[-_]?nghiem|fixtures?|testdata|templates?|scaffold|boilerplate|prompts?|\d{4}-\d{2}-\d{2}[^/]*|"
    r"done|completed|complete|implemented|shipped|superseded|obsolete|finished|"
    r"\.changesets?|\.changes|changelog\.d|newsfragments|release[-_]?notes|releasenotes|"    # one entry per change
    r"(?:tests?|__tests__|testsuite)/[^/]+/[^/]+|versioned_docs[^/]*)/", re.I)     # deep in a test folder: a test's input; Docusaurus snapshots
VERSION_DIR = re.compile(r"^(?:v(\d+(?:\.\d+)*)|version[-_]?(\d+(?:\.\d+)*)(?:\.x)?|(\d+\.(?:\d+|x)(?:\.\d+)*))$", re.I)
POST_DIR = re.compile(r"(?:^|/)(?:blogs?|news|posts|_posts|articles|announcements?)/", re.I)
PLAN_NAME = re.compile(
    r"(?:^|[_\-. ])(?:plan|plans|proposal|rfc|draft|todo|ideas?|spike|brainstorm|wip|"
    r"ke[-_ ]?hoach|de[-_ ]?xuat|y[-_ ]?tuong|phieu|brief)(?:[_\-. \d]|$)", re.I)
PLAN_PATH = re.compile(r"(?:^|/)(?:tasks?|tickets?|plans?|proposals?|rfcs?|drafts?|ideas?|y[-_]?tuong|backlog|todos?|wip|in[-_]?progress|planned|upcoming)/|(?:^|/)T\d+[a-z]?[-_][^/]*$", re.I)
DATED_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}")
STATUS_LINE = re.compile(
    r"^\s{0,3}(?:\*\*|__)?status(?:\*\*|__)?\s*[:—–-]\s*(?:\*\*|__)?\s*[\"']?"
    r"(done|implemented|completed|shipped|superseded|obsolete|deprecated|archived|rejected|withdrawn|accepted|"
    r"draft|proposed|planned|in\s+progress|wip|approved)\b", re.I)
PLAN_STATUS = {"draft", "proposed", "planned", "in progress", "wip", "approved"}
# `**Date**: 2026-07-11` under the title: a dated record (an experiment, a meeting, a postmortem). Not the `date:`
# of a site page's front matter, which every page of a Hugo or Jekyll site has
DATE_LINE = re.compile(r"^\s{0,3}(?:\*\*|__)?date(?:\*\*|__)?\s*[:—–-]\s*(?:\*\*|__)?\s*\d{4}-\d{2}-\d{2}\b", re.I)


def is_post(path: str) -> bool:
    """A dated post (a blog entry, an announcement): its links are still checked, its figures are of its day."""
    return POST_DIR.search(path) is not None


def _version(seg: str) -> tuple | None:
    m = VERSION_DIR.match(seg)
    if not m:
        return None
    return tuple(int(x) if x.isdigit() else 0 for x in (m.group(1) or m.group(2) or m.group(3)).split("."))


def old_versions(paths) -> set:
    """Docs under the folder of an older version (`docs/v1/`, `docs/v2/` next to `docs/v3/`): the guide
    of a release that still works as it did, not of the code in the tree."""
    seen: dict = {}
    for p in paths:
        segs = p.split("/")[:-1]
        for i, seg in enumerate(segs):
            v = _version(seg)
            if v is not None:
                seen.setdefault("/".join(segs[:i]), {})[seg] = v
    old = {(parent, seg) for parent, vs in seen.items() if len(vs) >= 2
           for seg, v in vs.items() if v < max(vs.values())}
    out = set()
    for p in paths:
        segs = p.split("/")[:-1]
        if any(("/".join(segs[:i]), seg) in old for i, seg in enumerate(segs)):
            out.add(p)
    return out


def _status_kind(lines: list[str]) -> str:
    limit = 20
    end = 0
    if lines and lines[0].lstrip("\ufeff").strip() == "---":
        end = next((index for index, line in enumerate(lines[1:], 1) if line.strip() in ("---", "...")), 0)
        limit = max(limit, end + 1)
    fence = ""
    comment = False
    dated = False
    for number, line in enumerate(lines[:limit]):
        if comment or "<!--" in line:
            comment = "-->" not in line
            continue
        marker = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if marker:
            if not fence:
                fence = marker.group(1)
            elif marker.group(1)[0] == fence[0] and len(marker.group(1)) >= len(fence):
                fence = ""
            continue
        if fence:
            continue
        match = STATUS_LINE.match(line)
        if match:
            status = " ".join(match.group(1).lower().split())
            return "plan" if status in PLAN_STATUS else "history"
        dated = dated or ((not end or number > end) and number < 10 + end and DATE_LINE.match(line) is not None)
    return "history" if dated else ""


def classify(path: str, cfg: dict | None = None, mark: str = "", old_version: bool = False,
             lines: list[str] | None = None) -> str:
    if mark in ("live", "plan", "history"):
        return mark
    cfg = cfg or {}
    if cfg.get("live") and match_any(path, cfg["live"]):
        return "live"
    if cfg.get("history") and match_any(path, cfg["history"]):
        return "history"
    if cfg.get("plans") and match_any(path, cfg["plans"]):
        return "plan"
    status = _status_kind(lines or [])
    if status:
        return status
    if old_version:
        return "history"
    name = path.rsplit("/", 1)[-1]
    stem = name.rsplit(".", 1)[0]
    if HISTORY_DIR.search(path):
        return "history"
    if DATED_NAME.match(name) and not is_post(path):
        return "plan"
    if HISTORY_NAME.search(stem):
        return "history"
    if PLAN_NAME.search(stem) or PLAN_PATH.search(path):
        return "plan"
    return "live"
