"""Verify claims against the working tree and the git history.

Rule of thumb: something a doc mentions but the repo lacks is only reported
when we can show it *belonged to the repo* (git history has it), when it is
a link (a reader clicks it), or when a near-identical name exists (a typo).
Everything else is "unverified": planned files, runtime output, other
products. Lines that say the thing was removed ("removed", "đã xóa", "cũ"...)
or strike it through are taken as already acknowledged.

How strict depends on the doc type (see doctype.py): history docs only get
decision-id checks, plan docs get everything at info level.
"""

from __future__ import annotations

import difflib
import fnmatch
import os
import posixpath
import re
import time
from collections import Counter, defaultdict

from .codeindex import IDENT, CodeIndex, stdlib_names
from .cost import AGENT_NAMES, AGENT_PATHS
from .claims import has_placeholder
from .doctype import is_post
from .files import GENERATED_DIRS, Inventory, is_private, kind_of
from .gitinfo import Git, day
from .globs import match_any
from .mdscan import scan, skeleton
from .model import ERROR, INFO, WARNING, Claim, Finding, evidence_text, fingerprint, message

FORBID = re.compile(r"^forbid\s+(?:/(.+)/([imsx]*)|\"([^\"]+)\"|'([^']+)')(?:\s+in\s+(.+))?$", re.I)
NUMBER = re.compile(r"\d+(?:[.,/]\d+)*")
SENSITIVE_VALUE = re.compile(r"(?i)((?:key|token|secret|password|passwd|credential|cookie|auth)\w*[\"']?\s*[:=]\s*[\"']?)[^\s\"']{6,}")
GONE_WORDS = re.compile(
    r"\b(?:removed|deleted|renamed|deprecated|obsolete|legacy|formerly|no longer|used to|replaced|"
    r"retired|dropped|moved to|was moved|old)\b"
    r"|(?<!\w)(?:xóa|xoá|gỡ|đổi tên|thay bằng|đã bỏ|bỏ hẳn|đã gộp|gộp vào|dời sang|đã dời|không còn|"
    r"trước đây|cũ|không dùng|đừng dùng|cấm dùng)(?!\w)"
    r"|\b(?:do not use|don't use|never use|avoid)\b", re.I)
DONE_CELL = re.compile(r"^\s*(?:\**\s*)?(?:(?:done|xong|đã xong|hoàn tất|hoàn thành|closed|merged|shipped)\b|[✅☑✔])", re.I)
DONE_LINE = re.compile(r"^\s*[-*+]\s+\[[xX]\]|✅|\bDONE\b|\bXONG\b")
JS_GLOBALS = {"console", "window", "document", "JSON", "Math", "process", "Object", "Array", "Promise",
              "navigator", "localStorage", "sessionStorage", "globalThis", "Number", "String", "Date",
              "Reflect", "Symbol", "Intl", "fetch", "require", "module", "exports", "Buffer"}
STRUCTURAL = {"table-orphan", "table-shape", "rule-invalid", "rule-violation"}
# "it existed, now it is gone" findings; in a sentence about the past they are a record, not a claim about now
PAST_RULES = {"symbol-gone", "symbol-removed-now", "path-gone", "path-moved", "path-removed-now",
              "flag-removed", "subcommand-missing"}
EACH_NOUNS = (r"câu|video|file|dòng|bước|người|cái|phần|mục|lần|cảnh|bài|trang|chữ|từ|ô|khung|đoạn|chương|"
              r"tập|ngày|tuần|tháng|cue|clip|lượt|nhóm|loại|kênh|job|đơn|phiên|ảnh|hình|bản|tool|task|vùng|"
              r"màn|nút|tab|cột|hàng|thứ|chút|chỗ|nơi|con|chiếc|một|module|hàm|lớp|tầng|frame|giây|phút|"
              r"stage|series|track|model|agent|điểm|việc")
PAST_CONTEXT = re.compile(
    r"\bv?\d+(?:\.\d+)+\s*[–—-]\s*v?\d+(?:\.\d+)+\b"                      # v1.2–v1.6
    r"|\b(?:previously|originally|historically|in the past|earlier versions?|back then|at the time|"
    r"measured (?:on )?\d)"
    r"|(?<!\w)(?:hồi đó|hồi trước|lúc đó|khi đó|ngày trước|lúc trước|thời điểm đó|"
    r"(?:đo|tính đến)(?: ngày)? \d{1,2}/\d{1,2})(?!\w)"
    r"|(?<!\w)từng(?!\w)(?!\s+(?:" + EACH_NOUNS + r")(?!\w))", re.I)     # "từng lọt" = once; "từng câu" = each
TRANSLATED_NAME = re.compile(r"[-_.]([a-z]{2})(?:[-_][A-Za-z0-9]{2,4})?\.(?:md|mdx|markdown)$", re.I)   # README-ja.md
# a place in the reader's project: "can be stored at `docs/.vitepress/config.ts`", "in our case, `docs/public/x`"
FOR_READER = re.compile(
    r"\b(?:(?:can|could|should|must|may|might) (?:also )?be (?:stored|placed|put|kept|created|added|saved|located)"
    r"|(?:you|we) (?:can|could|should|may|might|must|need to|have to|will) (?:also )?"
    r"(?:create|add|place|put|store|save|keep|write)|in our case|in your (?:project|repo|repository|app))\b", re.I)
# a page about a feature that is gone: said in its opening, before the first section
RETIRED_PAGE = re.compile(
    r"\b(?:has|have) been (?:removed|deprecated|discontinued|dropped)\b|\bwas (?:removed|discontinued|dropped)\b"
    r"|\bno longer (?:supported|maintained|available)\b|\b(?:removed|deprecated|discontinued) (?:experimental )?feature\b"
    r"|(?<!\w)(?:đã bị (?:gỡ|xóa|xoá|bỏ)|không còn được (?:hỗ trợ|duy trì))(?!\w)", re.I)
# a name a code block of the doc declares: `const isActive =`, `def handler(`, `func (s *S) Serve(`
EXAMPLE_DECL = re.compile(
    r"\b(?:const|let|var|val|def|class|function|fn|struct|enum|interface|trait)\s+\*?\s*([A-Za-z_$][\w$]*)"
    r"|\bfunc\s+(?:\([^)]*\)\s*)?([A-Za-z_]\w*)")
PACKAGE_MANIFESTS = ("package.json", "go.mod", "Cargo.toml", "pyproject.toml", "setup.py", "pom.xml", "build.gradle",
                     "build.gradle.kts", "Package.swift", "pubspec.yaml", "composer.json", "mix.exs")
PATHISH = re.compile(r"[^\s`'\"()\[\]<>|,;]*/[^\s`'\"()\[\]<>|,;]*")
LANG_CODES = set("ar bg bn ca cs da de el en es et fa fi fr he hi hr hu hy id it ja ka kk ko lt lv mk ml mn "
                 "mr ms my nb ne nl no pa pl pt ro ru si sk sl sq sr sv sw ta te th tl tr uk ur uz vi zh".split())
LANG_DIR = re.compile(r"^([a-z]{2})(?:[-_][a-z0-9]{2,4})?$", re.I)          # fr, zh-hant, pt_BR
BLOCK_START = re.compile(r"^\s*(?:#|>|\||```|~~~|[-*+]\s|\d+[.)]\s)")   # a line that starts its own block
BLOCK_END = re.compile(r"^\s*(?:#|\||```|~~~)")                     # a line no paragraph runs on from
SENTENCE_END = re.compile(r"(?<=[.!?;])\s+|\s\|\s")
# File and folder names so common that a path ending in one says nothing about which file was meant.
COMMON_NAMES = set(
    "readme.md index.md index.html index.js index.ts index.jsx index.tsx main.py main.js main.ts main.go main.rs "
    "main.c main.cpp lib.rs mod.rs __init__.py __main__.py app.py app.js app.ts cli.py config.py settings.py "
    "utils.py setup.py manage.py conftest.py test.py tests.py server.js server.py package.json tsconfig.json "
    "pyproject.toml requirements.txt makefile dockerfile run.bat run.sh config.json config.yaml config.yml "
    "config.toml style.css styles.css license changelog.md "
    "src app lib docs doc tests test scripts bin utils config assets static public dist build data examples "
    "templates tools core common api models views components".split())
SITE_PAGE_EXT = (".md", ".mdx", ".markdown", ".rst", ".html", ".htm", ".ipynb", ".qmd")
SITE_INDEX = ("index", "readme", "_index")      # the page a site serves at the folder's own address
QUEUE_TEXT = (".md", ".mdx", ".markdown", ".rst", ".adoc", ".txt")   # what work items are written in
SUBCOMMAND_DEF = re.compile(
    r"add_parser\(\s*[\"']([^\"']+)[\"']"
    r"|@\w+(?:\.\w+)*\.command\(\s*(?:name\s*=\s*)?[\"']([^\"']+)[\"']"
    r"|@\w+(?:\.\w+)*\.command\(\s*\)\s*\n\s*(?:async\s+)?def\s+(\w+)")


def redact(text: str) -> str:
    """Never echo something that looks like a secret value."""
    return SENSITIVE_VALUE.sub(r"\1***", text)


def path_literals(literal: str) -> list:
    """What a string in the code says about paths: itself, and for an import path its endings (`pkg/bindings` of
    `"github.com/containers/podman/v5/pkg/bindings"`, a library's package). A long string (base64, a minified
    bundle, thousands of `/`) is no path: its endings once filled the memory of a whole workspace run."""
    literal = literal.replace("\\", "/")
    if len(literal) > 400:
        return []
    out = [posixpath.normpath(literal)]
    if "/" in literal and not any(ch.isspace() for ch in literal):
        parts = literal.strip("/").split("/")
        out += ["/".join(parts[k:]) for k in range(1, len(parts) - 1)]
    return out


def _agent_doc(path: str) -> bool:
    """An instruction file a coding agent loads (CLAUDE.md, AGENTS.md... at any depth)."""
    return posixpath.basename(path).lower() in AGENT_NAMES or path in AGENT_PATHS


class PathIndex:
    def __init__(self, inv: Inventory):
        self.by_name: dict[str, list] = defaultdict(list)
        self.children: dict[str, list] = defaultdict(list)
        for p in list(inv.files) + list(inv.dir_set):
            name = p.rsplit("/", 1)[-1]
            self.by_name[name.casefold()].append(p)
            self.children[posixpath.dirname(p)].append(name)

    def suffix(self, t: str, area: str = "") -> str | None:
        """A file or folder whose path ends with `t`. A bare name is only
        looked up inside `area` (the doc's project), never in another project."""
        t = t.strip("/")
        if not t:
            return None
        tf = t.casefold()
        bare = "/" not in tf
        for full in self.by_name.get(tf.rsplit("/", 1)[-1], ()):
            ff = full.casefold()
            if ff == tf or ff.endswith("/" + tf):
                if bare and area and not full.startswith(area + "/"):
                    continue
                return full
        return None


