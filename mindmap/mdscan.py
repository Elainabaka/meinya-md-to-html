"""A small Markdown scanner: just enough structure to find claims.

It records, with 1-based line numbers: headings (with GitHub anchors),
inline code spans, fenced blocks, links, tables, `<!-- mindmap: ... -->`
directives, and which lines are prose. Content inside HTML comments and
YAML front matter is not prose.
"""

from __future__ import annotations

import re
import html
import posixpath
import shlex
import string
import unicodedata
from dataclasses import dataclass, field

FENCE_OPEN = re.compile(r"^(\s*)(`{3,}|~{3,})\s*([^`\s{]*)")
ATX = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
SETEXT_EQ = re.compile(r"^\s{0,3}=+\s*$")
SETEXT_DASH = re.compile(r"^\s{0,3}-+\s*$")
TABLE_SEP = re.compile(r"^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$")
# a line that starts another block and so ends a table: indented code, quote, list item, rule, HTML
TABLE_BREAK = re.compile(r"^(?: {4}|\t)|^\s{0,3}(?:>|[-+*](?:\s|$)|\d{1,9}[.)](?:\s|$)|<[A-Za-z/!?]"
                         r"|(?:\*\s*){3,}$|(?:-\s*){3,}$|(?:_\s*){3,}$)")
LINK = re.compile(r"(!?)\[((?:[^\[\]]|\[[^\]]*\])*)\]\(\s*(<[^>]*>|[^)\s]+)(?:\s+(?:\"[^\"]*\"|'[^']*'|\([^)]*\)))?\s*\)")
REF_DEF = re.compile(
    r"""^\s{0,3}\[(?!\^)([^\]]+)\]:[ \t]*(<[^<>]+>|[^\s<>]+)
    (?:[ \t]+(?:"(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*'|\((?:\\.|[^)\\])*\)))?[ \t]*$""",
    re.X)
DIRECTIVE = re.compile(r"<!--\s*mindmap\s*:\s*(.*?)\s*-->", re.IGNORECASE)
# `<a name="x">`, `<h3 id="x">`, `<div id=x>`: any tag can carry the anchor a link jumps to
HTML_ID = re.compile(r"""<[A-Za-z][\w-]*\s+[^>]*?\b(?:name|id)\s*=\s*["']?([^"'\s>]+)""", re.IGNORECASE)
HEADING_ID = re.compile(r"\s*\{\s*#([\w:.-]+)(?:\s+[^}]*)?\}\s*#*\s*$")
ATTR_ID = re.compile(r"\{:?\s*#([\w:.-]+)(?:\s[^}]*)?\}")          # `{#id}`, `{: #id}` on any block
DEFINITION = re.compile(r"^\s{0,3}:\s+\S")                         # `: text` under a term (a definition list)
TAG = re.compile(r"<[^>]+>")
ESCAPED_PUNCT = re.compile(r"\\([" + re.escape(string.punctuation) + r"])")
MDX_IMPORT = re.compile(r"""^\s*import\s+.+?\s+from\s+(['"])(\./[^'"]+\.mdx?)\1\s*;?\s*$""")
FENCE_PROMPT = re.compile(r"^\s*(?:[$❯➜%]|PS(?:\s+[^>\r\n]*)?>|>>>)(?:[ \t]+|$)")
CLONE_CD = re.compile(r"""^\s*(?:cd|set-location)(?:\s+/d)?\s+("[^"]*"|'[^']*'|[^\s;|&]+)\s*(?:\#.*)?$""", re.I)
READER_TREE = re.compile(
    r"\b(?:for example|as an example|suppose|assuming|scaffold|"
    r"(?:with|given|consider)\s+(?:this|the following|a)\s+(?:content|source|file|directory|project)\s+(?:structure|tree|layout)|"
    r"an?\s+(?:file|logical|content)\s+tree\s*:|(?:the|this)\s+(?:example|sample)\s+above|"
    r"your(?:\s+[\w-]+){0,3}\s+(?:project|site|content|repository|repo|app)|"
    r"(?:you|we)\s+(?:can|could|should|may|might|must|will)\s+(?:also\s+)?(?:create|scaffold)|"
    r"(?:you|we)\s+(?:can|could|should|may|might|must|will)\b[^.!?\n]{0,100}\bby\s+(?:creating|adding|generating|scaffolding)|"
    r"a[n]?\b[^.!?\n]{0,100}\bis\s+a[n]?\s+(?:file|directory)\b)", re.I)


