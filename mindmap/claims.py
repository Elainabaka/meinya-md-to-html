"""Turn a scanned doc into checkable claims.

Claim kinds: path, link, command (script/module/dir used by a command),
npm, make, flag, subcommand, symbol, decision, version, dep.
Extraction errs on the side of skipping: a claim we are unsure is a claim
(placeholders, URLs, prose) is not extracted at all.
"""

from __future__ import annotations

import posixpath
import re

from .mdscan import Doc
from .model import Claim

SHELL_LANGS = {
    "bash", "sh", "shell", "console", "zsh", "fish", "powershell", "ps", "ps1", "pwsh",
    "cmd", "bat", "batch", "dos", "terminal", "shellsession", "sh-session", "shell-session",
}
PY_RUNNERS = {"py", "python", "python3", "pythonw", "py.exe", "python.exe", "python3.exe", "pythonw.exe"}
NODE_RUNNERS = {"node", "node.exe", "deno", "tsx", "ts-node"}
PKG_RUNNERS = {"npm", "pnpm", "yarn", "bun"}
PKG_BUILTINS = {
    "install", "i", "ci", "add", "remove", "rm", "uninstall", "update", "up", "upgrade",
    "init", "create", "dlx", "exec", "x", "link", "unlink", "publish", "pack", "audit",
    "outdated", "list", "ls", "why", "info", "view", "config", "cache", "login", "logout",
    "version", "help", "set", "import", "dedupe", "prune", "rebuild", "store", "env",
    "workspace", "workspaces", "global", "fund", "doctor", "search", "--version", "-v",
}
SHELL_RUNNERS = {"bash", "sh", "zsh", "pwsh", "powershell", "powershell.exe", "pwsh.exe", "cmd", "cmd.exe", "call"}
PY_KNOWN_EXTERNAL = {
    "pip", "venv", "unittest", "pytest", "http", "json", "uvicorn", "gunicorn", "flask",
    "django", "streamlit", "graphify", "black", "ruff", "mypy", "pylint", "build", "twine",
    "ensurepip", "site", "pydoc", "timeit", "cProfile", "pdb", "doctest", "zipfile", "tarfile",
    "py_compile", "compileall", "webbrowser", "calendar", "this", "idlelib", "tkinter", "coverage",
}
KNOWN_EXT = set("""
md markdown mdx txt rst adoc py pyi pyw ipynb js mjs cjs jsx ts tsx mts cts json jsonc json5
yaml yml toml ini cfg conf env lock html htm css scss sass less svg png jpg jpeg gif webp ico
bmp tif tiff psd mp3 mp4 wav flac ogg opus m4a aac mov mkv webm avi pdf zip 7z tar gz tgz bz2
xz rar exe msi dll so dylib bat cmd ps1 psm1 psd1 sh bash zsh fish go rs java kt kts c h cc
cpp hpp cs fs vb rb php swift scala lua r sql db sqlite sqlite3 csv tsv xml proto graphql
gql vue svelte astro tex bib onnx pt pth bin ckpt safetensors gguf npz npy pkl joblib h5
tflite ttf otf woff woff2 srt vtt ass lrc log spec plist gradle properties mk cmake tpl j2
jinja hbs ejs pug mdc jsonl ndjson parquet arrow wasm whl crx xpi apk ipa dmg iso img
""".split())
CODE_EXT_FOR_CMD = (".py", ".js", ".mjs", ".cjs", ".ts", ".sh", ".bash", ".ps1", ".bat", ".cmd")
PY_LANGS = {"python", "py", "python3", "py3", "pycon", "ipython"}
PY_FROM_IMPORT = re.compile(r"^\s*(?:>>>\s*|\.\.\.\s*)?from\s+([A-Za-z_][\w.]*)\s+import\s+(.+)$")
IDENT_RE = re.compile(r"[A-Za-z_]\w*")
TREE_JUNK = re.compile(r"[←-⇿─-◿☀-➿]")


