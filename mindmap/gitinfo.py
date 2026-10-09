"""Git as a time machine: what did the repo look like when a doc line was written?

All paths given to and returned by `Git` are relative to the *scan root*;
the class converts to and from the repository top-level internally.
"""

from __future__ import annotations

import os
import re
import time
from bisect import bisect_left
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .files import GENERATED_DIRS, is_private, kind_of, run_git

ZERO = "0" * 40
HEX40 = re.compile(r"^[0-9a-f]{40}$")
# Does a code line define a name, or only use it? `%s` is the escaped name. A line that fits none
# of these only uses the name (a call, an import, a type from a library): the repo never owned it,
# so losing it is a note, not a warning. The patterns look at where the name sits, because in
# `static RegexSet build(` and `let set: RegexSet =` the word after the keyword is a type in use.
_TOK = r"[\w.:<>\[\],*&]*[\w>\],*&]"        # one type or modifier word; never ends in `:` (`x: T`, `lambda:`)
_NOT_STMT = (r"(?!(?i:return|throw|new|delete|goto|yield|await|else|elif|case|import|from|use|using|typeof|"
             r"sizeof|echo|print|puts|assert|raise|not|in|is|and|or|if|while|for|do|then|with|except|catch|"
             r"when|unless|until|exec|call|sudo|del|default|lambda|go|defer|select|insert|update|where|"
             r"values|export\s+default)\b)")
_NOT_IMPORT = r"(?!\s*=\s*(?:await\s+)?(?:require|import)\s*\()"       # `const X = require("x")` brings X in
DEFINES = (
    # key, variable, constant, a parameter on its own line: `name: 3`, `NAME = 3`, `"name": ...`, `- name:`
    r"""^\s*(?:-\s+)?["']?%s["']?\s*(?::(?!:)|\??=(?!=))""",
    r"""[\w\])]\.%s\s*=(?!=)""",                                         # `exports.name = `, `self.name = `
    r"""^\s*(?:export|local|readonly|typeset|declare(?:\s+-\w+)?|set|setx|ENV|ARG)\s+["']?%s\b""",
    # a declaring keyword, then the name: `def name`, `class Name`, `func (s *T) Name`, `impl<T> Name<T>`
    r"""\b(?:def|defp|defn|defmodule|defmacro|fn|fun|func|function|class|struct|enum|trait|interface|type|"""
    r"""module|mod|sub|namespace|object|record|protocol|union|alias|proc|macro|macro_rules!|impl)"""
    r"""(?:<[^>]*>)?\*?\s+(?:\([^)]*\)\s*)?(?:[\w.]+[.:]{1,2})?%s\b(?!\s+(?:for|from)\b)""",
    r"""\b(?:let|var|val)\s+(?:mut\s+)?%s\b""" + _NOT_IMPORT,
    r"""\b(?:const|static|final|readonly)\s+(?:(?:mut|ref|const|static|final|readonly)\s+)*%s\b"""
    r"""(?=\s*(?:[=:;,)\[]|$))""" + _NOT_IMPORT,
    # a parameter in a one-line signature: `def get(url, timeout=5):`
    r"""\b(?:def|fn|func|function|fun|sub)\s+[\w.:]+\s*(?:<[^>]*>)?\s*\((?:.*[(,])?\s*[*&]{0,2}%s\s*(?:[:=,)]|$)""",
    r"""#\s*define\s+%s\b""",
    r"""\bdefine\s*\(\s*["']%s["']""",
    r"""(?i:\bcreate\s+(?:or\s+replace\s+)?(?:table|view|function|procedure|index|trigger|type)\s+"""
    r"""(?:if\s+not\s+exists\s+)?)[\w."`\[\]]*?%s\b""",
    # C family, type first: `public void name(...) {`, `static const int NAME = 8;`, `private Foo name;`
    r"""^\s*(?:@[\w.]+(?:\([^)]*\))?\s+)*""" + _NOT_STMT + r"""(?:""" + _TOK + r"""\s+)+[*&]{0,2}(?:\w+::)*%s\s*\([^;]*$""",
    r"""^\s*""" + _NOT_STMT + r"""(?:""" + _TOK + r"""\s+)+[*&]{0,2}%s""" + _NOT_IMPORT + r"""\s*(?:\[[^\]]*\]\s*)?=(?!=)""",
    r"""^\s*(?:(?:public|private|protected|internal|static|final|readonly|const|volatile|transient|extern|mutable)"""
    r"""\s+)+(?:""" + _TOK + r"""\s+)*[*&]{0,2}%s\s*(?:\[[^\]]*\]\s*)?;""",
    # a method in a class body, a shell function: `name(a, b) {`, `name() {`; not a call that opens a block
    r"""^\s*(?:(?:async|static|public|private|protected|get|set|override|abstract)\s+)*\*?%s\s*"""
    r"""\((?:(?!\bfunction\b|=>)[^;])*\)\s*(?::\s*[\w<>\[\], |.]+?)?\s*\{\s*$""",
    r"""\btypedef\b.*\b%s\s*;""",
    r"""^\s*\}\s*%s\s*;""",                                              # `} name_t;` closing a typedef
    r"""^\s*\[\[?(?:[\w-]+\.)*%s\]\]?\s*$""",                            # TOML, INI section
    r"""^:%s\b""",                                                       # batch label
)
SHELL_FUNCTION = r"""^\s*%s\s*\(\s*\)\s*$"""    # `name()` alone on a line: a function in a shell script, a call elsewhere
SHELL_EXT = {"", ".sh", ".bash", ".zsh", ".ksh"}