def _clone_directory(line: str) -> str | None:
    try:
        words = [word.strip("\"'") for word in shlex.split(line, posix=False)]
    except ValueError:
        return None
    if len(words) < 3 or words[0].lower() not in ("git", "git.exe") or words[1] != "clone":
        return None
    args = []
    takes_value = False
    for word in words[2:]:
        if word.startswith("#"):
            break
        if takes_value:
            takes_value = False
        elif word in ("-b", "--branch", "--depth", "-o", "--origin", "-c", "--config", "--template", "--reference", "--separate-git-dir"):
            takes_value = True
        elif not word.startswith("-"):
            args.append(word)
    if not args or len(args) > 2 or any(word in ("&&", "||", ";", "|") for word in args):
        return None
    directory = args[1] if len(args) == 2 else args[0].rstrip("/").rsplit("/", 1)[-1].rsplit(":", 1)[-1].removesuffix(".git")
    return posixpath.normpath(directory.replace("\\", "/"))


def _is_diagram(lines: list, heading: str) -> bool:
    text = "\n".join(re.split(r"\s+#\s", line, maxsplit=1)[0] for _, line in lines)
    if re.search(r"[┌┐┏┓┗┛╭╮╰╯▼▲◀▶]|^\s*[|│]\s*\n\s*[vV^↓↑]\s*$|^\s*\+(?:[-=]+\+)+\s*$", text, re.M):
        return True
    if re.search(r"^\s*[^\n]+\?\s*$", text, re.M) and re.search(r"[├└]|^\s*[|+]--", text, re.M):
        return True
    if re.search(r"\b(?:flow|workflow|sequence|lifecycle|pipeline|diagram|process)\b", heading, re.I) and re.search(r"[←→]|(?<!-)--?>", text):
        return True
    for line in text.splitlines():
        branch = re.match(r"^\s*[│| ]*(?:[├└][─-]+|[+]--)[ \t]*(.+)", line)
        if branch and re.search(r"[→⇒]|(?<!-)--?>", branch.group(1)):
            label = re.split(r"[→⇒]|(?<!-)--?>", branch.group(1), maxsplit=1)[0].strip()
            if (not re.match(r"^[\w.@+~-]+(?:[/\\]|\.[A-Za-z0-9]+(?:\s|$))", label)
                    and (len(label.split()) > 1 or re.search(r"[()?]", label)
                         or label.lower() in ("yes", "no", "true", "false"))):
                return True
    return False


@dataclass
class Span:
    line: int
    col: int
    text: str
    ctx: str = "inline"    # inline | table | heading


@dataclass
class Fence:
    start: int
    lang: str
    lines: list = field(default_factory=list)   # [(line_no, text)]


@dataclass
class Link:
    line: int
    col: int
    text: str
    dest: str
    image: bool = False


@dataclass
class Heading:
    line: int
    level: int
    text: str
    slug: str


@dataclass
class Table:
    start: int
    header_cells: int
    rows: list = field(default_factory=list)    # [(line_no, cell_count)]


@dataclass
class Directive:
    line: int
    body: str
    rule_text: str = ""   # nearest prose line above (the rule in words)


@dataclass
class Doc:
    path: str
    lines: list
    headings: list = field(default_factory=list)
    spans: list = field(default_factory=list)
    fences: list = field(default_factory=list)
    links: list = field(default_factory=list)
    tables: list = field(default_factory=list)
    orphan_rows: list = field(default_factory=list)   # line numbers of `|` rows outside any table
    directives: list = field(default_factory=list)
    prose: list = field(default_factory=list)    # [(line_no, text)] outside fences/comments
    ignored: set = field(default_factory=set)
    ignore_file: bool = False
    kind_mark: str = ""          # `<!-- mindmap: history -->` (or plan, live): how to read this doc
    anchors: set = field(default_factory=set)
    imports: list[str] = field(default_factory=list)

    def line_text(self, n: int) -> str:
        return self.lines[n - 1] if 0 < n <= len(self.lines) else ""