def runnable(base: str) -> bool:
    """`./x` runs a file only when it is a script or has no extension (`./gradlew`)."""
    return base.endswith(CODE_EXT_FOR_CMD + (".exe",)) or "." not in base.lstrip(".")
PLACEHOLDER_CHARS = set("<>{}*?$%|")
TEMPLATE_VAR = re.compile(r"[A-Z][A-Z0-9]*(?:_[A-Z0-9]+)+")       # a link target like ENGLISH_PAGE
CAPS_FILES = {"CODE_OF_CONDUCT", "PULL_REQUEST_TEMPLATE", "ISSUE_TEMPLATE"}
PLACEHOLDER_SEGMENTS = {
    "foo", "bar", "baz", "qux", "xxx", "yyy", "zzz", "nnn", "abc", "xyz", "path", "your",
    "my", "some", "example", "sample", "somewhere", "file", "folder", "dir", "name",
    "ten", "thu_muc", "thư_mục", "đường_dẫn",
}
KEYWORDS = set("""
true false none null undefined nan self this cls super def class return import from async
await yield lambda function var let const new delete typeof instanceof in of is not and or
if else elif for while try except catch finally raise throw with as pass break continue
global nonlocal assert print len str int float list dict set tuple bool object type range
open bytes main init args kwargs void public private static final string number boolean
""".split())
DEP_SPEC = re.compile(
    r"^([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*"
    r"((?:===|==|>=|<=|~=|!=|<|>)\s*[A-Za-z0-9.*+!_-]+(?:\s*,\s*(?:==|>=|<=|~=|!=|<|>)\s*[A-Za-z0-9.*+!_-]+)*)$"
)
SYMBOL = re.compile(
    r"^(?:[A-Za-z_][A-Za-z0-9_]*)(?:(?:\.|::|#)[A-Za-z_][A-Za-z0-9_]*)*(?:\(\s*[^()]*\))?$"
)
VERSION_IN_HEADING = re.compile(r"(?:\bv|\bversion\s+|\bphiên bản\s+)(\d+\.\d+\.\d+(?:-[0-9A-Za-z.]+)?)\b", re.I)
TREE_GLYPHS = set(" \t│├└─┬┼┊┆|`+")
PROMPT = re.compile(r"^\s*(?:\$|>|%|PS[^>]*>|[A-Za-z]:\\[^>]*>)\s+")


def split_cmd(s: str) -> list:
    """Split a command line into argv, honoring quotes, without escapes."""
    tokens, cur, quote, had = [], [], None, False
    for ch in s:
        if quote:
            if ch == quote:
                quote = None
            else:
                cur.append(ch)
        elif ch in "\"'":
            quote = ch
            had = True
        elif ch.isspace():
            if cur or had:
                tokens.append("".join(cur))
                cur, had = [], False
        else:
            cur.append(ch)
    if cur or had:
        tokens.append("".join(cur))
    return tokens


def split_compound(line: str) -> list:
    parts, cur, quote = [], [], None
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            cur.append(ch)
            i += 1
            continue
        two = line[i:i + 2]
        if two in ("&&", "||"):
            parts.append("".join(cur))
            cur = []
            i += 2
            continue
        if ch in ";|" and not (ch == "|" and i > 0 and line[i - 1] == ">"):
            parts.append("".join(cur))
            cur = []
            i += 1
            continue
        cur.append(ch)
        i += 1
    parts.append("".join(cur))
    return [p.strip() for p in parts if p.strip()]


def has_placeholder(s: str) -> bool:
    if any(c in PLACEHOLDER_CHARS for c in s) or "..." in s or "…" in s:
        return True
    if "YYYY" in s.upper() and re.search(r"y{4}", s, re.I):
        return True
    low = s.lower().replace("\\", "/")
    if "path/to/" in low:
        return True
    for seg in low.split("/"):
        stem = seg.rsplit(".", 1)[0] if "." in seg[1:] else seg
        if stem in PLACEHOLDER_SEGMENTS or (len(stem) == 1 and stem.isalpha() and "." in seg):
            return True
    return False