def defines(text: str, name: str, rel: str = "x.py") -> bool:
    """Is `text` (one code line of `rel`) where `name` is defined, not just a place that uses it?"""
    if len(text) > 600:         # a minified bundle or a data line: nobody defines a name there by hand
        return False
    esc = re.escape(name)
    if any(re.search(p % ((esc,) * p.count("%s")), text) for p in DEFINES):
        return True
    return os.path.splitext(rel)[1].lower() in SHELL_EXT and re.search(SHELL_FUNCTION % esc, text) is not None


def day(epoch: int | float | str | None) -> str:
    """The day of a commit time, in UTC: the same text on every machine, whatever its time zone."""
    try:
        return time.strftime("%Y-%m-%d", time.gmtime(float(epoch))) if epoch else ""
    except (ValueError, OverflowError, OSError):
        return ""


class History:
    """Every add, delete and rename in the repo, read with one `git log`.

    Commits get a position: 0 is HEAD, larger is older (topological order).
    The index answers "did the repo ever have this path" and "which commit took
    it away". It reads the log as one line of commits, so it cannot say what a
    given commit had when histories run side by side: `Git.in_tree` does that.
    """

    def __init__(self, git: "Git"):
        self.commits: list = []                  # position -> (short sha, epoch)
        self.pos: dict[str, int] = {}            # full sha -> position
        self.events: dict[str, list] = defaultdict(list)   # path -> [(pos, kind, other)], newest first
        self.under: dict[str, set] = defaultdict(set)      # dir -> every file ever below it
        self.names: dict[str, set] = defaultdict(set)      # basename (casefold) -> files and dirs ever
        out = git._git(["log", "--topo-order", "-M", "--name-status", "-z", "--no-color",
                        "--format=%x01%H%x02%ct", "HEAD"], timeout=300)
        self.ok = out is not None
        for chunk in (out or b"").split(b"\x01")[1:]:
            head, _, body = chunk.partition(b"\0")
            sha, _, ct = head.decode("ascii", "replace").partition("\x02")
            p = len(self.commits)
            try:
                self.commits.append((sha[:10], int(ct.strip() or 0)))
            except ValueError:
                self.commits.append((sha[:10], 0))
            self.pos[sha] = p
            fields = body.lstrip(b"\n").split(b"\0")
            j = 0
            while j < len(fields):
                st = fields[j].decode("ascii", "replace").strip()
                if not st:
                    j += 1
                    continue
                if st[0] in "RC" and j + 2 < len(fields):
                    old = git.from_top(fields[j + 1].decode("utf-8", "replace"))
                    new = git.from_top(fields[j + 2].decode("utf-8", "replace"))
                    j += 3
                    if st[0] == "R" and old is not None:
                        self._add(old, p, "D", new)
                    if new is not None:
                        self._add(new, p, "A", old)
                elif j + 1 < len(fields):
                    path = git.from_top(fields[j + 1].decode("utf-8", "replace"))
                    j += 2
                    if path is not None:
                        self._add(path, p, "D" if st[0] == "D" else "A" if st[0] == "A" else "M", None)
                else:
                    break

    def _add(self, path: str, p: int, kind: str, other) -> None:
        ev = self.events[path]
        if not ev:
            name = path.rsplit("/", 1)[-1].casefold()
            self.names[name].add(path)
            parts = path.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                d = "/".join(parts[:i])
                if d not in self.under:
                    self.names[parts[i - 1].casefold()].add(d)
                self.under[d].add(path)
        ev.append((p, kind, other))

    def position(self, sha: str | None, epoch: int | None = None) -> int:
        """Position of a commit; 0 (HEAD) when unknown."""
        if sha and sha in self.pos:
            return self.pos[sha]
        if epoch:
            for i, (_, t) in enumerate(self.commits):
                if t <= epoch:
                    return i
        return 0

    def ever(self, path: str) -> bool:
        return path in self.events or path in self.under

    def file_at(self, path: str, p: int) -> bool:
        ev = self.events.get(path)
        if not ev:
            return False
        keys = [e[0] for e in ev]                  # increasing: newest first
        i = bisect_left(keys, p)
        return i < len(ev) and ev[i][1] != "D"

    def last_seen(self, path: str) -> int | None:
        """Newest position at which `path` (file or dir) still existed."""
        best = None
        for f in ([path] if path in self.events else list(self.under.get(path, ()))[:2000]):
            for q, kind, _ in self.events.get(f, ()):
                if kind != "D":
                    if best is None or q < best:
                        best = q
                    break
        return best

    def gone(self, path: str, p: int) -> dict | None:
        """How did `path`, present at `p`, disappear later? {to, sha, date, deleted}"""
        files = [path] if path in self.events else [f for f in self.under.get(path, ()) if self.file_at(f, p)]
        moves: dict = defaultdict(int)
        first = None
        for f in files[:400]:
            for q, kind, other in reversed(self.events.get(f, ())):    # oldest first
                if q >= p or kind != "D":
                    continue
                sha, epoch = self.commits[q]
                if first is None or q < first[0]:
                    first = (q, sha, epoch)
                if other:
                    rest = f[len(path):] if f != path else ""
                    to = other[: len(other) - len(rest)] if rest and other.endswith(rest) else other
                    moves[(to, sha, epoch)] += 1
                break
        if moves:
            (to, sha, epoch), _ = max(moves.items(), key=lambda kv: kv[1])
            return {"to": to.rstrip("/"), "sha": sha, "date": day(epoch), "deleted": False}
        if first:
            return {"to": None, "sha": first[1], "date": day(first[2]), "deleted": True}
        return None


