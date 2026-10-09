"""Decision logs: which decisions exist and which were replaced.

Two formats are understood:
- a table log (DECISIONS.md, DECISION_LOG.md...) whose first column is an id
  like `MD65` or `D-12`; a status column (or a bold marker in the row) says
  "superseded by X", "replaced by X", "bị thay (X)", "bị thay một phần"...
  Every `|` row of the file counts, also rows after a paragraph broke the
  table (they still are decisions, even if they render as plain text).
- an ADR directory (`adr/0007-use-x.md`, `docs/decisions/...`) with a
  `Status:` line or `## Status` section.
A newer row that says "supersedes/replaces/thay MD12" marks MD12 as amended.

A log applies to the folder it lives in (`docs/` and ADR folders count as
their parent), so two tools may both use `D-1` without clashing.
"""

from __future__ import annotations

import posixpath
import re

from .mdscan import Doc, split_cells

LOG_NAME = re.compile(r"^(?:decisions?|decision[-_ ]?log|adr[-_ ]?log|adrs?|quyet[-_ ]?dinh)\.(?:md|markdown)$", re.I)
ADR_FILE = re.compile(r"(?:^|/)(?:adr|adrs|decisions|decision-records|architecture/decisions)/(\d{1,5})[-_][^/]+\.md$", re.I)
ID_CELL = re.compile(r"^\s*\**\s*([A-Z]{1,6})-?(\d{1,5})([a-z]?)\s*\**\s*$")
FULL = re.compile(r"\bsuperseded\b(?![^.;]*\b(?:in part|partly|partially)\b)|\breplaced by\b|\bobsolete\b|\bwithdrawn\b|\brevoked\b|\bbị thay\b(?!\s*(?:một phần|1 phần))|\bđã bỏ\b|\bđã hủy\b", re.I)
PARTIAL = re.compile(r"\bbị thay\s*(?:một phần|1 phần)|\b(?:partially|partly) superseded\b|\bsuperseded in part\b|\bamended by\b|\bsửa một phần\b", re.I)
DEPRECATED = re.compile(r"\bdeprecated\b", re.I)
REPLACES = re.compile(r"\b(?:supersedes|replaces|overrides|thay(?: cho| thế)?|sửa|đè)\s+((?:[A-Z]{1,6}-?\d{1,5}(?:\s*(?:,|và|and|&)\s*)?)+)", re.I)
STATUS_HEAD = re.compile(r"status|trạng thái|state|tình trạng", re.I)
BOLD = re.compile(r"\*\*([^*]{2,80})\*\*")
REF = re.compile(r"\b([A-Z]{1,6})-?(\d{1,5})\b")
WRAPPER_DIRS = {"docs", "doc", "adr", "adrs", "decisions", "decision-records", "architecture"}


def norm(prefix: str, number: str) -> str:
    return prefix.upper() + str(int(number))


def scope_of(log: str) -> str:
    d = posixpath.dirname(log)
    while d and posixpath.basename(d).lower() in WRAPPER_DIRS:
        d = posixpath.dirname(d)
    return d