def plain_heading(text: str) -> str:
    """Heading text as GitHub renders it (markup stripped)."""
    out = []
    start = 0
    spans = _spans(text)
    for index, (span_start, span_end, content) in enumerate(spans + [(len(text), len(text), "")]):
        part = ESCAPED_PUNCT.sub(lambda match: f"\0{ord(match.group(1))}\0", text[start:span_start])
        out.append(part)
        if span_end > span_start:
            out.append(f"\0c{index}\0")
        start = span_end
    part = re.sub(r"!?\[([^\]]*)\]\([^)]*\)", r"\1", "".join(out))
    part = TAG.sub("", part)
    part = re.sub(r"(\*\*|\*|~~)(?=\S)(.+?)(?<=\S)\1", r"\2", part)
    part = re.sub(r"(?<![\w])(__|_)(?=\S)(.+?)(?<=\S)\1(?![\w])", r"\2", part)
    part = html.unescape(part)
    part = re.sub(r"\0(\d+)\0", lambda match: chr(int(match.group(1))), part)
    part = re.sub(r"\0c(\d+)\0", lambda match: spans[int(match.group(1))][2], part)
    return part.strip()


def skeleton(anchor: str) -> str:
    """The letters and digits of an anchor, accents off: the part every way of naming a heading keeps
    (`build.target` is `buildtarget` on GitHub and `build-target` on a VitePress site)."""
    return "".join(ch for ch in unicodedata.normalize("NFKD", anchor).casefold() if ch.isalnum())


def github_slug(text: str) -> str:
    out = []
    for ch in plain_heading(text).lower():
        cat = unicodedata.category(ch)
        if ch in " -_" or ch.isalnum() or cat.startswith("M"):
            out.append("-" if ch == " " else ch)
    return "".join(out)


def code_spans(line: str) -> list:
    """[(col0, content)] of inline code spans in one line."""
    return [(a, c) for a, _, c in _spans(line)]


def _spans(line: str) -> list:
    """[(start, end_exclusive, content)] of inline code spans."""
    out = []
    i, n = 0, len(line)
    while i < n:
        if line[i] == "\\" and i + 1 < n and line[i + 1] in string.punctuation:
            i += 2
            continue
        if line[i] != "`":
            i += 1
            continue
        j = i
        while j < n and line[j] == "`":
            j += 1
        run = j - i
        k = j
        found = -1
        while k < n:
            if line[k] == "`":
                m = k
                while m < n and line[m] == "`":
                    m += 1
                if m - k == run:
                    found = k
                    break
                k = m
            else:
                k += 1
        if found < 0:
            i = j
            continue
        content = line[j:found]
        if len(content) >= 2 and content[0] == " " and content[-1] == " " and content.strip():
            content = content[1:-1]
        out.append((i, found + run, content))
        i = found + run
    return out


def mask_code(line: str) -> str:
    """Replace inline code spans with spaces (keeps columns)."""
    chars = list(line)
    for start, end, _ in _spans(line):
        for p in range(start, end):
            chars[p] = " "
    return "".join(chars)


def split_cells(line: str) -> list:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    return re.split(r"(?<!\\)\|", s)