def clean_path_text(s: str) -> str:
    s = s.strip().strip("\"'")
    s = s.rstrip(",;:")
    if s.endswith(".") and not s.endswith(".."):
        s = s[:-1]
    s = s.replace("\\", "/")
    while s.startswith("./"):
        s = s[2:]
    return s


def path_strength(s: str) -> int:
    """0 = not a path, 1 = weak (maybe prose like cpu/cuda), 2 = clearly a path."""
    if not s or "://" in s or s.startswith(("mailto:", "-", "@", "#", "=")) or "\n" in s:
        return 0
    if re.match(r"^[A-Za-z]:/", s) or s.startswith(("~", "/")):
        return 0        # absolute: handled by the caller
    if has_placeholder(s) or "=" in s or s.count(":") > 0:
        return 0
    name = s.rstrip("/").rsplit("/", 1)[-1]
    ext = name.rsplit(".", 1)[-1].lower() if "." in name[1:] else ""
    if re.match(r"^v?\d+(\.\d+)+$", name):
        return 0
    if "/" not in s:
        if " " in s:
            return 0
        return 2 if ext in KNOWN_EXT else 0
    if " " in s and not ext and not s.endswith("/"):
        return 1
    if ext in KNOWN_EXT or s.endswith("/") or s.count("/") >= 2:
        return 2
    return 1