class Checker:
    def __init__(self, inv: Inventory, index: CodeIndex, gits: dict, decisions, docs: dict,
                 lang: str = "en", kinds: dict | None = None, light: bool = False, load_doc=None):
        self.inv = inv
        self.index = index
        self.gits = gits            # repo prefix ('' = root) -> Git
        self.decisions = decisions
        self.docs = docs            # path -> Doc
        self.kinds = kinds or {}    # doc path -> live | plan | history
        self.lang = lang
        self.light = light          # one doc only: skip checks that compare all docs
        self.load_doc = load_doc
        self.paths = PathIndex(inv)
        self.findings: list[Finding] = []
        self._reported: dict = {}           # (fingerprint, line) -> the finding already made
        self.external = stdlib_names() | set(index.imports) | JS_GLOBALS
        self._now = time.time()
        self._docusaurus_sites = sorted(
            {posixpath.dirname(path) for path in inv.file_set
             if posixpath.basename(path) in (
                 "docusaurus.config.js", "docusaurus.config.ts",
                 "docusaurus.config.mjs", "docusaurus.config.cjs",
                 "sidebars.js", "sidebars.ts", "sidebars.json",
                 "sidebars.cjs", "sidebars.mjs")},
            key=len, reverse=True)
        self._modified: set | None = None
        self._never_links: dict[str, list] = defaultdict(list)
        self._mirrors: dict | None = None
        self._removed_left = 200        # lookups of "which commit removed it" a run may spend
        self._link_total: dict[str, int] = defaultdict(int)
        self._site_trees: set = set()       # docs trees where a site address led to a source page
        self._skeletons: dict[str, set] = {}
        self._spell: dict | None = None     # case-folded path -> the spelling the repo uses
        self._listings: dict[str, list] = {}
        self._examples: dict[str, set] = {}
        self._retired: dict[str, bool] = {}
        self._ignore_rules: dict[str, list] = {}
        self._path_strings: set[str] | None = None
        self._manifest_texts: list | None = None
        self._queues: dict[str, bool] = {}
        self._other_projects: dict[str, bool] = {}
        self._own_names: set | None = None

    # -- helpers -------------------------------------------------------------
    def git_for(self, rel: str) -> Git | None:
        return self.gits.get(self.inv.repo_of(rel)) or (self.gits.get("") if "" in self.gits else None)

    def kind(self, doc: str) -> str:
        return self.kinds.get(doc, "live")

    def add(self, rule: str, sev: str, c: Claim | None, path: str = "", line: int = 0, col: int = 1,
            evidence=None, suggestion: str = "", **kw) -> Finding:
        path = path or (c.doc if c else "")
        line = line or (c.line if c else 1)
        col = col if c is None else c.col
        if sev != INFO and rule not in STRUCTURAL and (self.kind(path) == "plan" or self._done_line(path, line)):
            sev = INFO          # plans describe intent; finished items describe the past
        if sev != INFO and c is not None and rule in PAST_RULES and (self._past(c) or self._retired_page(c.doc)
                                                                   or is_post(c.doc) or self._translated(c.doc)):
            sev = INFO      # a dated post tells of its day; a translation follows its source page, which is warned
        claim_text = c.text if c else kw.get("claim", "")
        kw.setdefault("claim", claim_text)
        msg = message(rule, self.lang, **kw)
        line_text = ""
        d = self.docs.get(path)
        if d is not None:
            line_text = d.line_text(line)
        evidence = [dict(e, note=evidence_text(e.get("note", ""), self.lang),
                         text=evidence_text(e.get("text", ""), self.lang)) for e in evidence or []]
        evidence = [{k: v for k, v in e.items() if v != ""} for e in evidence]
        f = Finding(rule, sev, path, line, col, msg, claim_text, evidence, suggestion,
                    fingerprint(rule, path, claim_text, line_text))
        key = (f.fingerprint, line)
        if key in self._reported:       # one name in two cells of a table row: one finding
            f = self._reported[key]
        else:
            self._reported[key] = f
            self.findings.append(f)
        if c is not None:
            c.status = "broken" if sev in (ERROR, WARNING) else c.status
        return f

    def _done_line(self, path: str, line: int) -> bool:
        """A finished task (a DONE row, a ticked box): it describes the past."""
        d = self.docs.get(path)
        text = d.line_text(line) if d is not None else ""
        if not text:
            return False
        if text.lstrip().startswith("|"):
            from .mdscan import split_cells
            return any(DONE_CELL.match(cell) for cell in split_cells(text)[1:])
        return bool(DONE_LINE.search(text))

    def sentence(self, c: Claim) -> str:
        """The sentence holding the claim, read across the hard-wrapped lines of its paragraph.
        A table row is one unit: its cells talk about the same thing."""
        d = self.docs.get(c.doc)
        line = d.line_text(c.line) if d is not None else ""
        if not line or line.lstrip().startswith("|"):
            return line
        lo = hi = c.line
        while lo > 1 and c.line - lo < 8 and not BLOCK_START.match(d.line_text(lo)) \
                and d.line_text(lo - 1).strip() and not BLOCK_END.match(d.line_text(lo - 1)):
            lo -= 1
        while hi < len(d.lines) and hi - c.line < 8 and d.line_text(hi + 1).strip() \
                and not BLOCK_START.match(d.line_text(hi + 1)) and not BLOCK_END.match(d.line_text(hi + 1)):
            hi += 1
        parts = [d.line_text(n).strip() for n in range(lo, hi + 1)]
        text = " ".join(parts)
        before = sum(len(x) + 1 for x in parts[: c.line - lo])
        lead = len(line) - len(line.lstrip())
        i = c.col - 1
        if not (0 <= i < len(line) and line.startswith(c.text, i)):
            i = line.find(c.text)
        if i < 0:
            return line
        i = before + max(0, i - lead)
        start, end = 0, len(text)
        for m in SENTENCE_END.finditer(text):
            if m.end() <= i:
                start = m.end()
            elif m.start() > i:
                end = m.start()
                break
        return text[start:end]

    def _past(self, c: Claim) -> bool:
        """The sentence holding the claim talks about the past ("v1.2–v1.6 put X in", "X once leaked")."""
        return bool(PAST_CONTEXT.search(self.sentence(c)))

    def acknowledged(self, c: Claim) -> bool:
        """The line, or the wrapped sentence, says the thing is gone (or strikes it through)."""
        d = self.docs.get(c.doc)
        line = d.line_text(c.line) if d is not None else ""
        if not line:
            return False
        if GONE_WORDS.search(line) or GONE_WORDS.search(self.sentence(c)):
            return True
        for m in re.finditer(r"~~(.+?)~~", line):
            if c.text in m.group(1):
                return True
        return False

    def _bases(self, c: Claim) -> list:
        ddir = posixpath.dirname(c.doc)
        bases = []
        cwd = c.extra.get("cwd")
        if cwd:
            bases += [posixpath.normpath(posixpath.join(ddir, cwd)) if ddir else cwd, cwd]
        d = ddir
        while d:
            bases.append(d)
            d = posixpath.dirname(d)
        bases += [self.inv.repo_of(c.doc), ""]
        return list(dict.fromkeys(bases))

    def _cands(self, c: Claim) -> list:
        t = c.target
        anchor = c.extra.get("anchor")
        if anchor in ("root", "exact"):
            out = [posixpath.normpath(t)]
            directory = posixpath.dirname(c.doc)
            if c.ctx == "tree" and directory and t.startswith(directory + "/"):
                rooted = posixpath.normpath(posixpath.join(self.inv.repo_of(c.doc), t[len(directory) + 1:]))
                if rooted not in out:
                    out.append(rooted)
            return out
        if c.kind == "link":
            if t.startswith("/"):
                repo = self.inv.repo_of(c.doc)
                return [posixpath.normpath(posixpath.join(repo, t.lstrip("/")))]
            p = posixpath.normpath(posixpath.join(posixpath.dirname(c.doc), t))
            m = self._mirror_dir(c.doc)
            out = [p] if m is None else [p, posixpath.normpath(posixpath.join(m, t))]
            if t.lower().endswith((".md", ".markdown", ".mdx")):
                for site in self._docusaurus_sites:
                    if site and not c.doc.startswith(site + "/"):
                        continue
                    relative = c.doc[len(site):].lstrip("/")
                    match = re.match(
                        r"(docs|versioned_docs/[^/]+|i18n/[^/]+/docusaurus-plugin-content-docs/[^/]+)/",
                        relative)
                    if match:
                        root = posixpath.join(site, match.group(1))
                        fallback = posixpath.normpath(posixpath.join(root, t))
                        if fallback.startswith(root + "/") and fallback not in out:
                            out.append(fallback)
                    break
            return out
        out = []
        for b in self._bases(c):
            p = posixpath.normpath(posixpath.join(b, t)) if b else posixpath.normpath(t)
            if p not in out:
                out.append(p)
        return out

    @staticmethod
    def _is_lang(seg: str) -> bool:
        m = LANG_DIR.match(seg)
        return bool(m) and m.group(1).lower() in LANG_CODES

    def _lang_roots(self) -> dict:
        """{translated folder: source folder} for translation trees (a folder holding two or more
        language folders, like i18n/fr + i18n/ja). Learned from pages that exist on both sides."""
        if self._mirrors is not None:
            return self._mirrors
        self._mirrors = {}
        kids = defaultdict(list)
        for d in self.inv.dir_set:
            if self._is_lang(posixpath.basename(d)):
                kids[posixpath.dirname(d)].append(d)
        trees = [langs for langs in kids.values() if len(langs) >= 2]
        if not trees:
            return self._mirrors
        by_name = defaultdict(list)
        for d in self.inv.docs:
            by_name[posixpath.basename(d).lower()].append(d)
        for langs in trees:
            inside = tuple(x + "/" for x in langs)
            for lang in langs:
                votes = Counter()
                for d in self.inv.docs:
                    if not d.startswith(lang + "/"):
                        continue
                    segs = d[len(lang) + 1:].split("/")
                    best, best_n, tie = None, 0, False
                    for src in by_name.get(segs[-1].lower(), ()):
                        if src.startswith(inside):
                            continue
                        ss = src.split("/")
                        n = 0
                        while n < min(len(ss), len(segs)) and ss[-1 - n] == segs[-1 - n]:
                            n += 1
                        if n > best_n:
                            best, best_n, tie = src, n, False
                        elif n == best_n:
                            tie = True
                    if best and not tie:
                        ss = best.split("/")
                        votes["/".join([lang] + segs[: len(segs) - best_n]), "/".join(ss[: len(ss) - best_n])] += 1
                if votes:
                    (t_root, s_root), n = votes.most_common(1)[0]
                    if n >= 2:
                        self._mirrors[t_root] = s_root
        return self._mirrors

    def _mirror_dir(self, doc: str) -> str | None:
        """Where a translated page's links land when the page is missing in that language (the build
        falls back to the source page): i18n/fr/pages/x.md -> docs/."""
        roots = self._lang_roots()
        if not roots:
            return None
        ddir = posixpath.dirname(doc)
        for t_root, s_root in roots.items():
            if ddir == t_root or ddir.startswith(t_root + "/"):
                rest = ddir[len(t_root):].lstrip("/")
                return posixpath.join(s_root, rest) if s_root else rest
        return None

    def _exists(self, p: str, want_dir: bool = False) -> bool:
        if p in (".", ""):
            return True
        if not p.startswith("..") and (p in self.inv.file_set or p in self.inv.dir_set):
            return not want_dir or p in self.inv.dir_set
        full = self.inv.root / p
        try:
            return full.is_dir() if want_dir else full.exists()
        except OSError:
            return False

    def resolve(self, c: Claim) -> str | None:
        want_dir = bool(c.extra.get("dir"))
        for p in self._cands(c):
            if self._exists(p, want_dir):
                return p
        for alt in c.extra.get("alts") or ():     # an unquoted path with spaces, split by the shell
            probe = Claim(c.kind, alt, alt, c.doc, c.line, c.col, c.ctx, {"cwd": c.extra.get("cwd")})
            for p in self._cands(probe):
                if self._exists(p):
                    return p
        if c.kind != "link" and c.extra.get("anchor") not in ("root", "exact"):
            hit = self.paths.suffix(c.target, self._area(c.doc))
            if hit:
                return hit
            hit = self.paths.suffix(c.target)
            if hit:
                c.extra["far"] = True       # same name in another project: exists, but not checked further
                return hit
        return self._site_page(c) if c.kind == "link" else None

    def _site_page(self, c: Claim) -> str | None:
        """The file behind a link written for the built site: `../advanced/transports`, `guide/`, `page.html`,
        `/logo.png`. A site serves `page.md` at `page/`, so the link is read from the page's own folder first,
        then from the folder the site gives the page. A link from the site's root is matched by its ending:
        that root is some folder of the repo (`docs/`, `docs/public/`). The page and its headings can
        then be checked, though the link names no file of the repo."""
        raw = c.target.replace("\\", "/")
        t = self._site_address(raw)
        found: list = []
        if raw.startswith("/"):
            roots = {}
            for n in (self._page_names(t) if t else [raw.strip("/")]):
                for full in self.paths.by_name.get(n.rsplit("/", 1)[-1].casefold(), ()):
                    if n and (full == n or full.endswith("/" + n)) and full in self.inv.file_set:
                        roots.setdefault(full, full[:len(full) - len(n)])
            own = [f for f, r in roots.items() if c.doc.startswith(r)]      # the site this doc is a page of
            found = own or list(roots)
        elif t:
            name = posixpath.splitext(posixpath.basename(c.doc))[0].lower()
            for d in (posixpath.dirname(c.doc), self._mirror_dir(c.doc)):
                if d is None or found:
                    continue
                for b in ([d] if name in SITE_INDEX else [d, posixpath.join(d, name)]):
                    p = posixpath.normpath(posixpath.join(b, t))
                    if not p.startswith(".."):
                        found += [x for x in self._page_names(p) if x in self.inv.file_set and x not in found]
        if not found:
            return None
        if len(found) > 1:
            c.extra["far"] = True               # two pages fit: the link is fine, whose headings count is not known
        c.extra["site"] = True
        self._site_trees.add(self._tree(c.doc))
        return found[0]

    @staticmethod
    def _site_address(target: str) -> str:
        """`target` as a page address (`guide/intro`), or '' when it names a file (`guide/intro.png`)."""
        t = target.replace("\\", "/").strip("/")
        stem, ext = posixpath.splitext(t)
        if ext.lower() in (".html", ".htm"):
            t = stem
        elif ext:
            return ""
        return "" if posixpath.basename(t) in ("", ".", "..") else t

    @staticmethod
    def _page_names(p: str) -> list:
        out = [p + e for e in SITE_PAGE_EXT] + [f"{p}/{n}{e}" for n in ("index", "README", "_index")
                                                for e in SITE_PAGE_EXT]
        d, name = posixpath.split(p)
        if name.lower() == "index":         # `guide/index.html` is built from `guide/README.md` (mdBook, GitBook)
            out += [posixpath.join(d, n + e) for n in ("README", "_index") for e in SITE_PAGE_EXT]
        return out

    def _tree(self, doc: str) -> str:
        """The top folder a doc sits in, inside its own repo: one docs site lives in one such folder."""
        repo = self.inv.repo_of(doc)
        rest = doc[len(repo):].lstrip("/")
        return posixpath.join(repo, rest.split("/", 1)[0]) if "/" in rest else repo

    def modified(self) -> set:
        if self._modified is None:
            mod = set()
            for g in self.gits.values():
                mod |= g.modified_now()
            self._modified = mod
        return self._modified

    @staticmethod
    def _generated(c: Claim) -> bool:
        segs = c.target.replace("\\", "/").split("/")
        return any(s.lower() in GENERATED_DIRS for s in segs)

    # -- main ----------------------------------------------------------------
    def run(self, claims: list) -> list:
        by: dict[str, list] = defaultdict(list)
        for c in claims:
            by[c.kind].append(c)
            if c.kind == "link" and c.target:
                self._link_total[c.doc] += 1
        self._paths(by["path"] + by["command"] + by["link"])
        self._modules(by["module"])
        self._script_flags(by["command"] + by["module"])
        self._symbols(by["symbol"])
        self._global_flags(by["flag"])
        self._npm_make(by["npm"] + by["make"])
        self._decisions(by["decision"])
        self._versions(by["version"])
        self._deps(by["dep"])
        if not self.light:
            self._copies()
        self._tables()
        self._rules()
        return self.findings

    # -- paths, links, commands, trees ----------------------------------------
    def _reroot_trees(self, claims: list) -> None:
        """A tree drawn from the folder that holds the clone (`mytool/` on top, or `mytool/mytool/` for the
        clone and its package) names its entries from outside the repo. When most entries are missing under that
        top, history never had them there, and most exist with the top cut shorter, they are read from there.
        Entries that history had under the top (a `lib/` since flattened) keep their findings."""
        groups: dict = defaultdict(list)
        for c in claims:
            if c.ctx == "tree" and "top" in c.extra:
                groups[(c.doc, c.extra["top"])].append(c)
        for (doc, top), group in groups.items():
            kids = [c for c in group if c.extra["sub"]]

            def found(base: str) -> int:
                return sum(1 for c in kids if self._exists(posixpath.join(base, c.extra["sub"]), bool(c.extra.get("dir"))))

            if len(kids) < 2:
                continue
            score = found(top)
            if score * 2 >= len(kids):
                continue
            git = self.git_for(doc)
            hist = git.history() if git else None
            if hist is not None and hist.ok and any(hist.ever(c.target) for c in kids):
                continue
            ddir = posixpath.dirname(doc)
            segs = (top[len(ddir) + 1:] if ddir and top.startswith(ddir + "/") else top).split("/")
            best = None
            for k in range(1, len(segs) + 1):
                rest = "/".join(segs[k:])
                for b in dict.fromkeys([posixpath.join(ddir, rest).rstrip("/"), rest]):
                    n = found(b)
                    if n > score:
                        best, score = b, n
            if best is None or score * 2 < len(kids):
                continue
            for c in group:
                if c.extra["sub"]:
                    c.target = posixpath.join(best, c.extra["sub"])
                else:
                    c.status, c.where = "ok", best or "."       # the clone's own folder

    def _paths(self, claims: list) -> None:
        self._reroot_trees(claims)
        missing: list = []
        for c in claims:
            if c.ctx == "tree" and c.status == "ok":
                continue
            if c.kind == "link" and not c.target.startswith("/"):
                repo = self.inv.repo_of(c.doc)
                doc = c.doc[len(repo):].lstrip("/") if repo else c.doc
                target = posixpath.normpath(posixpath.join(posixpath.dirname(doc), c.target))
                if re.match(r"^(?:\.\./)+(?:issues|pulls|pull|wiki|discussions|releases|actions|security|compare|tags|milestones|projects|commits|blob|tree)(?:/|$)", target):
                    c.status = "external"
                    continue
            if c.kind != "link" and self._generated(c):
                c.status = "skipped"
                continue
            hit = self.resolve(c)
            if hit is not None:
                if c.kind == "link" and self._wrong_case(c, hit):
                    continue
                c.status, c.where = "ok", hit
                if c.kind == "link" and c.extra.get("anchor") and not c.extra.get("far"):
                    self._anchor(c, hit)
                continue
            if c.kind == "link" and not c.target:      # pure #anchor
                c.status, c.where = "ok", c.doc
                self._anchor(c, c.doc)
                continue
            if c.kind == "link" and any(self._wrong_case(c, p) for p in self._cands(c)):
                continue
            missing.append(c)
        by_git: dict = defaultdict(list)
        for c in missing:
            by_git[id(self.git_for(c.doc))].append(c)
        todo = []
        for group in by_git.values():
            git = self.git_for(group[0].doc)
            ignored = set()
            if git:
                allc = []
                for c in group:
                    allc += self._cands(c)
                ignored = git.ignored([p for p in allc if not p.startswith("..")])
            hist = git.history() if git else None
            if hist is not None and not hist.ok:
                hist = None
            need_blame = set()
            for c in group:
                if any(p in ignored for p in self._cands(c)) or self._ignored_folder(c):
                    c.status = "skipped"          # generated / runtime file
                    continue
                if c.kind != "link" and self.acknowledged(c):
                    c.status = "acknowledged"
                    continue
                ever = self._ever(hist, c) if hist else []
                if ever:
                    need_blame.add(c.doc)
                todo.append((c, git, hist, ever))
            if git and need_blame:
                git.prefetch_blame(sorted(need_blame))
        for c, git, hist, ever in todo:
            self._missing_path(c, git, hist, ever)
        self._flush_links()

    def _ignored_folder(self, c: Claim) -> bool:
        """A folder that a folder-only pattern (`tests/output/`) ignores. git cannot tell for a folder that is
        not there, and asking it with the slash is no cure: on a .gitignore saved with CRLF the `\\r` of a blank
        line matches every such path."""
        return bool(c.extra.get("dir") or c.target.endswith("/")) and any(
            self._ignored_path(p, True) for p in self._cands(c) if not p.startswith(".."))

    def _work_queue(self, hist, path: str) -> bool:
        """The path is, or lies in, a folder of work items (`openspec/changes/<id>/`): an item waits there while
        in progress and leaves when done, and git keeps no empty folder, so the folder is gone whenever nothing is
        in progress. Told apart from a folder dropped, moved or emptied in a commit or two, and from code that
        moved bit by bit: items left in at least three commits, new items kept arriving after the first one had
        left, and most files there were written text."""
        d = path.rstrip("/")
        while d:
            if d not in self._queues:
                queue = False
                files = hist.under.get(d, ())
                if d not in self.inv.dir_set and files and 2 * sum(
                        1 for f in files if f.lower().endswith(QUEUE_TEXT)) >= len(files):
                    arrived: dict = {}          # item -> position of its first add (larger is older)
                    left: dict = {}             # item -> position of its last delete
                    for f in hist.under[d]:
                        item = f[len(d) + 1:].split("/", 1)[0]
                        for pos, kind, _ in hist.events[f]:
                            if kind == "A":
                                arrived[item] = max(arrived.get(item, pos), pos)
                            elif kind == "D":
                                left[item] = min(left.get(item, pos), pos)
                    queue = len(set(left.values())) >= 3 and sum(
                        1 for pos in arrived.values() if pos < max(left.values())) >= 2
                self._queues[d] = queue
            if self._queues[d]:
                return True
            d = posixpath.dirname(d)
        return False

    def _other_project(self, doc: str) -> bool:
        """The doc, or the skill it belongs to, has the reader clone another project and enter it (`git clone
        …/torchtitan`, `cd torchtitan`): the scripts its commands name are that project's. Entering a clone of
        this very repo is no such move."""
        root = posixpath.dirname(doc)
        while root and f"{root}/SKILL.md" not in self.inv.file_set:
            root = posixpath.dirname(root)
        key = root or doc
        if key not in self._other_projects:
            if self._own_names is None:
                self._own_names = {self.inv.root.name.lower()}
                for git in self.gits.values():
                    url = git._git(["config", "--get", "remote.origin.url"], timeout=20) or b""
                    name = url.decode("utf-8", "replace").strip().rstrip("/").rsplit("/", 1)[-1]
                    self._own_names.add(name.rsplit(":", 1)[-1].removesuffix(".git").lower())
            elsewhere = False
            for p in ([p for p in self.inv.docs if p.startswith(root + "/")] if root else [doc]):
                d = self.docs.get(p)
                if d is None and self.load_doc is not None:
                    d = self.load_doc(p)
                if d is not None and any(posixpath.basename(e).lower() not in self._own_names for e in d.entered):
                    elsewhere = True
                    break
            self._other_projects[key] = elsewhere
        return self._other_projects[key]

    def _anchor(self, c: Claim, target: str) -> None:
        anchor = c.extra.get("anchor", "")
        if not anchor or not target.lower().endswith((".md", ".markdown", ".mdx")):
            return
        d = self.docs.get(target)
        if d is None and self.load_doc is not None:
            d = self.load_doc(target)
            if d is not None:
                self.docs[target] = d
        if d is None:
            return
        from urllib.parse import unquote
        a = unquote(anchor)
        if a in d.anchors or re.match(r"^L\d+(-L\d+)?$", a):        # the second: GitHub line anchors
            return
        have = self._skeletons.get(target)
        if have is None:
            have = set()
            pending = [d]
            seen = set()
            while pending:
                page = pending.pop()
                if page.path in seen:
                    continue
                seen.add(page.path)
                have.update(skeleton(value) for value in page.anchors)
                for imported in page.imports:
                    if imported.startswith(("../", "/")) or imported in seen:
                        continue
                    partial = self.docs.get(imported)
                    if partial is None and self.load_doc is not None:
                        partial = self.load_doc(imported)
                        if partial is not None:
                            self.docs[imported] = partial
                    if partial is not None:
                        pending.append(partial)
            self._skeletons[target] = have
        want = {skeleton(a), skeleton(re.sub(r"-\d+$", "", a))}
        if want & have:
            return          # every site names headings its own way, and numbers the repeats
        gone = self._heading_gone(target, want)
        if gone:
            self.add("anchor-missing", WARNING, c, anchor=a, target=target, evidence=[{
                "kind": "git", "rev": gone["sha"][:10], "date": gone["date"], "path": target,
                "note": f"the heading `{gone['text']}` was removed by this commit: {gone['subject']}"}])
            return
        if c.extra.get("site") or re.search(r"[.:/]", a):
            self.add("anchor-unverified", INFO, c, anchor=a, target=target)     # an id only the built site has
            return
        self.add("anchor-missing", WARNING, c, anchor=a, target=target)

    def _heading_gone(self, target: str, want: set) -> dict | None:
        """The commit that took the heading behind an anchor out of the page: proof that the link once worked."""
        git = self.git_for(target)
        if git is None:
            return None
        for item in git.headings_removed(target):
            if not want & {skeleton(x) for x in scan(target, "## " + item["text"]).anchors}:
                continue
            before, after = git.show(item["sha"] + "^", target), git.show(item["sha"], target)
            if before is None or after is None:
                continue        # the page came or went with that commit: its headings may have moved with it
            if want & {skeleton(x) for x in scan(target, before).anchors} \
                    and not want & {skeleton(x) for x in scan(target, after).anchors}:
                return item
        return None

    def _area(self, doc: str) -> str:
        """Where a bare file name is looked for in the past: the doc's project folder."""
        parts = posixpath.dirname(doc).split("/")
        return "/".join(parts[:2]) if parts and parts[0] else ""

    def _ever(self, hist, c: Claim) -> list:
        """Candidate paths that the repo had at some point."""
        out = [p for p in self._cands(c) if hist.ever(p)]
        if c.kind != "link" and c.extra.get("anchor") not in ("root", "exact"):
            t = c.target.strip("/").casefold()
            name = t.rsplit("/", 1)[-1]
            area = ""
            if "/" not in t:
                if kind_of(name) not in ("code", "doc"):
                    return out          # bare data names (out.json, voice.wav) are runtime files
                area = self._area(c.doc)
            tails = []
            for p in sorted(hist.names.get(name, ())):
                pf = p.casefold()
                if (pf == t or pf.endswith("/" + t)) and p not in out:
                    if area and not p.startswith(area + "/"):
                        continue
                    tails.append(p)
            if "/" in t:
                # `docs/guide.md` in a page under `website/src/next/docs/` is read from that `docs` folder:
                # the `website/src/latest/docs/guide.md` of another version is not what it names
                first = t.split("/", 1)[0]
                d = posixpath.dirname(c.doc).casefold()
                while d:
                    if posixpath.basename(d) == first:
                        tails = [p for p in tails if p.casefold().startswith(d + "/")]
                        break
                    d = posixpath.dirname(d)
            # found by its ending only: weak proof (see _pick), and none at all for a common name
            if name not in COMMON_NAMES:
                c.extra["tails"] = set(tails[:20])
                out += tails
        return out[:20]

    @staticmethod
    def _pick(c: Claim, live: list) -> str | None:
        """Which of the paths that existed the line meant. One found only by its ending
        (`pkg/build.py` for `src/pkg/build.py`) counts when nothing else ends that way: the
        `app/server.py` of a tutorial is not the `app/server.py` an unrelated folder once had."""
        tails = c.extra.get("tails") or ()
        exact = [x for x in live if x not in tails]
        if exact:
            return exact[0]
        return live[0] if len(live) == 1 else None

    def _missing_path(self, c: Claim, git: Git | None, hist, ever: list) -> None:
        if c.kind != "link" and FOR_READER.search(self.sentence(c)):
            c.status = "unverified"
            return
        if hist is not None and hist.ok and any(self._work_queue(hist, p) for p in ever):
            c.status = "skipped"            # empty while no work is in progress
            return
        if not ever:
            if c.kind == "command" and self._other_project(c.doc):
                c.status = "unverified"     # a script of the project the reader cloned; one this repo had stays
                return
            self._never(c)
            return
        rule = {"link": "link-broken", "command": "command-missing"}.get(c.kind, "path-moved")
        rev, epoch = git.written_at(c.doc, c.line)
        if rev is None:
            hit = self._pick(c, self._there(git, "HEAD", ever))
            if hit:
                self.add("path-removed-now", ERROR, c,
                         evidence=[{"kind": "git", "rev": "HEAD", "path": hit,
                                    "note": "committed, removed in the working tree"}])
                return
            self._gone_before(c, git, hist, ever)
            return
        hit = self._pick(c, self._there(git, rev, ever))
        if hit is None:
            self._gone_before(c, git, hist, ever)
            return
        ev = [{"kind": "git", "rev": rev[:10], "date": day(epoch), "path": hit,
               "note": "existed when the line was written"}]
        fol = hist.gone(hit, hist.position(rev, epoch))
        if fol and not git.is_ancestor(rev, fol["sha"]):
            fol = None          # a delete on another line of history: not what happened to the path this line names
        # a line that names where it went ("move `a` to `b/`") describes the move: a record, not an error
        sev = INFO if c.kind != "link" and self._names_target(c, fol) else ERROR
        sug = self._follow_text(fol, ev, hit)
        self.add(rule, sev, c, evidence=ev, suggestion=sug, when=day(epoch))

    @staticmethod
    def _there(git: Git, rev: str, paths: list) -> list:
        """The paths the commit itself had, in the order given. The history index is fast but reads the log
        as one line; only the tree of the commit proves what was there (see Git.in_tree)."""
        have = git.in_tree(rev, paths)
        return [x for x in paths if x in have]

    def _names_target(self, c: Claim, fol: dict | None) -> bool:
        """The line also names where the path went, or that place's folder ("move `a` to `b/`")."""
        to = ((fol or {}).get("to") or "").casefold().rstrip("/")
        if not to:
            return False
        d = self.docs.get(c.doc)
        line = (d.line_text(c.line) if d is not None else "").replace("\\", "/").casefold()
        line = line.replace(c.text.replace("\\", "/").casefold(), " ")
        for tok in PATHISH.findall(line):
            tok = tok.strip("./")
            if "/" in tok and (to == tok or to.endswith("/" + tok) or to.startswith(tok + "/")):
                return True
        return False

    def _gone_before(self, c: Claim, git: Git, hist, ever: list) -> None:
        """The repo had it, but not when this line was written (removed earlier, or added later and removed)."""
        tails = c.extra.get("tails") or ()
        for x in ever:
            # known by its ending only, and not even there when the line was written: no proof
            seen = None if x in tails else hist.last_seen(x)
            if seen is None:
                continue
            if c.kind != "link":
                # a bare name in a doc that does not sit where the file was: `yarn.lock` in a guide, rewritten
                # after this repo dropped its own, is the lock file of the reader's project
                if "/" not in c.target.replace("\\", "/").strip("/") and posixpath.dirname(x) != posixpath.dirname(c.doc):
                    continue
                # the doc must have named it while it was there; a guide written later that says
                # `config/_default` is about the reader's project, not about a folder this repo once had
                then = git.show(hist.commits[seen][0], c.doc)
                if then is None or not (c.target in then or c.text in then):
                    continue
            ev = [{"kind": "git", "rev": hist.commits[seen][0], "date": day(hist.commits[seen][1]),
                   "path": x, "note": "last seen here"}]
            fol = hist.gone(x, seen)
            sug = self._follow_text(fol, ev, x)
            sev = ERROR if c.kind == "link" else INFO if self._names_target(c, fol) else WARNING
            self.add("link-broken" if c.kind == "link" else "path-gone", sev, c, evidence=ev, suggestion=sug)
            return
        self._never(c, missing=False)

    def _follow_text(self, fol: dict | None, ev: list, path: str) -> str:
        if not fol:
            return ""
        ev.append({"kind": "git", "rev": fol["sha"], "date": fol["date"], "path": fol.get("to") or path,
                   "note": "deleted" if fol.get("deleted") else "renamed"})
        if fol.get("deleted"):
            return (f"deleted in {fol['sha']} ({fol['date']})" if self.lang != "vi"
                    else f"đã xóa ở commit {fol['sha']} ({fol['date']})")
        to = fol.get("to")
        if to and self._exists(to):
            return (f"moved to `{to}` in {fol['sha']} ({fol['date']})" if self.lang != "vi"
                    else f"đã dời sang `{to}` ở commit {fol['sha']} ({fol['date']})")
        return (f"renamed to `{to}` in {fol['sha']} ({fol['date']}), later removed too" if self.lang != "vi"
                else f"đã đổi thành `{to}` ở commit {fol['sha']} ({fol['date']}), sau đó cũng bị xóa")

    def _never(self, c: Claim, *, missing: bool = True) -> None:
        """Never in the repo: report links, typos and clear commands; the rest is unverified."""
        if c.kind == "link":
            self._never_links[c.doc].append(c)
            return
        near = self._near(c)
        if near and not (c.kind == "path" and self._in_code_strings(c.target.replace("\\", "/").rstrip("/"))):
            # `vite.config.js` written as a key of a project template in the code is the file it makes
            self.add("path-typo", WARNING, c, near=near,
                     suggestion=(f"did you mean `{near}`?" if self.lang != "vi" else f"có phải `{near}`?"))
            return
        if c.kind == "command" and "/" in c.target.strip("/") and self.kind(c.doc) == "live" \
                and not c.extra.get("alts"):
            for p in self._cands(c):
                parent = posixpath.dirname(p)
                if parent and not parent.startswith("..") and parent in self.inv.dir_set:
                    self.add("command-missing", WARNING, c)
                    return
        if missing and c.kind == "path" and self._path_missing(c):
            # Measured on 14 small repos built with agents: 1 of 21 was real elsewhere (other repos,
            # examples, branch names); an agent's own instruction file is where a made-up path does harm.
            self.add("path-missing", WARNING if _agent_doc(c.doc) else INFO, c)
            return
        c.status = "unverified"

    def _ignored_path(self, path: str, want_dir: bool = False, holder: bool = False) -> bool:
        parts = path.split("/")
        rules = []
        for depth in range(len(parts)):
            directory = "/".join(parts[:depth])
            if directory not in self._ignore_rules:
                ignore = posixpath.join(directory, ".gitignore")
                text = self.inv.text(ignore) if not is_private(ignore) else None
                self._ignore_rules[directory] = [line.rstrip() for line in (text or "").splitlines()
                                                 if line.strip() and not line.startswith("#")]
            rules.extend((directory, rule) for rule in self._ignore_rules[directory])
            candidate = "/".join(parts[:depth + 1])
            ignored = False
            for base, rule in rules:
                negate = rule.startswith("!")
                pattern = rule[1:] if negate else rule
                relative = candidate[len(base) + 1:] if base else candidate
                folder = depth < len(parts) - 1 or want_dir
                if pattern.endswith("/") and not folder:
                    continue
                if pattern and match_any(relative + "/" if folder else relative, [pattern]):
                    ignored = not negate
                elif (holder and want_dir and depth == len(parts) - 1 and not negate and "/" in pattern.strip("/")
                        and pattern.strip("/").lower().startswith(relative.lower() + "/")
                        and not re.search(r"[*?[]", relative)):
                    ignored = True      # `/src/generated/prisma` ignored: `src/generated/` is the build's folder
            if ignored:
                return True
        return False

    def _path_missing(self, c: Claim) -> bool:
        target = c.target.replace("\\", "/")
        directory = posixpath.dirname(c.doc)
        tree_base = directory if c.ctx == "tree" and directory and target.startswith(directory + "/") else ""
        referenced = target[len(tree_base) + 1:] if tree_base else target
        parts = referenced.strip("/").split("/")
        if (self.kind(c.doc) != "live" or len(parts) < 2 or target.startswith(("/", "~"))
                or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", target)
                or has_placeholder(target) or "[" in target or is_private(target)
                or any(part.lower().startswith(("your-", "my-")) for part in parts)
                or any(part.lower() in GENERATED_DIRS | {"build", "out", "target", ".git"} for part in parts)
                or self._past(c) or self._retired_page(c.doc)):
            return False
        sentence = self.sentence(c)
        before = sentence.split(c.text, 1)[0] if c.text in sentence else sentence
        if re.search(r"\b(?:for example|example|usually|typically)\b|\be\.g\.", before, re.I):
            return False
        if re.search(r"\b(?:you|we)\s+(?:can|could|should|may|might|must|need to|have to|will)\s+(?:also\s+)?(?:customize|configure|define|implement|set up)\b", before, re.I):
            return False
        after = sentence.split(c.text, 1)[1] if c.text in sentence else ""
        if (re.search(r"\b(?:no (?:such )?(?:file|folder|directory|path)|không (?:có|tồn tại)|tidak (?:ada|memiliki))\b[^.!?;\n]{0,60}$", before, re.I)
                or re.match(r'''^[\s`"']*(?:does not|doesn't|do not|don't|is not|isn't) exist\b''', after, re.I)):
            return False
        if re.search(r"\b(?:denyWrite|denyRead|allowWrite|allowRead|denylist|allowlist|denied individually|deny list|allow list)\b", sentence, re.I):
            return False
        if re.search(r"\bif\s+(?:the\s+)?(?:repo(?:sitory)?|project|app|you)\b[^\n]*\b(?:has|have|uses?|contains?|includes?)\b", before, re.I):
            return False
        doc = self.docs.get(c.doc)
        if doc is not None:
            from urllib.parse import unquote, urlsplit
            context = " ".join(doc.line_text(line) for line in range(max(1, c.line - 12), c.line + 1))
            for url in re.findall(r'''https?://[^\s<>()[\]"'`]+''', context, re.I):
                try:
                    remote = unquote(urlsplit(url.rstrip(".,;")).path)
                except ValueError:
                    continue
                if remote.endswith("/" + target.lstrip("./")):
                    return False
        if re.search(r"\b(?:create|add|new|generate|will|should\s+create|tạo|thêm|sinh\s+ra|sẽ)\b[^.!?;\n]{0,60}$", before, re.I):
            return False
        if re.search(r"\b(?:build|compil\w*|generat\w*|render\w*)\b[^\n]*\b(?:moves?|copies?|writes?|outputs?|emits?)\b[^\n]*\bto\s*`?\s*$", before, re.I):
            return False
        candidates = self._cands(c)
        if any(self._ignored_path(path, bool(c.extra.get("dir") or target.endswith("/")), holder=True)
               for path in candidates if not path.startswith("..")):
            return False
        first = next((part for part in parts if part not in (".", "..")), "")
        if not first:
            return False
        first_path = posixpath.join(tree_base, first) if tree_base else first
        probe = Claim("path", first, first_path, c.doc, c.line, c.col, c.ctx, c.extra.copy())
        if not any(not path.startswith("..") and self._exists(path, True) for path in self._cands(probe)):
            return False
        return not self._in_code_strings(target)

    def _in_code_strings(self, target: str) -> bool:
        """The path, or its file name, is written as a string in the code: a file the code makes or names."""
        if self._path_strings is None:
            self._path_strings = set()
            for source in self.index.files:
                text = self.inv.text(source) or ""
                for match in re.finditer(r'''(["'`])((?:\\.|(?!\1)[^\\\r\n])*)\1''', text):
                    self._path_strings.update(path_literals(match.group(2)))
        return bool({posixpath.normpath(target), posixpath.basename(target)} & self._path_strings)

    def _near(self, c: Claim) -> str | None:
        """A sibling whose name differs by a typo (not a variant like `x_v2` next to `x`)."""
        name = c.target.rstrip("/").rsplit("/", 1)[-1]
        if len(name) < 5:
            return None
        want_dir = c.target.endswith("/") or bool(c.extra.get("dir"))
        stem = name.rsplit(".", 1)[0].casefold() if "." in name[1:] else name.casefold()
        for p in self._cands(c)[:6]:
            parent = posixpath.dirname(p)
            if parent.startswith("..") or (parent and parent not in self.inv.dir_set):
                continue
            sibs = self.paths.children.get(parent, ())
            for best in difflib.get_close_matches(name, sibs, n=3, cutoff=0.84):
                full = posixpath.join(parent, best) if parent else best
                if (full in self.inv.dir_set) != want_dir:
                    continue        # a folder is not a typo of a file
                if re.sub(r"\d", "", best) == re.sub(r"\d", "", name):
                    continue        # numbered variants (v1/v2, part-1/part-2) are not typos
                if name.startswith(".") and best == "_" + name[1:]:
                    continue        # a project template stores `.gitignore` as `_gitignore`
                bstem = best.rsplit(".", 1)[0].casefold() if "." in best[1:] else best.casefold()
                if bstem in stem or stem in bstem:
                    continue        # `x_v2` next to `x`: a planned or retired variant
                if best.casefold() == name.casefold() and self._exists(p):
                    continue
                return full
        return None

    def _flush_links(self) -> None:
        for doc, links in self._never_links.items():
            total = self._link_total.get(doc, len(links))
            if self._tree(doc) in self._site_trees:
                site = [c for c in links if self._site_address(c.target) or c.target.startswith("/")]
                if site:        # a site also makes pages of its own: an API reference, a blog, a glossary
                    self.add("link-unverified", INFO, None, path=doc, line=site[0].line, col=site[0].col,
                             claim=site[0].text if len(site) == 1 else f"{len(site)} links", count=len(site),
                             sample=", ".join(f"`{c.text}`" for c in site[:3]) + (", ..." if len(site) > 3 else ""),
                             evidence=[{"kind": "doc", "path": doc, "line": c.line, "text": c.text} for c in site[:5]])
                    for c in site:
                        c.status = "external"
                    ids = {id(c) for c in site}
                    links = [c for c in links if id(c) not in ids]
            if len(links) >= 3 and len(links) * 2 >= total:
                self.add("foreign-links", INFO, None, path=doc, line=links[0].line,
                         claim=f"{len(links)}/{total} links", broken=len(links), total=total,
                         evidence=[{"kind": "doc", "path": doc, "line": c.line, "text": c.text} for c in links[:5]])
                for c in links:
                    c.status = "external"
                continue
            for c in links:
                self.add("link-broken", INFO if self.acknowledged(c) else ERROR, c, suggestion=self._elsewhere(c))
        self._never_links.clear()

    def _elsewhere(self, c: Claim) -> str:
        """The one place where the target of a broken link does exist (a README copied out of `docs/`)."""
        t = posixpath.normpath(c.target.replace("\\", "/"))
        while t.startswith("../"):
            t = t[3:]
        t = t.strip("/")
        name = t.rsplit("/", 1)[-1].casefold()
        if t in ("", ".", "..") or name in COMMON_NAMES:
            return ""
        tf = t.casefold()
        hits = [p for p in self.paths.by_name.get(name, ()) if p.casefold() == tf or p.casefold().endswith("/" + tf)]
        if len(hits) != 1:
            return ""
        link = posixpath.relpath(hits[0], posixpath.dirname(c.doc) or ".")     # as the link must be written
        return f"did you mean `{link}`?" if self.lang != "vi" else f"có phải `{link}`?"

    def _wrong_case(self, c: Claim, p: str) -> bool:
        """A link whose target differs from the real path by letter case only. It opens on Windows and
        macOS and is dead on GitHub and Linux, so every system reports it, and reports it the same way."""
        if not p or p == "." or p.startswith("..") or self.inv.exists(p) or is_private(p):
            return False
        if self._spell is None:
            self._spell = {x.casefold(): x for x in self.inv.dir_set}
            self._spell.update((x.casefold(), x) for x in self.inv.file_set)
        real = self._spell.get(p.casefold()) or self._on_disk(p)    # git's spelling first: that is what GitHub serves
        if not real or real == p:
            return False
        fix = self._respell(c.target, real)
        if c.extra.get("anchor"):
            fix += "#" + c.extra["anchor"]
        self.add("link-case", INFO if self.acknowledged(c) else WARNING, c, real=real,
                 suggestion=f"write `{fix}`" if self.lang != "vi" else f"sửa thành `{fix}`")
        if c.status != "broken":
            c.status = "ok"         # reported as a note only (a plan, a line about the past)
        return True

    def _on_disk(self, p: str) -> str | None:
        """`p` as the disk spells it, matching each part without regard to case (for files the
        inventory does not list). Only folder listings are read, never a file."""
        cur, real = str(self.inv.root), []
        for seg in p.split("/"):
            names = self._listings.get(cur)
            if names is None:
                try:
                    names = os.listdir(cur)
                except OSError:
                    names = []
                self._listings[cur] = names
            if seg not in names:
                fold = seg.casefold()
                seg = next((n for n in names if n.casefold() == fold), None)
                if seg is None:
                    return None
            real.append(seg)
            cur = os.path.join(cur, seg)
        return "/".join(real)

    @staticmethod
    def _respell(target: str, real: str) -> str:
        """`target` with the spelling of `real`, keeping the way it starts (`./`, `../`, `/`)."""
        m = re.match(r"^((?:\.{1,2}/)*|/)(.*)$", target.replace("\\", "/"))
        head, tail = m.group(1), m.group(2).rstrip("/")
        segs = tail.split("/")
        if not tail or any(s in (".", "..") for s in segs):
            return real
        return head + "/".join(real.split("/")[-len(segs):])

    # -- python modules run with -m -------------------------------------------
    def _modules(self, claims: list) -> None:
        for c in claims:
            mod = c.target.replace(".", "/")
            variants = (mod + ".py", mod + "/__main__.py", mod + "/__init__.py",
                        "src/" + mod + ".py", "src/" + mod + "/__main__.py")
            found = None
            for variant in variants:
                probe = Claim("path", variant, variant, c.doc, c.line, c.col, c.ctx, {"cwd": c.extra.get("cwd")})
                hit = self.resolve(probe)
                if hit:
                    found = hit
                    break
            if found:
                c.status, c.where = "ok", found
                continue
            top = c.target.split(".")[0]
            if top in self.external or self.acknowledged(c):
                c.status = "external"
                continue
            git = self.git_for(c.doc)
            hist = git.history() if git else None
            if hist is None or not hist.ok:
                c.status = "unverified"
                continue
            rev, epoch = git.written_at(c.doc, c.line)
            existed = None
            for v in variants[:3]:
                had = sorted(path for path in hist.names.get(v.rsplit("/", 1)[-1].casefold(), ()) if path.endswith(v))
                existed = next(iter(self._there(git, rev or "HEAD", had[:20])), None)
                if existed:
                    break
            if existed:
                self.add("command-missing", ERROR, c, claim=c.target,
                         evidence=[{"kind": "git", "rev": rev[:10] if rev else "HEAD", "date": day(epoch),
                                    "path": existed}])
            else:
                c.status = "external"

    # -- flags and subcommands of the repo's own scripts ----------------------
    def _script_scope(self, script: str) -> list:
        d = posixpath.dirname(script)
        name = posixpath.basename(script)
        files = [script]
        if name in ("__main__.py", "__init__.py"):
            pre = d + "/" if d else ""
            files += [f for f in self.inv.code if f.startswith(pre) and f.endswith(".py")][:200]
        else:
            files += [f for f in self.inv.code if posixpath.dirname(f) == d and f.endswith(".py")][:100]
            pkg = posixpath.join(d, posixpath.splitext(name)[0])
            files += [f for f in self.inv.code if f.startswith(pkg + "/") and f.endswith(".py")][:200]
        return list(dict.fromkeys(files))

    def _script_flags(self, claims: list) -> None:
        texts: dict[str, str] = {}
        for c in claims:
            if c.status != "ok" or not c.where or not c.where.endswith((".py", ".pyw")) or c.extra.get("far"):
                continue
            flags = c.extra.get("flags") or []
            first = c.extra.get("first_arg")
            if not flags and not first:
                continue
            if c.kind != "module" and not self._script_is_here(c):
                continue        # a bare `main.py` far from the doc is the reader's own script
            if c.where not in texts:
                texts[c.where] = "\n".join(self.inv.text(f) or "" for f in self._script_scope(c.where))
            text = texts[c.where]
            if not text:
                continue
            parses = re.search(r"argparse|click|typer|optparse|sys\.argv|getopt|fire", text)
            # typer, fire, getopt and docopt name an option without writing `--name` anywhere
            implicit = re.search(r"\b(?:typer|fire|getopt|docopt)\b", text)
            missing = []
            for flag in flags:
                pat = r"(?<![\w-])" + re.escape(flag) + r"(?![\w-])"
                if not re.search(pat, text) and flag not in ("--help", "--version") and parses:
                    plain = "|".join(sorted({re.escape(flag[2:]), re.escape(flag[2:].replace("-", "_"))}))
                    if implicit and re.search(r"(?<![\w-])(?:" + plain + r")(?![\w-])", text):
                        continue
                    missing.append((flag, pat))
            if not missing and not first:
                continue
            if self.acknowledged(c):
                continue
            git = self.git_for(c.doc)
            past: dict = {}

            def old_text():
                """The script as it was when the doc line was written (asked only when needed)."""
                if "text" not in past:
                    rev, epoch = (git.written_at(c.doc, c.line) if git else (None, None))
                    past["rev"], past["epoch"] = rev, epoch
                    past["text"] = git.show(rev, c.where) if (git and rev) else None
                return past["text"]

            for flag, pat in missing:
                old = old_text()
                if old and re.search(pat, old):
                    rev, epoch = past["rev"], past["epoch"]
                    self.add("flag-removed", WARNING, c, flag=flag, script=c.where, when=day(epoch),
                             evidence=[{"kind": "git", "rev": rev[:10], "date": day(epoch), "path": c.where}]
                             + self._removed_by(git, rev, c.where, flag))
                else:
                    self.add("flag-missing", WARNING, c, flag=flag, script=c.where)
            if first:
                self._subcommand(c, first, text, old_text, past)

    def _script_is_here(self, c: Claim) -> bool:
        """`python main.py --name x` in a tutorial runs the reader's script. A bare file name is
        ours only when it sits where the command would run: next to the doc, in the `cd`
        folder, or at the root of the doc's project or repo."""
        t = c.target.replace("\\", "/")
        while t.startswith("./"):
            t = t[2:]
        if "/" in t:
            return True
        ddir = posixpath.dirname(c.doc)
        here = {ddir, self.inv.repo_of(c.doc).rstrip("/"), self._area(c.doc)}
        cwd = c.extra.get("cwd")
        if cwd:
            here |= {posixpath.normpath(posixpath.join(ddir, cwd)), posixpath.normpath(cwd)}
        return posixpath.dirname(c.where) in here

    def _subcommand(self, c: Claim, first: str, scope_text: str, old_text, past: dict) -> None:
        """Report a missing subcommand only with proof: it was in the script when
        the line was written, or it is a near-typo of a real one. Subcommands
        are often registered in loops, so a static list alone proves nothing."""
        package = c.kind == "module" or c.where.endswith(("__main__.py", "__init__.py"))
        own = scope_text if package else (self.inv.text(c.where) or "")
        subs = set()
        for m in SUBCOMMAND_DEF.finditer(own):
            name = m.group(1) or m.group(2) or (m.group(3) or "").replace("_", "-")
            if name:
                subs.add(name)
        if len(subs) < 2 or first in subs or first.replace("_", "-") in subs:
            return
        quoted = r"[\"']" + re.escape(first) + r"[\"']"
        if re.search(quoted, scope_text):
            return              # registered some other way (a loop, a dict)
        old = old_text()
        if old and re.search(quoted, old):
            rev, epoch = past["rev"], past["epoch"]
            self.add("subcommand-missing", WARNING, c, name=first, script=c.where,
                     evidence=[{"kind": "git", "rev": rev[:10], "date": day(epoch), "path": c.where,
                                "note": f"`{first}` was a subcommand when the line was written"}],
                     suggestion=", ".join(sorted(subs)[:8]))
            return
        near = difflib.get_close_matches(first, sorted(subs), n=1, cutoff=0.75)
        if near:
            self.add("subcommand-missing", WARNING, c, name=first, script=c.where,
                     suggestion=(f"did you mean `{near[0]}`?" if self.lang != "vi" else f"có phải `{near[0]}`?"))

    # -- identifiers -----------------------------------------------------------
    def _symbols(self, claims: list) -> None:
        pending = []
        for c in claims:
            parts = c.extra.get("parts") or [c.target]
            if parts[0] in self.external and len(parts) > 1:
                c.status = "external"
                continue
            mod = c.extra.get("from")           # `from pkg.mod import Name` in an example
            if mod and not self._repo_module(mod):
                c.status = "external"
                continue
            missing = [p for p in parts if not self.index.has(p)]
            built = [self.index.built(p) for p in missing]
            if all(built):          # the code builds them from a format string: `f"time_{n}_{field}"`
                missing = []
            if not missing:
                c.status = "ok"
                w = self.index.defs.get(c.target)
                if w:
                    c.where = f"{w[0][0]}:{w[0][1]}"
                elif built:
                    c.where = built[0]
                continue
            if self.acknowledged(c):
                c.status = "acknowledged"
                continue
            if all(p in self._example_names(c.doc) for p in missing):
                c.status = "external"       # `isActive` of the page's own example (`const isActive = ref(true)`)
                continue
            c.extra["missing"] = missing
            pending.append(c)
        self._time_travel_names(pending, "symbol")

    def _example_names(self, doc: str) -> set:
        """Names the doc's own code blocks declare: the example's, not the repo's."""
        names = self._examples.get(doc)
        if names is None:
            d = self.docs.get(doc)
            names = set()
            for f in (d.fences if d is not None else ()):
                for _, text in f.lines:
                    names.update(m.group(1) or m.group(2) for m in EXAMPLE_DECL.finditer(text))
            self._examples[doc] = names
        return names

    def _translated(self, doc: str) -> bool:
        """A translation (`docs/ko/guide/x.md` next to `docs/en/`, `README-ja.md`): its drift is the source page's,
        found and warned there; translators catch up after."""
        m = TRANSLATED_NAME.search(posixpath.basename(doc))
        if m and m.group(1).lower() in LANG_CODES and m.group(1).lower() != "en":
            return True
        segs = doc.split("/")[:-1]
        for i, seg in enumerate(segs):
            if self._is_lang(seg) and seg[:2].lower() != "en":
                parent = "/".join(segs[:i])
                pre = parent + "/" if parent else ""
                langs = {d for d in self.inv.dir_set if d.startswith(pre) and "/" not in d[len(pre):]
                         and self._is_lang(d[len(pre):])}
                if len(langs) >= 2:
                    return True
        return False

    def _retired_page(self, doc: str) -> bool:
        """The page opens by saying its subject was removed or deprecated ("has been removed in 3.4"):
        what it names from the old code is its record of the feature."""
        hit = self._retired.get(doc)
        if hit is None:
            d = self.docs.get(doc)
            lead = []
            for n in range(1, min(len(d.lines), 25) + 1) if d is not None else ():
                text = d.line_text(n)
                if n > 1 and re.match(r"^\s{0,3}#{2,6}\s", text):
                    break
                lead.append(text)
            hit = self._retired[doc] = bool(RETIRED_PAGE.search(" ".join(lead)))
        return hit

    def _repo_module(self, mod: str) -> bool:
        rel = mod.replace(".", "/")
        return any(self.paths.suffix(rel + ext) for ext in (".py", ".pyi", "/__init__.py"))

    def _global_flags(self, claims: list) -> None:
        pending = []
        for c in claims:
            name = c.target[2:] if c.target.startswith("--") else ""
            # a flag library builds `--name` from a plain "name" (Go's pflag, clap, getopt_long) or from a
            # field `dry_run` (clap derive, typer): the flag is there though no `--name` is written
            if c.target in self.index.dashed or name in self.index.spelled \
                    or ("-" in name and self.index.has(name.replace("-", "_"))):
                c.status = "ok"
                continue
            if self.acknowledged(c):
                c.status = "acknowledged"
                continue
            c.extra["missing"] = [c.target]
            pending.append(c)
        self._time_travel_names(pending, "flag")

    def _time_travel_names(self, pending: list, what: str) -> None:
        by_git: dict = defaultdict(list)
        for c in pending:
            git = self.git_for(c.doc)
            if git is None:
                c.status = "unverified"
                continue
            by_git[id(git)].append((c, git))
        groups: dict = defaultdict(list)
        for items in by_git.values():
            git = items[0][1]
            git.prefetch_blame(sorted({c.doc for c, _ in items}))
            for c, _ in items:
                rev, epoch = git.written_at(c.doc, c.line)
                now_line = rev is None
                if now_line:
                    rev = git.head()
                    if rev is None:
                        c.status = "unverified"
                        continue
                groups[(id(git), rev)].append((c, git, epoch, now_line))
        for (_, rev), items in groups.items():
            git = items[0][1]
            names = sorted({n for c, *_ in items for n in c.extra["missing"]})
            found = git.grep_words(rev, names)
            if found:       # still in a file the index does not read (a script without an extension)?
                alive = git.alive_words(sorted(found))
                found = {n: v for n, v in found.items() if n not in alive}
            for c, _, epoch, now_line in items:
                gone = [n for n in c.extra["missing"] if n in found]
                if not gone:
                    c.status = "external"
                    continue
                gone.sort(key=lambda n: not found[n][2])        # a name the repo defined first
                where = found[gone[0]]
                # The repo never defined it, it only used it: an outside name (a library's) that the
                # code stopped using. Worth a note, not a warning.
                used = what != "flag" and not where[2]
                ev = [{"kind": "git", "rev": "HEAD" if now_line else rev[:10], "date": "" if now_line else day(epoch),
                       "path": where[0], "line": where[1],
                       "note": f"`{gone[0]}` was used here" if used else f"`{gone[0]}` was here"}]
                if not now_line:
                    ev += self._removed_by(git, rev, where[0], gone[0])
                sug = self._rename_hint(gone[0], where[0], flag=what == "flag")
                if what == "flag":
                    # the whole script left the repo (an installer moved to its own repo, completions
                    # rebuilt another way): a bare `--flag` may well mean the program that lives on elsewhere
                    sev = WARNING if where[0] in self.inv.file_set else INFO
                    self.add("flag-removed", sev, c, flag=c.target, script=where[0], when=day(epoch) or "HEAD",
                             evidence=ev, suggestion=sug)
                elif now_line:
                    self.add("symbol-removed-now", INFO if used else WARNING, c, evidence=ev, suggestion=sug)
                else:
                    # the package that held it left the repo (an SDK moved to its own repo): the name may
                    # well live on there, as with a flag whose script left
                    left = self._package_left(git, where[0], rev)
                    if left:
                        ev.append({"kind": "git", "path": left, "note": "this package is no longer in the repo"})
                    self.add("symbol-gone", INFO if used or left else WARNING, c, evidence=ev, suggestion=sug,
                             when=day(epoch))

    def _package_left(self, git, path: str, rev: str) -> str:
        """The package folder that held `path`, when the package left the repo and lives on elsewhere: the
        folder is gone and the repo now depends on the package by the name its manifest had (`@acme/sdk`).
        A package deleted for good (a crate folded into another) is no such proof."""
        hist = git.history()
        if not hist.ok:
            return ""
        d = posixpath.dirname(path)
        while d:
            for m in PACKAGE_MANIFESTS:
                manifest = posixpath.join(d, m)
                if hist.ever(manifest):
                    if d in self.inv.dir_set:       # still in the repo (files, not an empty folder left on disk)
                        return ""
                    name = re.search(r'"name"\s*:\s*"([^"]+)"|^module\s+(\S+)|^name\s*=\s*"([^"]+)"',
                                     git.show(rev, manifest) or "", re.M)
                    name = name and next(g for g in name.groups() if g)
                    return d if name and self._depended_on(name) else ""
            d = posixpath.dirname(d)
        return ""

    def _depended_on(self, name: str) -> bool:
        """Some manifest of the repo names this package (as a dependency: its own manifest is gone)."""
        if self._manifest_texts is None:
            self._manifest_texts = [self.inv.text(f) or "" for f in sorted(self.inv.file_set)
                                    if posixpath.basename(f) in PACKAGE_MANIFESTS
                                    or re.match(r"requirements.*\.txt$", posixpath.basename(f))]
        word = re.compile(r"(?<![\w@/.-])" + re.escape(name) + r"(?![\w/.-])")
        return any(word.search(text) for text in self._manifest_texts)

    def _removed_by(self, git, rev: str, path: str, name: str) -> list:
        """One more evidence line: the commit that took `name` out of `path`, when git can tell."""
        if self._removed_left <= 0:
            return []
        self._removed_left -= 1
        hit = git.removed_in(rev, path, name)
        if not hit:
            return []
        return [{"kind": "git", "rev": hit["sha"], "date": hit["date"], "path": path,
                 "note": "removed by this commit: " + hit["subject"]}]

    def _rename_hint(self, name: str, path: str, flag: bool = False) -> str:
        text = self.inv.text(path) if path in self.inv.file_set else None
        if not text:
            return ""
        if flag:
            cands = set(re.findall(r"(?<![\w-])--[A-Za-z][\w-]*", text)) - {name}
        else:
            cands = {t for t in IDENT.findall(text) if len(t) >= 3} - {name}
        best = difflib.get_close_matches(name, sorted(cands), n=1, cutoff=0.75)
        if best:
            return (f"maybe renamed to `{best[0]}` ({path})" if self.lang != "vi"
                    else f"có thể đã đổi tên thành `{best[0]}` ({path})")
        return ""

    # -- npm scripts, make targets -----------------------------------------
    def _find_up(self, start: str, names: tuple) -> str | None:
        d = start
        while True:
            for n in names:
                p = posixpath.join(d, n) if d else n
                if p in self.inv.file_set:
                    return p
            if not d or d in (".", "/"):
                return None
            d = posixpath.dirname(d)

    def _npm_make(self, claims: list) -> None:
        for c in claims:
            ddir = posixpath.dirname(c.doc)
            cwd = c.extra.get("cwd")
            start = posixpath.normpath(posixpath.join(ddir, cwd)) if cwd else ddir
            if c.kind == "npm":
                pj = self._find_up(start, ("package.json",))
                if not pj or pj not in self.index.npm:
                    c.status = "external"
                    continue
                def has(scripts, c=c) -> bool:
                    if c.extra.get("glob"):     # `bun run --parallel "*:check"` runs every script the pattern fits
                        return any(fnmatch.fnmatchcase(s, c.target) for s in scripts)
                    return c.target in scripts
                if has(self.index.npm[pj]["scripts"]) or (c.extra.get("builtin") and c.target != "test"):
                    c.status, c.where = "ok", pj
                    continue
                if c.extra.get("bare"):
                    c.status = "external"       # `pnpm vite`, `yarn patch`: a tool of the project or of the runner
                    continue
                repo = self.inv.repo_of(pj)
                other = next((p for p in sorted(self.index.npm) if has(self.index.npm[p]["scripts"])
                              and self.inv.repo_of(p) == repo), None)
                if other:
                    c.status, c.where = "ok", other     # a workspace: the line is about another package of the repo
                    c.extra["far"] = True
                    continue
                if self.acknowledged(c):
                    continue
                if posixpath.dirname(pj) == ("" if start == "." else start):
                    self.add("npm-script-missing", ERROR, c, name=c.target, manifest=pj)
                else:       # found by walking up: a guide may be telling readers about their own project
                    self.add("npm-script-missing", INFO, c, name=c.target, manifest=pj, suggestion=(
                        "the line may be about the reader's own project" if self.lang != "vi"
                        else "dòng này có thể nói về dự án của chính người đọc"))
            else:
                names = ("Makefile", "makefile", "GNUmakefile") if c.extra.get("tool") == "make" else ("justfile", "Justfile")
                mk = self._find_up(start, names)
                if not mk or mk not in self.index.make:
                    c.status = "external"
                    continue
                targets = self.index.make[mk]
                # `%:` and `test-%:` are pattern rules: `make test-full` runs `test-%`
                if c.target in targets or any("%" in t and fnmatch.fnmatchcase(c.target, t.replace("%", "*"))
                                              for t in targets):
                    c.status, c.where = "ok", mk
                    continue
                if self.acknowledged(c):
                    continue
                self.add("make-target-missing", ERROR, c, name=c.target, manifest=mk)

    # -- decisions -------------------------------------------------------------
    def _decisions(self, claims: list) -> None:
        dec = self.decisions
        for c in claims:
            if any(part.lower() in {"template", "templates", "scaffold", "boilerplate"}
                   for part in c.doc.split("/")[:-1]):
                c.status = "skipped"
                continue
            item = dec.lookup(c.target, c.doc)
            if item is None:
                if dec.known_prefix(c.target, c.doc):
                    self.add("decision-unknown", ERROR, c, log=dec.names_for(c.doc))
                else:
                    c.status = "external"
                continue
            c.where = f"{item['log']}:{item['line']}"
            if self.kind(c.doc) == "history":
                c.status = "ok"         # history may cite replaced decisions on purpose
                continue
            ev = [{"kind": "doc", "path": item.get("note_log", item["log"]), "line": item["note_line"]}]
            by = ", ".join(item["by"]) or "?"
            if item["status"] == "superseded":
                self.add("decision-superseded", WARNING, c, by=by, evidence=ev)
            elif item["status"] == "amended":
                self.add("decision-amended", INFO, c, by=by, evidence=ev)
                c.status = "ok"
            else:
                c.status = "ok"

    # -- versions and pinned dependencies ----------------------------------
    def _versions(self, claims: list) -> None:
        for c in claims:
            m = self.index.manifest_for(posixpath.dirname(c.doc))
            if not m:
                continue
            if c.target.lstrip("v") == m["version"].lstrip("v"):
                c.status, c.where = "ok", m["file"]
            else:
                self.add("version-mismatch", WARNING, c, manifest=m["file"], actual=m["version"],
                         evidence=[{"kind": "code", "path": m["file"]}])

    def _deps(self, claims: list) -> None:
        for c in claims:
            d = posixpath.dirname(c.doc)
            while True:
                hit = None
                for pf, pins in self.index.pins.items():
                    if posixpath.dirname(pf) == d and c.target in pins and not pf.endswith("package.json"):
                        hit = (pf, pins[c.target])
                        break
                if hit or not d:
                    break
                d = posixpath.dirname(d)
            if not hit:
                continue
            want = c.extra["spec"]
            have = hit[1]
            if sorted(want.split(",")) == sorted(have.split(",")):
                c.status, c.where = "ok", hit[0]
            else:
                self.add("dep-mismatch", WARNING, c, manifest=hit[0], actual=c.target + have,
                         evidence=[{"kind": "code", "path": hit[0]}])

    # -- the same sentence in two docs, different numbers -------------------
    def _line_time(self, doc: str, line: int) -> float:
        git = self.git_for(doc)
        if git:
            rev, epoch = git.written_at(doc, line)
            if rev:
                return float(epoch or 0)
            return self._now
        try:
            return os.stat(self.inv.root / doc).st_mtime
        except OSError:
            return 0.0

    def _copies(self) -> None:
        shapes: dict[str, list] = defaultdict(list)
        logs = self.decisions.logs if self.decisions else set()
        for path, d in self.docs.items():
            if path in logs or self.kind(path) == "history" or d.ignore_file or is_post(path):
                continue        # the last: "1.1K contributors" was true the day the post went out
            for n, text in d.prose:
                if n in d.ignored:
                    continue
                s = re.sub(r"[`*_>#|]", " ", text).strip().lower()
                s = re.sub(r"\s+", " ", s)
                if len(s) < 50 or "copyright" in s or "©" in s:
                    continue        # the second: a copyright line keeps the year its file was born
                nums = tuple(NUMBER.findall(s))
                if not nums:
                    continue
                shape = NUMBER.sub("#", s)
                if len(shape.replace("#", "").replace(" ", "")) < 40:
                    continue
                shapes[shape].append((path, n, nums))
        groups = []
        for items in shapes.values():
            docs_in = {i[0] for i in items}
            variants = {i[2] for i in items}
            if len(docs_in) < 2 or len(variants) < 2:
                continue
            if len(variants) >= 3:
                continue        # a template filled with different values (reports, notes)
            groups.append(items)
        for items in groups:
            for g in {id(self.git_for(p)): self.git_for(p) for p, _, _ in items}.values():
                if g:
                    g.prefetch_blame(sorted({p for p, _, _ in items if self.git_for(p) is g}))
        for items in groups:
            timed = sorted(((self._line_time(p, n), p, n, nums) for p, n, nums in items), reverse=True)
            newest = timed[0]
            for t, p, n, nums in timed[1:]:
                if nums == newest[3] or t >= newest[0] or p == newest[1]:
                    continue
                if NUMBER.sub("#", p) == NUMBER.sub("#", newest[1]):
                    continue        # `migrate-v1-to-v2.md` and `migrate-v2-to-v3.md`: two versions, not two copies
                diff_mine = [a for a, b in zip(nums, newest[3]) if a != b]
                diff_theirs = [b for a, b in zip(nums, newest[3]) if a != b]
                self.add("copies-diverged", WARNING, None, path=p, line=n,
                         claim=", ".join(diff_mine[:3]), other=f"{newest[1]}:{newest[2]}",
                         mine=", ".join(diff_mine[:3]), theirs=", ".join(diff_theirs[:3]),
                         evidence=[{"kind": "doc", "path": newest[1], "line": newest[2]}])

    # -- tables: rows with the wrong number of cells, rows cut off from their table --
    def _tables(self) -> None:
        for path, d in self.docs.items():
            if d.ignore_file:
                continue
            for t in d.tables:
                if not t.rows:
                    continue
                bad = [(n, k) for n, k in t.rows if k != t.header_cells and n not in d.ignored]
                if not bad:
                    continue
                counts: dict = defaultdict(int)
                for _, k in bad:
                    counts[k] += 1
                cells = max(counts, key=counts.get)
                order = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))     # 45 rows of 3, then 3 of 4
                detail = ", ".join((f"{n} dòng {k} ô" if self.lang == "vi" else f"{n} with {k}") for k, n in order)
                self.add("table-shape", INFO, None, path=path, line=bad[0][0], claim=f"{len(bad)} rows",
                         bad=len(bad), rows=len(t.rows), cells=cells, header=t.header_cells, detail=detail)
            runs: list = []
            for n in d.orphan_rows:
                if n in d.ignored:
                    continue
                if runs and n - runs[-1][-1] <= 2:
                    runs[-1].append(n)
                else:
                    runs.append([n])
            for run in runs:
                if len(run) < 2:
                    continue
                above = [t for t in d.tables if t.start < run[0]]
                if not above:
                    continue
                last = above[-1]
                end = last.rows[-1][0] if last.rows else last.start + 1
                a, b = end + 1, run[0] - 1
                span = f"{a}" if a >= b else f"{a}–{b}"
                if all(not d.line_text(n).strip() for n in range(a, b + 1)):
                    sug = (f"delete the blank line {span}" if self.lang != "vi" else f"xóa dòng trống {span}")
                elif a == b and not d.line_text(end).rstrip().endswith("|"):
                    sug = (f"join line {a} onto line {end}: a line break inside a cell cut the table"
                           if self.lang != "vi" else
                           f"nối dòng {a} vào cuối dòng {end}: một lần xuống dòng trong ô đã cắt đôi bảng")
                else:
                    sug = (f"move line {span} below the table, or give the rows from line {run[0]} their own header"
                           if self.lang != "vi" else
                           f"dời dòng {span} xuống dưới bảng, hoặc thêm dòng tiêu đề cho các dòng từ {run[0]}")
                self.add("table-orphan", WARNING, None, path=path, line=run[0], claim=f"{len(run)} rows",
                         rows=len(run), end=end,
                         evidence=[{"kind": "doc", "path": path, "line": a,
                                    "text": d.line_text(a).strip()[:80] or "(blank line)"}],
                         suggestion=sug)

    # -- prose rules made executable --------------------------------------------
    def _rules(self) -> None:
        for path, d in self.docs.items():
            for dv in d.directives:
                m = FORBID.match(dv.body.strip())
                if not m:
                    if dv.body.lower().startswith("forbid"):
                        self.add("rule-invalid", ERROR, None, path=path, line=dv.line, claim=dv.body,
                                 error="expected: forbid /regex/ in glob")
                    continue
                if m.group(1) is not None:
                    flags = 0
                    for ch in m.group(2) or "":
                        flags |= {"i": re.I, "m": re.M, "s": re.S, "x": re.X}[ch]
                    try:
                        rx = re.compile(m.group(1), flags)
                    except re.error as e:
                        self.add("rule-invalid", ERROR, None, path=path, line=dv.line, claim=dv.body, error=str(e))
                        continue
                else:
                    rx = re.compile(re.escape(m.group(3) or m.group(4)))
                globs = [g.strip() for g in re.split(r"[,\s]+", m.group(5) or "") if g.strip()]
                rule_text = re.sub(r"\s+", " ", re.sub(r"[`*_]", "", dv.rule_text)).strip()[:140]
                hits = 0
                for f in self.inv.code:
                    if globs and not match_any(f, globs):
                        continue
                    if not globs and kind_of(f) != "code":
                        continue
                    text = self.inv.text(f)
                    if not text or not rx.search(text):
                        continue
                    for i, line in enumerate(text.splitlines(), 1):
                        if rx.search(line):
                            self.add("rule-violation", ERROR, None, path=f, line=i, claim=redact(line.strip())[:120],
                                     doc=f"{path}:{dv.line}", rule_text=rule_text,
                                     evidence=[{"kind": "doc", "path": path, "line": dv.line, "text": rule_text}])
                            hits += 1
                            if hits >= 50:
                                break
                    if hits >= 50:
                        break

    # -- freshness ----------------------------------------------------------------
    def freshness(self, claims: list) -> dict:
        """doc -> {"refs": n, "newer": [(path, epoch)], "doc_time": epoch}"""
        refs: dict[str, set] = defaultdict(set)
        for c in claims:
            if c.status != "ok" or not c.where or self.kind(c.doc) != "live":
                continue
            p = c.where.split(":", 1)[0] if c.kind in ("symbol", "decision") else c.where
            if p in self.inv.file_set and kind_of(p) in ("code", "conf") and p != c.doc:
                refs[c.doc].add(p)
        mod = self.modified()
        out = {}
        for doc, files in refs.items():
            git = self.git_for(doc)
            if git is None:
                continue
            times = git.last_times()
            if doc in mod or doc not in times:
                out[doc] = {"refs": len(files), "newer": [], "doc_time": self._now}
                continue
            t_doc = times[doc]
            newer = []
            for f in files:
                t = self._now if f in mod else times.get(f)
                if t and t > t_doc + 86400:
                    newer.append((f, t))
            newer.sort(key=lambda x: (-x[1], x[0]))     # one commit often touches several: same output every run
            out[doc] = {"refs": len(files), "newer": newer, "doc_time": t_doc}
            if newer:
                shown = ", ".join(f"`{f}` ({day(t) if t < self._now - 60 else 'now'})" for f, t in newer[:3])
                if len(newer) > 3:
                    shown += f" +{len(newer) - 3}"
                self.add("stale-risk", INFO, None, path=doc, line=1, claim=f"{len(newer)} files", files=shown,
                         evidence=[{"kind": "code", "path": f} for f, _ in newer[:5]])
        return out