def scan(path: str, text: str) -> Doc:
    lines = text.splitlines()
    doc = Doc(path=path, lines=lines)
    slug_count: dict = {}
    fence = None
    prompted = False
    cloned: set[str] = set()
    fence_context = ""
    fence_heading = ""
    context_start = 0
    paragraph = False
    fence_char, fence_len = "", 0
    in_comment = False
    ignore_range = False
    ignore_next = False
    table = None
    prev_prose = ""
    start = 1
    if lines and lines[0].strip() == "---":           # YAML front matter
        for k in range(1, min(len(lines), 200)):
            if lines[k].strip() in ("---", "..."):
                start = k + 2
                break

    def add_heading(n: int, level: int, raw: str) -> None:
        m = HEADING_ID.search(raw)             # "## Titel {#title}" (MkDocs attr_list, Docusaurus, Hugo, kramdown)
        if m:
            raw = raw[: m.start()]
            doc.anchors.add(m.group(1))
        slug = github_slug(raw)
        c = slug_count.get(slug, 0)
        slug_count[slug] = c + 1
        final = slug if c == 0 else f"{slug}-{c}"
        doc.headings.append(Heading(n, level, plain_heading(raw), m.group(1) if m else final))
        doc.anchors.add(final)

    introduction = "\n".join(lines[:min(start + 20, 60)])
    skill_examples = (posixpath.basename(path).lower() == "skill.md" or re.search(
        r"\bskills?\b[^\n]{0,100}\b(?:authoring|best practices|patterns)\b", introduction, re.I)) and re.search(
        r"\b(?:patterns|standards|best practices|test-driven|cross-project|across projects)\b",
        introduction, re.I)

    def add_fence() -> None:
        illustrative = READER_TREE.search(fence_context) or (skill_examples and re.search(
            r"\b(?:visual overview|pattern\s+\d+|(?:project|file|test|directory|folder|skill)\s+(?:\w+\s+)?(?:structure|organization|layout))\b",
            fence_heading, re.I))
        following = "\n".join(lines[n:n + 8])
        illustrative = illustrative or re.search(r"\b(?:the|this)\s+(?:example|sample)\s+above\b", following, re.I)
        if fence.lang in ("mermaid", "plantuml", "graphviz", "dot", "goat", "ditaa") or (
                (illustrative or _is_diagram(fence.lines, fence_heading)) and sum(
                    bool(re.search(r"[├└]|^\s*[|`+]--", text)) for _, text in fence.lines) >= 2):
            doc.ignored.add(fence.start)
        doc.fences.append(fence)

    for n in range(start, len(lines) + 1):
        raw = lines[n - 1]
        if fence is not None:
            stripped = raw.strip()
            if stripped and set(stripped) == {fence_char} and len(stripped) >= fence_len:
                add_fence()
                fence = None
                context_start = n
                paragraph = False
            else:
                prompt = FENCE_PROMPT.match(raw)
                if prompt:
                    prompted = True
                if prompt or not prompted:
                    command = raw[prompt.end():] if prompt else raw
                    directory = _clone_directory(command)
                    if directory:
                        cloned.add(directory)
                    change = CLONE_CD.fullmatch(command)
                    if change and posixpath.normpath(change.group(1).strip("\"'").replace("\\", "/")) in cloned:
                        continue
                    fence.lines.append((n, command))
            continue

        # directives and comments; one written inside `code` is shown to the reader, not obeyed
        spans = _spans(raw) if "`" in raw and DIRECTIVE.search(raw) else ()
        for m in DIRECTIVE.finditer(raw):
            if any(a <= m.start() < b for a, b, _ in spans):
                continue
            body = m.group(1).strip()
            low = body.lower()
            if low == "ignore-file":
                doc.ignore_file = True
            elif low in ("history", "plan", "live"):
                doc.kind_mark = low
            elif low == "ignore-start":
                ignore_range = True
            elif low == "ignore-end":
                ignore_range = False
            elif low in ("ignore-next-line", "ignore-next"):
                ignore_next = True
            elif low == "ignore":
                if raw[: m.start()].strip():
                    doc.ignored.add(n)
                else:
                    ignore_next = True
            else:
                doc.directives.append(Directive(n, body, prev_prose))
        if in_comment:
            paragraph = False
            if "-->" in raw:
                in_comment = False
            continue
        visible = re.sub(r"<!--.*?-->", "", raw)
        if "<!--" in visible:
            visible = visible[: visible.index("<!--")]
            in_comment = True

        if ignore_range:
            doc.ignored.add(n)
        elif ignore_next and visible.strip():
            doc.ignored.add(n)
            ignore_next = False

        m = FENCE_OPEN.match(visible)
        if m:
            fence_char = m.group(2)[0]
            fence_len = len(m.group(2))
            fence = Fence(n, (m.group(3) or "").lower())
            prompted = False
            cloned = set()
            fence_context = "\n".join(text for line_no, text in doc.prose[-8:]
                                      if line_no >= context_start and n - line_no <= 20)
            fence_heading = doc.headings[-1].text if doc.headings else ""
            paragraph = False
            table = None
            continue

        h = ATX.match(visible)
        if h:
            paragraph = False
            add_heading(n, len(h.group(1)), h.group(2))
            for col, content in code_spans(visible):
                doc.spans.append(Span(n, col + 1, content, "heading"))
            doc.prose.append((n, visible))
            table = None
            continue
        if n > start and (SETEXT_EQ.match(visible) or SETEXT_DASH.match(visible)):
            prev = lines[n - 2].strip() if n >= 2 else ""
            if prev and not prev.startswith(("|", "-", "*", "+", ">", "#", "<")) \
                    and not re.match(r"^\d+[.)]\s", prev) and (n - 1) not in {h.line for h in doc.headings} \
                    and not (SETEXT_DASH.match(visible) and doc.prose and doc.prose[-1][0] != n - 1):
                add_heading(n - 1, 1 if "=" in visible else 2, prev)
                paragraph = False
                continue

        # tables
        stripped = visible.strip()
        if stripped.startswith("|"):
            if table is None and n < len(lines) and TABLE_SEP.match(lines[n]) and "-" in lines[n]:
                table = Table(n, len(split_cells(visible)))
                doc.tables.append(table)
            elif table is not None and not TABLE_SEP.match(visible):
                table.rows.append((n, len(split_cells(visible))))
            elif table is None and len(split_cells(visible)) >= 2:
                doc.orphan_rows.append(n)
        elif table is not None and stripped and not TABLE_BREAK.match(visible):
            # GFM: a row needs no leading `|`; only a blank line or another block ends the table
            table.rows.append((n, len(split_cells(visible))))
        else:
            table = None

        ctx = "table" if table is not None else "inline"
        for col, content in code_spans(visible):
            doc.spans.append(Span(n, col + 1, content, ctx))
        masked = mask_code(visible)
        imported = MDX_IMPORT.match(masked)
        if imported:
            doc.imports.append(posixpath.normpath(posixpath.join(posixpath.dirname(path), imported.group(2))))
        for lm in LINK.finditer(masked):
            dest = lm.group(3)
            if dest.startswith("<") and dest.endswith(">"):
                dest = dest[1:-1]
            doc.links.append(Link(n, lm.start() + 1, lm.group(2), dest, lm.group(1) == "!"))
        rd = REF_DEF.fullmatch(visible) if not paragraph else None
        if rd:
            dest = rd.group(2)
            if dest.startswith("<") and dest.endswith(">"):
                dest = dest[1:-1]
            doc.links.append(Link(n, 1, rd.group(1), dest))
        for hm in HTML_ID.finditer(visible):
            doc.anchors.add(hm.group(1))
        for am in ATTR_ID.finditer(masked):
            doc.anchors.add(am.group(1))
        if DEFINITION.match(visible):
            # a definition list: the lines right above are its terms, and a site can give each term an id
            k = n - 2
            if k >= 0 and not lines[k].strip():
                k -= 1
            while k >= 0 and n - 2 - k < 6 and lines[k].strip() and not DEFINITION.match(lines[k]):
                doc.anchors.add(github_slug(lines[k].strip()))
                k -= 1
        if stripped:
            doc.prose.append((n, visible))
            if not stripped.startswith("<!--"):
                prev_prose = stripped
        paragraph = bool(stripped) and rd is None and table is None and not TABLE_BREAK.match(visible)
    if fence is not None:                      # unclosed fence runs to the end
        add_fence()
    return doc