class Extractor:
    def __init__(self, decision_re: re.Pattern | None = None, decision_log: set | None = None,
                 root_abs: str = ""):
        self.decision_re = decision_re
        self.decision_log = decision_log or set()
        self.root_abs = root_abs.replace("\\", "/").rstrip("/").lower()

    def extract(self, doc: Doc) -> list:
        if doc.ignore_file:
            return []
        out: list[Claim] = []
        ddir = posixpath.dirname(doc.path)
        for sp in doc.spans:
            if sp.line in doc.ignored:
                continue
            out.extend(self._inline(doc, sp.line, sp.col, sp.text, sp.ctx))
        for fence in doc.fences:
            if fence.start in doc.ignored:
                continue
            lines = [(n, t) for n, t in fence.lines if n not in doc.ignored]
            if self._is_tree(lines):
                out.extend(self._tree(doc, ddir, lines))
            elif fence.lang in SHELL_LANGS or (fence.lang in ("", "text", "txt") and self._looks_shell(lines)):
                out.extend(self._shell_block(doc, lines, fence.lang))
            elif fence.lang in PY_LANGS:
                out.extend(self._python_block(doc, lines))
        for ln in doc.links:
            if ln.line in doc.ignored:
                continue
            c = self._link(doc, ln)
            if c:
                out.append(c)
        if self.decision_re is not None and doc.path not in self.decision_log:
            for n, text in doc.prose:
                if n in doc.ignored:
                    continue
                for m in self.decision_re.finditer(text):
                    out.append(Claim("decision", m.group(0), m.group(0), doc.path, n, m.start() + 1, "prose"))
        for h in doc.headings:
            if h.line in doc.ignored:
                continue
            m = VERSION_IN_HEADING.search(h.text)
            if m and not re.search(r"change|history|release|thay[ _-]?đổi", doc.path, re.I):
                out.append(Claim("version", m.group(1), m.group(1), doc.path, h.line, 1, "heading"))
        return out

    # -- python examples ---------------------------------------------------
    @staticmethod
    def _python_block(doc: Doc, lines: list) -> list:
        """`from pkg.mod import Name` in an example says pkg.mod still has Name."""
        out = []
        i = 0
        while i < len(lines):
            n, raw = lines[i]
            m = PY_FROM_IMPORT.match(raw)
            i += 1
            if not m or m.group(1) == "__future__":
                continue
            names = m.group(2).split("#", 1)[0]
            if names.strip().startswith("(") and ")" not in names:
                while i < len(lines) and ")" not in names:        # parenthesized, one name per line
                    names += " " + lines[i][1].split("#", 1)[0]
                    i += 1
            for part in names.strip().strip("()").split(","):
                name = part.strip().split(" as ")[0].strip()
                if IDENT_RE.fullmatch(name) and name.lower() not in KEYWORDS:
                    col = raw.find(name) + 1 if name in raw else 1
                    out.append(Claim("symbol", name, name, doc.path, n, col, "example",
                                     {"parts": [name], "from": m.group(1)}))
        return out

    # -- inline code -------------------------------------------------------
    def _inline(self, doc: Doc, line: int, col: int, text: str, ctx: str) -> list:
        t = text.strip()
        if not t or len(t) > 300:
            return []
        if self.decision_re is not None and self.decision_re.fullmatch(t):
            return []          # decision ids are picked up from prose
        if self._is_command(t):
            return self._command(doc, line, col, t, ctx, cwd=None)
        m = DEP_SPEC.match(t)
        if m:
            return [Claim("dep", t, m.group(1).lower(), doc.path, line, col, ctx,
                          {"spec": m.group(3).replace(" ", "")})]
        p = self._abs_in_root(t)
        if p is not None:
            return [Claim("path", t, p, doc.path, line, col, ctx, {"strength": 2, "anchor": "root"})]
        cleaned = clean_path_text(t)
        if "#" in cleaned and path_strength(cleaned.split("#", 1)[0]) == 2:
            cleaned = cleaned.split("#", 1)[0]      # `guide.md#install`: the file, and a place in it
        strength = path_strength(cleaned)
        if strength:
            return [Claim("path", t, cleaned, doc.path, line, col, ctx, {"strength": strength})]
        fm = re.fullmatch(r"(--[A-Za-z][A-Za-z0-9_-]*)(?:[= ].*)?", t)
        if fm:
            return [Claim("flag", t, fm.group(1), doc.path, line, col, ctx)]
        sym = self._symbol(t)
        if sym:
            return [Claim("symbol", t, sym[0], doc.path, line, col, ctx, {"parts": sym[1]})]
        return []

    def _abs_in_root(self, t: str) -> str | None:
        s = t.strip().strip("\"'").replace("\\", "/")
        if not self.root_abs or not re.match(r"^[A-Za-z]:/", s):
            return None
        if s.lower().startswith(self.root_abs + "/"):
            rel = s[len(self.root_abs) + 1:].rstrip("/")
            if rel and not has_placeholder(rel):
                return rel
        return None

    @staticmethod
    def _symbol(t: str):
        if not SYMBOL.match(t) or re.match(r"^v?\d", t):
            return None
        call = t.endswith(")")
        core = re.sub(r"\(.*\)$", "", t)
        parts = [p for p in re.split(r"\.|::|#", core) if p]
        if not parts:
            return None
        if len(parts) == 1:
            name = parts[0]
            if len(name) < 3 or name.lower() in KEYWORDS:
                return None
            has_us = "_" in name.strip("_")
            camel = bool(re.search(r"[a-z][A-Z]", name)) or bool(re.match(r"^[A-Z][a-z0-9]+[A-Z]", name))
            upper = name.isupper()
            if upper and not has_us and len(name) <= 5:
                return None         # API, JSON, HTTP...
            if not (call or has_us or camel or (upper and has_us)):
                return None         # plain words: designed, operational
            return name, [name]
        if parts[0].lower() in ("self", "this", "cls"):
            parts = parts[1:]
            if not parts:
                return None
        return parts[-1], parts

    # -- commands ----------------------------------------------------------
    @staticmethod
    def _is_command(t: str) -> bool:
        argv = split_cmd(PROMPT.sub("", t))
        if not argv:
            return False
        head = argv[0].replace("\\", "/")
        base = head.rsplit("/", 1)[-1].lower()
        if base in PY_RUNNERS or base in NODE_RUNNERS or base in ("make", "just", "cd", "pytest"):
            return len(argv) > 1 or base == "pytest"
        if base in PKG_RUNNERS:
            return len(argv) > 1
        if base in SHELL_RUNNERS and len(argv) > 1:
            return True
        if head.startswith(("./", "../")) and runnable(base):
            # a lone `../etc` in prose is a path value; `./configure` alone still runs
            return not (head.startswith("../") and len(argv) == 1 and "." not in base.lstrip("."))
        return base.endswith(CODE_EXT_FOR_CMD) and len(argv) > 1

    @staticmethod
    def _looks_shell(lines: list) -> bool:
        hits = 0
        for _, t in lines:
            s = PROMPT.sub("", t).strip()
            if not s or s.startswith("#"):
                continue
            word = s.split()[0].replace("\\", "/").rsplit("/", 1)[-1].lower()
            if word in PY_RUNNERS | NODE_RUNNERS | PKG_RUNNERS | {"make", "just", "cd", "pytest", "git", "pip", "uv"}:
                hits += 1
            else:
                return False
        return hits > 0

    def _shell_block(self, doc: Doc, lines: list, lang: str) -> list:
        out = []
        cwd = None
        joined: list = []
        buf, start = "", 0
        for n, t in lines:
            s = t.rstrip()
            if not buf:
                start = n
            if s.endswith((" \\", " `", " ^")):
                buf += s[:-1] + " "
                continue
            buf += s
            joined.append((start, buf))
            buf = ""
        if buf:
            joined.append((start, buf))
        for n, s in joined:
            s = PROMPT.sub("", s).strip()
            if not s or s.startswith(("#", "REM ", "rem ", "::", "//")):
                continue
            s = re.sub(r"\s+#\s.*$", "", s)        # trailing comment
            for part in split_compound(s):
                claims = self._command(doc, n, 1, part, "fence", cwd)
                for c in claims:
                    if c.extra.get("cd"):
                        cwd = c.target
                out.extend(claims)
        return out

    def _command(self, doc: Doc, line: int, col: int, t: str, ctx: str, cwd) -> list:
        argv = split_cmd(PROMPT.sub("", t))
        out: list[Claim] = []
        while argv and (re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", argv[0]) or argv[0] in ("sudo", "time", "&", "call", "exec")):
            argv = argv[1:]
        if not argv:
            return out
        head = argv[0].replace("\\", "/")
        base = head.rsplit("/", 1)[-1].lower()

        def path_claim(p: str, kind: str = "command", strength: int = 2, **extra):
            p2 = clean_path_text(p)
            if not p2 or has_placeholder(p2) or "://" in p2 or p2.startswith(("~", "/")) \
                    or re.match(r"^[A-Za-z]:/", p2) or p2 in (".", ".."):
                return None
            c = Claim(kind, p, p2, doc.path, line, col, ctx, {"strength": strength, "cwd": cwd, **extra})
            if p in argv and "." not in p2.rsplit("/", 1)[-1]:
                i = argv.index(p)
                alts = [clean_path_text(" ".join(argv[i:j])) for j in range(i + 2, min(len(argv), i + 6) + 1)]
                if alts:
                    c.extra["alts"] = alts
            out.append(c)
            return c

        if base == "cd" or base in ("pushd", "set-location"):
            if len(argv) > 1 and argv[1] not in ("-", "~", ".."):
                args = argv[2:] if argv[1].lower() == "/d" else argv[1:]
                target = " ".join(args)         # unquoted folder names with spaces
                c = path_claim(target, "path", 2)
                if c:
                    c.extra["cd"] = True
                    c.extra["dir"] = True
            return out
        if base in PY_RUNNERS or base.endswith(("python.exe", "pythonw.exe")) or base in ("python3.12", "python3.11", "python3.13"):
            self._python(argv, path_claim, out, doc, line, col, ctx, cwd)
            return out
        if base in NODE_RUNNERS:
            for a in argv[1:]:
                if not a.startswith("-"):
                    if a.lower().endswith((".js", ".mjs", ".cjs", ".ts", ".tsx", ".mts")):
                        path_claim(a)
                    break
            return out
        if base in PKG_RUNNERS and len(argv) > 1:
            sub = argv[1]
            name, bare = None, False
            if sub in ("run", "run-script") and len(argv) > 2:
                name = argv[2]
            elif sub in ("test", "start", "stop", "restart", "t"):
                name = "test" if sub == "t" else sub
            elif base in ("pnpm", "yarn", "bun") and sub not in PKG_BUILTINS and not sub.startswith("-"):
                name, bare = sub, True          # a script, or a tool in node_modules/.bin
            if name and not has_placeholder(name):
                out.append(Claim("npm", t, name, doc.path, line, col, ctx,
                                 {"cwd": cwd, "builtin": sub in ("start", "stop", "restart"), "bare": bare}))
            return out
        if base in ("make", "just"):
            for a in argv[1:]:
                if a.startswith("-") or "=" in a:
                    continue
                if not has_placeholder(a):
                    out.append(Claim("make", t, a, doc.path, line, col, ctx, {"cwd": cwd, "tool": base}))
                break
            return out
        if base == "pytest":
            self._pytest_args(argv[1:], path_claim)
            return out
        if base in SHELL_RUNNERS:
            for a in argv[1:]:
                if a.lower().endswith((".ps1", ".sh", ".bash", ".bat", ".cmd")):
                    path_claim(a)
                    break
            return out
        if (head.startswith(("./", "../")) and runnable(base)) or base.endswith(CODE_EXT_FOR_CMD):
            c = path_claim(head)
            if c and base.endswith(".py"):
                self._script_args(c, argv[1:])
            return out
        return out

    def _python(self, argv, path_claim, out, doc, line, col, ctx, cwd) -> None:
        i = 1
        while i < len(argv):
            a = argv[i]
            if a in ("-X", "-W", "-Q"):
                i += 2
                continue
            if re.match(r"^-(?:[23](?:\.\d+)?(?:-\d+)?|V:.*|[IuBOEsSqbdvPR]+|OO|bb|X.+|W.+)$", a):
                i += 1
                continue
            if a == "-c":
                return
            if a == "-m" and i + 1 < len(argv):
                mod = argv[i + 1]
                rest = argv[i + 2:]
                top = mod.split(".")[0]
                if top == "unittest":
                    self._unittest_args(rest, path_claim)
                elif top == "pytest":
                    self._pytest_args(rest, path_claim)
                elif top == "pip":
                    for j, r in enumerate(rest):
                        if r in ("-r", "--requirement", "-c", "--constraint") and j + 1 < len(rest):
                            path_claim(rest[j + 1], "command", 2)
                        elif r in ("-e", "--editable") and j + 1 < len(rest) and not rest[j + 1].startswith(("git+", "http")):
                            path_claim(rest[j + 1], "command", 1)
                elif top in PY_KNOWN_EXTERNAL or has_placeholder(mod):
                    pass
                else:
                    c = Claim("module", " ".join(argv), mod, doc.path, line, col, ctx, {"cwd": cwd})
                    out.append(c)
                    self._script_args(c, rest)
                return
            if a.startswith("-"):
                i += 1
                continue
            c = path_claim(a, "command", 2)
            if c and a.lower().endswith((".py", ".pyw")):
                self._script_args(c, argv[i + 1:])
            return

    @staticmethod
    def _script_args(claim: Claim, rest: list) -> None:
        flags = [r.split("=", 1)[0] for r in rest
                 if r.startswith("--") and len(r) > 2 and not has_placeholder(r)]
        pos = None          # a subcommand comes right after the script
        if rest and re.match(r"^[a-z][a-z0-9_-]*$", rest[0]):
            pos = rest[0]
        claim.extra["flags"] = flags
        claim.extra["first_arg"] = pos

    @staticmethod
    def _unittest_args(rest: list, path_claim) -> None:
        for j, r in enumerate(rest):
            if r in ("-s", "--start-directory", "-t", "--top-level-directory") and j + 1 < len(rest):
                c = path_claim(rest[j + 1], "command", 2)
                if c:
                    c.extra["dir"] = True

    @staticmethod
    def _pytest_args(rest: list, path_claim) -> None:
        skip_next = False
        for r in rest:
            if skip_next:
                skip_next = False
                continue
            if r in ("-k", "-m", "-p", "-o", "--rootdir", "--basetemp", "-W", "--junitxml", "--maxfail", "-n", "--tb", "--durations"):
                skip_next = True
                continue
            if r.startswith("-"):
                continue
            path = r.split("::", 1)[0]
            if "/" in path.replace("\\", "/") or path.endswith(".py") or path in ("tests", "test"):
                path_claim(path, "command", 2)

    # -- trees -------------------------------------------------------------
    @staticmethod
    def _is_tree(lines: list) -> bool:
        n = sum(1 for _, t in lines if re.search(r"[├└]|^\s*[|`+]--", t))
        return n >= 2

    def _tree(self, doc: Doc, ddir: str, lines: list) -> list:
        out = []
        stack: list = []      # [(col, rel)]
        base = None
        for n, raw in lines:
            if not raw.strip():
                continue
            i = 0
            while i < len(raw) and (raw[i] in TREE_GLYPHS or (raw[i] == "-" and i + 1 < len(raw) and raw[i + 1] in "-─ ")):
                i += 1
            rest = raw[i:]
            name = re.split(r"\s{2,}|\t| #| //| ←| <-| —| – ", rest, maxsplit=1)[0].strip()
            name = re.sub(r"\s*\(.*\)$", "", name).strip()
            if not name:
                continue
            if base is None:
                base_name = name.rstrip("/")
                if i == 0 and name.endswith("/") and not any(g in raw for g in "├└│"):
                    if posixpath.basename(ddir).lower() == base_name.lower():
                        base = ddir
                    else:
                        base = posixpath.join(ddir, base_name) if ddir else base_name
                    continue
                base = ddir
            while stack and stack[-1][0] >= i:
                stack.pop()
            if has_placeholder(name) or (" " in name and not name.endswith("/")):
                continue          # "...", "<repo>/", or a description, not an entry
            if TREE_JUNK.search(name) or not re.match(r"^[\w.@+~-]", name):
                continue          # arrows, boxes: a diagram, not a file tree
            parent = stack[-1][1] if stack else base
            rel = posixpath.normpath(posixpath.join(parent, name.rstrip("/"))) if parent else name.rstrip("/")
            stack.append((i, rel))
            out.append(Claim("path", name, rel, doc.path, n, i + 1, "tree",
                             {"strength": 2, "anchor": "exact", "dir": name.endswith("/")}))
        return out

    # -- links -------------------------------------------------------------
    @staticmethod
    def _link(doc: Doc, ln) -> Claim | None:
        dest = ln.dest.strip()
        if not dest or re.match(r"^[A-Za-z][A-Za-z0-9+.-]*:", dest) or dest.startswith("//"):
            return None
        target, _, anchor = dest.partition("#")
        target = target.split("?", 1)[0]
        try:
            from urllib.parse import unquote
            target = unquote(target)
        except Exception:
            pass
        if has_placeholder(target) and target:
            return None
        if TEMPLATE_VAR.fullmatch(target) and target not in CAPS_FILES:
            return None                 # `[text](ENGLISH_PAGE)`: a build step fills it in
        return Claim("link", dest, target, doc.path, ln.line, ln.col, "link",
                     {"anchor": anchor, "image": ln.image})