class Decisions:
    def __init__(self):
        self.items: dict[str, dict] = {}         # norm id -> first item seen (any log)
        self.by_log: dict[str, dict] = {}        # log (or ADR folder) -> {norm id -> item}
        self.prefix_of: dict[str, set] = {}      # log -> id prefixes it uses
        self.logs: set[str] = set()              # every file that is (part of) a log
        self.prefixes: set[str] = set()
        self.width = 1
        self.regex: re.Pattern | None = None
        self.adr = False

    @property
    def log_names(self) -> str:
        return ", ".join(sorted(self.by_log)) or "the decision log"

    def logs_for(self, doc: str) -> list:
        """Logs that apply to `doc`, nearest first."""
        out = []
        for log in self.by_log:
            s = scope_of(log)
            if not s or doc == s or doc.startswith(s + "/"):
                out.append((len(s), log))
        return [log for _, log in sorted(out, reverse=True)]

    def load(self, docs: dict) -> None:
        """docs: path -> Doc."""
        widths = []
        for path, doc in docs.items():
            name = posixpath.basename(path)
            if LOG_NAME.match(name):
                if self._table_log(path, doc, widths):
                    self.logs.add(path)
            m = ADR_FILE.search(path)
            if m:
                self._adr(path, doc, m.group(1))
        if self.items:
            self.width = min(widths) if widths else 1
            alts = []
            for p in sorted(self.prefixes):
                if p == "ADR":
                    alts.append(r"ADR[- ]?\d{1,5}")
                else:
                    alts.append(re.escape(p) + r"-?\d{%d,5}" % max(1, self.width))
            self.regex = re.compile(r"(?<![A-Za-z0-9_/.-])(?:" + "|".join(alts) + r")(?![A-Za-z0-9_])")

    def _rows(self, doc: Doc) -> list:
        """[(line, cells, header_cells)] for every `|` row whose first cell is an id."""
        heads = sorted((t.start, split_cells(doc.line_text(t.start))) for t in doc.tables)
        lines = sorted({n for t in doc.tables for n, _ in t.rows} | set(doc.orphan_rows))
        out = []
        for n in lines:
            cells = split_cells(doc.line_text(n))
            if not cells or not ID_CELL.match(cells[0]):
                continue
            head = []
            for start, h in heads:
                if start < n:
                    head = h
                else:
                    break
            out.append((n, cells, head))
        return out

    def _table_log(self, path: str, doc: Doc, widths: list) -> bool:
        rows = self._rows(doc)
        if len(rows) < 2:
            return False
        own = self.by_log.setdefault(path, {})
        prefixes = self.prefix_of.setdefault(path, set())
        pending = []
        for n, cells, head in rows:
            m = ID_CELL.match(cells[0])
            nid = norm(m.group(1), m.group(2))
            prefixes.add(m.group(1).upper())
            self.prefixes.add(m.group(1).upper())
            widths.append(len(m.group(2)))
            text = " ".join(cells)
            status_col = None
            for i, h in enumerate(head):
                if STATUS_HEAD.search(h):
                    status_col = i
            item = {"id": m.group(0).strip().strip("*").strip(), "log": path, "line": n,
                    "status": "active", "by": [], "note_line": n}
            if status_col is not None and len(cells) == len(head):
                self._status(item, cells[status_col], nid)
            else:
                # no status cell: only a bold marker inside the row counts, and a
                # marker in the middle of a long row replaces part of it at most
                for bm in BOLD.finditer(text):
                    seg = bm.group(1)
                    if PARTIAL.search(seg) or FULL.search(seg) or DEPRECATED.search(seg):
                        tail = text[bm.start():bm.end() + 200]
                        item["status"] = "amended"
                        item["by"] = self._refs(tail, nid)
                        break
                if item["status"] == "active" and len(text) < 300:
                    self._status(item, text, nid)
            own.setdefault(nid, item)
            self.items.setdefault(nid, item)
            for rm in REPLACES.finditer(text):
                for ref in REF.findall(rm.group(1)):
                    old = norm(*ref)
                    if old != nid:
                        pending.append((old, item["id"], n))
        for old, by, n in pending:
            it = own.get(old)
            if it and it["status"] == "active":
                it["status"] = "amended"
                it["by"].append(by)
                it["note_line"] = n
                it["note_log"] = path
            elif it and it["status"] == "amended" and by not in it["by"]:
                it["by"].append(by)
        return True

    @staticmethod
    def _refs(text: str, nid: str) -> list:
        out = []
        for p, num in REF.findall(text):
            r = norm(p, num)
            if r != nid and f"{p}{num}" not in out:
                out.append(f"{p}{num}")
        return out

    def _status(self, item: dict, text: str, nid: str) -> None:
        full = FULL.search(text) or DEPRECATED.search(text)
        if PARTIAL.search(text):
            item["status"] = "amended"
        elif full:
            lead = re.sub(r"[*_`(\[]", "", text[:full.start()]).strip(" :;,.-")
            # "bị thay (MD40)" is the status; "đồng ý; ... (**bị thay: MD67**)" replaces one clause
            item["status"] = "superseded" if len(lead) <= 12 else "amended"
        else:
            return
        item["by"] = self._refs(text, nid)

    def _adr(self, path: str, doc: Doc, number: str) -> None:
        self.adr = True
        self.prefixes.add("ADR")
        folder = posixpath.dirname(path)
        own = self.by_log.setdefault(folder, {})
        self.prefix_of.setdefault(folder, set()).add("ADR")
        nid = norm("ADR", number)
        status_text = ""
        for i, line in enumerate(doc.lines):
            low = line.strip().lower()
            if low.startswith(("status:", "* status:", "- status:", "**status**:", "**status:**")):
                status_text = line
                break
            if re.match(r"^#+\s*status\b", low):
                for nxt in doc.lines[i + 1:i + 6]:
                    if nxt.strip():
                        status_text = nxt
                        break
                break
        item = {"id": f"ADR-{number}", "log": path, "line": 1, "status": "active", "by": [], "note_line": 1}
        self._status(item, status_text, nid)
        own[nid] = item
        self.items.setdefault(nid, item)
        self.logs.add(path)

    @staticmethod
    def _key(ref: str) -> tuple:
        m = re.match(r"([A-Za-z]{1,6})[- ]?(\d{1,5})", ref)
        return (m.group(1).upper(), norm(m.group(1), m.group(2))) if m else (None, None)

    def lookup(self, ref: str, doc: str = "") -> dict | None:
        prefix, nid = self._key(ref)
        if nid is None:
            return None
        for log in self.logs_for(doc):
            it = self.by_log[log].get(nid)
            if it:
                return it
        return None

    def known_prefix(self, ref: str, doc: str = "") -> bool:
        """Is `ref` written in the id style of a log that applies to `doc`?"""
        prefix, _ = self._key(ref)
        return prefix is not None and any(prefix in self.prefix_of.get(log, ()) for log in self.logs_for(doc))

    def names_for(self, doc: str) -> str:
        return ", ".join(self.logs_for(doc)) or self.log_names