class Git:
    def __init__(self, top: Path, scan_root: Path):
        self.top = Path(top).resolve()
        self.scan_root = Path(scan_root).resolve()
        rel = os.path.relpath(self.scan_root, self.top).replace("\\", "/")
        self.sub = "" if rel == "." else rel + "/"      # scan root inside top
        self.nested = rel.startswith("..")              # repo below the scan root
        if self.nested:
            up = os.path.relpath(self.top, self.scan_root).replace("\\", "/")
            self.prefix = up + "/"
            self.sub = ""
        else:
            self.prefix = ""
        self._blame: dict[str, dict | None] = {}
        self._in_tree: dict[tuple, bool] = {}
        self._ancestor: dict[tuple, bool] = {}
        self._show: dict[tuple, str | None] = {}
        self._times: dict[str, int] | None = None
        self._head: str | None | bool = False
        self._history: History | None = None
        self._removed: dict[tuple, dict | None] = {}
        self._alive: dict[str, bool] = {}
        self._headings: dict[str, list] = {}

    # -- path mapping --------------------------------------------------
    def to_top(self, rel: str) -> str:
        if self.prefix and rel.startswith(self.prefix):
            rel = rel[len(self.prefix):]
        return self.sub + rel

    def from_top(self, rel_top: str) -> str | None:
        if self.sub:
            if not rel_top.startswith(self.sub):
                return None
            rel_top = rel_top[len(self.sub):]
        return self.prefix + rel_top

    def _git(self, args, **kw):
        return run_git(args, self.top, **kw)

    # -- basics --------------------------------------------------------
    def head(self) -> str | None:
        if self._head is False:
            out = self._git(["rev-parse", "HEAD"], timeout=20)
            self._head = out.decode().strip() if out else None
        return self._head or None

    def blame(self, rel: str) -> dict | None:
        """line -> (sha, epoch). None when the file is not in HEAD (new file)."""
        if rel in self._blame:
            return self._blame[rel]
        out = self._git(["blame", "-w", "--porcelain", "--", self.to_top(rel)], timeout=120)
        result = None
        if out is not None:
            result = {}
            times: dict[str, int] = {}
            sha = ""
            final = 0
            for raw in out.decode("utf-8", "replace").split("\n"):
                if raw.startswith("\t"):
                    if sha:
                        result[final] = (sha, times.get(sha, 0))
                    continue
                parts = raw.split(" ")
                if HEX40.match(parts[0]) and len(parts) >= 3:
                    sha = parts[0]
                    try:
                        final = int(parts[2])
                    except ValueError:
                        final = 0
                elif parts[0] == "committer-time" and sha:
                    try:
                        times[sha] = int(parts[1])
                    except (ValueError, IndexError):
                        pass
        self._blame[rel] = result
        return result

    def prefetch_blame(self, rels) -> None:
        """Blame many docs at once (git runs in parallel; results are cached)."""
        todo = [r for r in dict.fromkeys(rels) if r not in self._blame]
        if len(todo) > 1:
            with ThreadPoolExecutor(max_workers=min(8, len(todo))) as pool:
                list(pool.map(self.blame, todo))
        elif todo:
            self.blame(todo[0])

    def history(self) -> History:
        if self._history is None:
            self._history = History(self)
        return self._history

    def written_at(self, doc: str, line: int) -> tuple:
        """(rev, epoch) of the commit that last wrote this doc line.

        rev is None when the line is not committed yet (then HEAD is the
        best "before" picture)."""
        b = self.blame(doc)
        if not b or line not in b:
            return None, None
        sha, epoch = b[line]
        if sha == ZERO:
            return None, None
        return sha, epoch

    def in_tree(self, rev: str, rels) -> set:
        """Which of these paths (files or folders) the commit `rev` itself has.

        The history index reads the log as one line of commits. A repo that merged another history in
        (a subtree, a project with another layout) has commits side by side, and the index then takes a
        file of one side for a file of the other. The tree of the commit is the proof; no answer from
        git means no proof."""
        rels = list(rels)
        ask = {rel: self.to_top(rel).rstrip("/") for rel in rels if (rev, rel) not in self._in_tree}
        tops = sorted({t for t in ask.values() if t and not t.startswith(":")})    # `:` would start pathspec magic
        have: set[str] = set()
        for i in range(0, len(tops), 50):
            out = self._git(["ls-tree", "-z", "--name-only", "--full-tree", rev, "--", *tops[i:i + 50]], timeout=60)
            have.update(raw.decode("utf-8", "replace") for raw in (out or b"").split(b"\0") if raw)
        for rel, top in ask.items():
            self._in_tree[(rev, rel)] = top in have
        return {rel for rel in rels if self._in_tree[(rev, rel)]}

    def is_ancestor(self, older: str, newer: str) -> bool:
        """Does `newer` come after `older` on the same line of history?"""
        key = (older, newer)
        if key not in self._ancestor:
            self._ancestor[key] = self._git(["merge-base", "--is-ancestor", older, newer], timeout=30) is not None
        return self._ancestor[key]

    def show(self, rev: str, rel: str) -> str | None:
        key = (rev, rel)
        if key not in self._show:
            out = self._git(["show", f"{rev}:{self.to_top(rel)}"], timeout=60)
            self._show[key] = out.decode("utf-8", "replace") if out is not None else None
        return self._show[key]

    # -- searching the past ----------------------------------------------
    def grep_words(self, rev: str, names: list) -> dict:
        """name -> (path, line, defined) of a code file mentioning it at `rev`.

        The line that defines the name wins over lines that only use it;
        `defined` is False when no line at `rev` looks like its definition."""
        found: dict[str, tuple] = {}
        names = sorted(set(n for n in names if n))
        for i in range(0, len(names), 60):
            chunk = names[i:i + 60]
            args = ["grep", "-n", "-w", "-F", "-I", "--no-color"]
            for n in chunk:
                args += ["-e", n]
            args += [rev, "--"]
            if self.sub:
                args.append(self.sub)
            out = self._git(args, timeout=120, ok_codes=(0, 1))
            if not out:
                continue
            for raw in out.decode("utf-8", "replace").split("\n"):
                if not raw.startswith(rev + ":"):
                    continue
                rest = raw[len(rev) + 1:]
                m = re.match(r"(.*?):(\d+):(.*)$", rest)
                if not m:
                    continue
                rel = self.from_top(m.group(1))
                if rel is None or not self._is_code(rel):
                    continue
                text = m.group(3)
                for n in chunk:
                    if n in found and found[n][2]:
                        continue
                    if re.search(r"(?<![A-Za-z0-9_])" + re.escape(n) + r"(?![A-Za-z0-9_])", text):
                        d = defines(text, n, rel)
                        if d or n not in found:
                            found[n] = (rel, int(m.group(2)), d)
        return found

    def alive_words(self, names: list) -> set:
        """Names a file of the working tree still has, docs and their HTML renderings aside.

        The code index reads known file types; this also sees a script without
        an extension (`bin/publish`) and types the index does not know. When
        git cannot answer, the name counts as alive: no proof, no finding."""
        todo = [n for n in dict.fromkeys(names) if n and n not in self._alive]
        for i in range(0, len(todo), 60):
            chunk = todo[i:i + 60]
            args = ["grep", "-I", "-o", "-h", "-w", "-F", "--untracked", "--no-color"]
            for n in chunk:
                args += ["-e", n]
            args += ["--", self.sub or ".", ":(exclude)*.md", ":(exclude)*.markdown", ":(exclude)*.mdx",
                     ":(exclude)*.html", ":(exclude)*.htm"]
            out = self._git(args, timeout=60, ok_codes=(0, 1))
            hits = None if out is None else set(out.decode("utf-8", "replace").split())
            for n in chunk:
                self._alive[n] = hits is None or n in hits
        return {n for n in names if self._alive.get(n)}

    def headings_removed(self, rel: str) -> list:
        """Heading lines `rel` lost, newest first: [{"sha", "date", "subject", "text"}], from one pass over
        the file's own history. A `#` line of a code block is listed too: the caller reads the page
        before and after the commit."""
        if rel not in self._headings:
            out = self._git(["log", "-n", "500", "-p", "-U0", "--no-color", "--format=%x01%H%x00%ct%x00%s",
                             "--", self.to_top(rel)], timeout=30)
            found = []
            for block in (out or b"").decode("utf-8", "replace").split("\x01")[1:]:
                head, _, diff = block.partition("\n")
                sha, date, subject = (head.split("\x00", 2) + ["", ""])[:3]
                subject = re.sub(r"\s+", " ", "".join(ch for ch in subject if ch.isprintable())).strip()[:80]
                for line in diff.split("\n"):
                    if line.startswith("-#") and not line.startswith("---"):
                        found.append({"sha": sha, "date": day(date), "subject": subject,
                                      "text": line[1:].lstrip("#").strip()})
            self._headings[rel] = found
        return self._headings[rel]

    def removed_in(self, rev: str, rel: str, name: str) -> dict | None:
        """The commit after `rev` that took `name` out of `rel`: {"sha", "date", "subject"}.

        None when unsure: the file came or went in that commit (the name may
        have moved with it), the name is still in the file, or git gave up."""
        key = (rev, rel, name)
        if key not in self._removed:
            self._removed[key] = self._removed_in(rev, rel, name)
        return self._removed[key]

    def _removed_in(self, rev: str, rel: str, name: str) -> dict | None:
        # whole-word pickaxe: a plain -S would still count `build_index` inside `rebuild_index`
        whole = r"(^|[^A-Za-z0-9_-])" + re.sub(r"([.\[\]{}()*+?^$|\\])", r"\\\1", name) + r"([^A-Za-z0-9_-]|$)"
        out = self._git(["log", "-n", "1", "--pickaxe-regex", "-S" + whole, "--format=%H%x00%ct%x00%s",
                         f"{rev}..HEAD", "--", self.to_top(rel)], timeout=20)
        sha, date, subject = ((out or b"").decode("utf-8", "replace").strip().split("\x00", 2) + ["", ""])[:3]
        if not sha:
            return None
        after, before = self.show(sha, rel), self.show(sha + "^", rel)
        if after is None or before is None:
            return None
        word = re.compile(r"(?<![\w-])" + re.escape(name) + r"(?![\w-])")
        if word.search(after) or not word.search(before):
            return None
        subject = re.sub(r"\s+", " ", "".join(ch for ch in subject if ch.isprintable())).strip()
        return {"sha": sha[:10], "date": day(date), "subject": subject[:80]}

    @staticmethod
    def _is_code(rel: str) -> bool:
        if kind_of(rel) not in ("code", "conf") or is_private(rel):
            return False
        if rel.lower().endswith((".html", ".htm")):
            return False      # may be a rendering of a doc
        return not any(seg.lower() in GENERATED_DIRS for seg in rel.split("/")[:-1])

    def follow(self, rev: str, rel: str) -> dict | None:
        """Where did `rel` (file or dir) go after `rev`? {"to", "sha", "date", "deleted"}"""
        top_path = self.to_top(rel).rstrip("/")
        out = self._git(["log", "-M", "--name-status", "--diff-filter=RD",
                         "--format=%x01%h %ct", f"{rev}..HEAD", "--", top_path], timeout=120)
        if not out:
            return None
        events = []
        sha, date = "", ""
        for raw in out.decode("utf-8", "replace").split("\n"):
            if raw.startswith("\x01"):
                sha, _, stamp = raw[1:].partition(" ")
                date = day(stamp)
                continue
            parts = raw.split("\t")
            if len(parts) == 3 and parts[0].startswith("R"):
                events.append(("R", parts[1], parts[2], sha, date))
            elif len(parts) == 2 and parts[0] == "D":
                events.append(("D", parts[1], "", sha, date))
        for kind, old, new, sha, date in reversed(events):      # oldest first
            if old == top_path or old.startswith(top_path + "/"):
                if kind == "D":
                    if old == top_path:
                        return {"to": None, "sha": sha, "date": date, "deleted": True}
                    continue
                rest = old[len(top_path):]
                to = new[: len(new) - len(rest)] if rest and new.endswith(rest) else new
                to_rel = self.from_top(to)
                return {"to": to_rel, "sha": sha, "date": date, "deleted": False}
        return None

    def last_times(self, max_commits: int = 3000) -> dict:
        """path -> epoch of the last commit touching it."""
        if self._times is not None:
            return self._times
        out = self._git(["log", "--format=%x01%ct", "--name-only", "-n", str(max_commits)], timeout=180)
        times: dict[str, int] = {}
        current = 0
        for raw in (out or b"").decode("utf-8", "replace").split("\n"):
            if raw.startswith("\x01"):
                try:
                    current = int(raw[1:])
                except ValueError:
                    current = 0
            elif raw:
                rel = self.from_top(raw)
                if rel is not None and rel not in times:
                    times[rel] = current
        self._times = times
        return times

    def ignored(self, rels: list) -> set:
        """Subset of scan-root-relative paths that .gitignore marks as ignored."""
        if not rels:
            return set()
        tops = {self.to_top(r): r for r in rels}
        data = b"\0".join(t.encode("utf-8") for t in tops) + b"\0"
        out = self._git(["check-ignore", "--stdin", "-z"], stdin=data, timeout=60, ok_codes=(0, 1))
        res = set()
        for raw in (out or b"").split(b"\0"):
            t = raw.decode("utf-8", "replace")
            if t in tops:
                res.add(tops[t])
        return res

    def modified_now(self) -> set:
        """Scan-root-relative paths with uncommitted changes (incl. untracked)."""
        out = self._git(["status", "--porcelain", "-z", "--untracked-files=all"], timeout=120)
        res = set()
        items = (out or b"").split(b"\0")
        i = 0
        while i < len(items):
            raw = items[i].decode("utf-8", "replace")
            i += 1
            if len(raw) < 4:
                continue
            code, path = raw[:2], raw[3:]
            if code[0] in "RC":
                i += 1          # skip the source path of a rename/copy
            rel = self.from_top(path)
            if rel is not None:
                res.add(rel)
        return res
