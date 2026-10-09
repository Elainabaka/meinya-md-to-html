"""Index of the code: identifiers, definitions, CLI flags, manifests.

Everything is computed from file text with regular expressions from the
standard library. The index answers "does this name exist anywhere in the
code right now, and where?" quickly; deeper questions read the file again.
It is cached as JSON (never pickle) in the user cache folder, keyed by the
size and time of every code file, so repeated runs (hook, MCP) skip the build.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from bisect import bisect_right
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from .files import Inventory, kind_of

PY_DEF = re.compile(r"^[ \t]*(?:async[ \t]+)?def[ \t]+([A-Za-z_]\w*)|^[ \t]*class[ \t]+([A-Za-z_]\w*)", re.M)
PY_ASSIGN = re.compile(r"^([A-Za-z_]\w*)[ \t]*(?::[^=\n]*)?=(?!=)", re.M)
PY_IMPORT = re.compile(
    r"^[ \t]*(?:from[ \t]+([A-Za-z_][\w.]*)[ \t]+import\b|import[ \t]+([A-Za-z_][\w.]*(?:[ \t]*,[ \t]*[A-Za-z_][\w.]*)*))",
    re.M)


def newlines(text: str) -> list:
    return [i for i, ch in enumerate(text) if ch == "\n"]

IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
DASHED = re.compile(r"(?<![\w-])--?[A-Za-z][A-Za-z0-9_-]*")
JS_IMPORT = re.compile(r"""(?:from\s+|require\(\s*|import\(\s*|import\s+)["']([^"'./][^"']*)["']""")
JS_DEF = re.compile(
    r"(?:function\s*\*?\s+([A-Za-z_$][\w$]*)|class\s+([A-Za-z_$][\w$]*)"
    r"|(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=)"
)
GENERIC_DEF = re.compile(
    r"^\s*(?:pub\s+|export\s+|public\s+|private\s+|static\s+|async\s+)*"
    r"(?:def|fn|func|function|class|struct|enum|trait|interface|type|module|sub)\s+([A-Za-z_][\w]*)",
    re.MULTILINE,
)
PS_FUNC = re.compile(r"^\s*function\s+([A-Za-z][\w-]*)", re.IGNORECASE | re.MULTILINE)
BAT_LABEL = re.compile(r"^:([A-Za-z_][\w-]*)", re.MULTILINE)
MAKE_TARGET = re.compile(r"^([A-Za-z0-9_.][A-Za-z0-9_./-]*)\s*:(?!=)", re.MULTILINE)
JUST_RECIPE = re.compile(r"^@?([A-Za-z0-9_-]+)(?:\s+[^:=\n]*)?:(?!=)", re.MULTILINE)
REQ_LINE = re.compile(r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)\s*(\[[^\]]*\])?\s*([<>=!~].*?)?\s*(?:;.*)?(?:#.*)?$")
PY_TEST = re.compile(r"^\s*(?:async\s+)?def\s+test\w*\s*\(", re.MULTILINE)
JS_TEST = re.compile(r"^\s*(?:it|test)(?:\.each\([^)]*\))?\s*\(", re.MULTILINE)
VERSION_ASSIGN = re.compile(r"""^__version__\s*=\s*["']([^"']+)["']""", re.MULTILINE)


CACHE_VERSION = 1
STATE_SETS = ("dashed", "imports", "local_modules")


def cache_dir() -> Path:
    if os.environ.get("MINDMAP_CACHE_DIR"):
        return Path(os.environ["MINDMAP_CACHE_DIR"])
    base = os.environ.get("LOCALAPPDATA") or os.environ.get("XDG_CACHE_HOME") or str(Path.home() / ".cache")
    return Path(base) / "meinya-mind-map"


def stdlib_names() -> set:
    names = set(getattr(sys, "stdlib_module_names", ()))
    names |= set(sys.builtin_module_names)
    return names


class CodeIndex:
    @classmethod
    def cached(cls, inv: Inventory) -> "CodeIndex":
        """Load the index from the cache when no code file changed, else build and save it."""
        h = hashlib.sha1()
        h.update(str(CACHE_VERSION).encode())
        for rel in sorted(inv.files):
            h.update(rel.encode("utf-8", "replace") + b"\0")
        for rel in sorted(inv.code):
            try:
                st = (inv.root / rel).stat()
                h.update(f"{rel}\0{st.st_size}\0{st.st_mtime_ns}\n".encode("utf-8", "replace"))
            except OSError:
                h.update(f"{rel}\0-\n".encode("utf-8", "replace"))
        sig = h.hexdigest()
        path = cache_dir() / (hashlib.sha1(str(inv.root).lower().encode("utf-8")).hexdigest()[:16] + ".json")
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("v") == CACHE_VERSION and data.get("sig") == sig:
                return cls.from_state(inv, data["state"])
        except (OSError, ValueError, KeyError, TypeError):
            pass
        idx = cls(inv)
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"v": CACHE_VERSION, "sig": sig, "state": idx.to_state()}), encoding="utf-8")
            os.replace(tmp, path)
        except OSError:
            pass
        return idx

    def to_state(self) -> dict:
        st = {k: sorted(getattr(self, k)) for k in STATE_SETS}
        st.update(first_file=self.first_file, files=self.files, defs=self.defs, npm=self.npm,
                  make={k: sorted(v) for k, v in self.make.items()}, manifests=self.manifests,
                  pins=self.pins, tests=self.tests)
        return st

    @classmethod
    def from_state(cls, inv: Inventory, st: dict) -> "CodeIndex":
        idx = cls.__new__(cls)
        idx.inv = inv
        idx._nl_text, idx._nl = None, []
        for k in STATE_SETS:
            setattr(idx, k, set(st[k]))
        idx.first_file = st["first_file"]
        idx.files = st["files"]
        idx.defs = {k: [tuple(x) for x in v] for k, v in st["defs"].items()}
        idx.npm = st["npm"]
        idx.make = {k: set(v) for k, v in st["make"].items()}
        idx.manifests = st["manifests"]
        idx.pins = st["pins"]
        idx.tests = st["tests"]
        return idx

    def __init__(self, inv: Inventory):
        self.inv = inv
        self.first_file: dict[str, int] = {}     # identifier -> index into self.files
        self.files: list[str] = []
        self.dashed: set[str] = set()            # every --flag / -f literal in code
        self.defs: dict[str, list] = {}          # name -> [(path, line, kind)]
        self.imports: set[str] = set()           # top-level external modules/packages
        self.local_modules: set[str] = set()     # importable names defined by the repo
        self.npm: dict[str, dict] = {}           # package.json path -> {"scripts": {...}, "version": ...}
        self.make: dict[str, set] = {}           # Makefile/justfile path -> targets
        self.manifests: dict[str, dict] = {}     # dir -> {"file": path, "version": v}
        self.pins: dict[str, dict] = {}          # requirements/pyproject path -> {pkg: spec}
        self.tests: dict[str, int] = {}          # test file -> number of tests
        self._nl_text: str | None = None
        self._nl: list = []
        self._build()

    # ------------------------------------------------------------------
    def _read_all(self):
        """(path, text) of every code file, in the order of the inventory. Eight are read at a time: where
        each open is scanned (Windows with an antivirus) the first read of a tree takes 9.5 ms a file in
        a loop and 1.3 ms this way."""
        code = list(self.inv.code)
        with ThreadPoolExecutor(max_workers=8) as pool:
            for i in range(0, len(code), 256):          # a part at a time: the texts are not all held at once
                part = code[i:i + 256]
                yield from zip(part, pool.map(self.inv.text, part))

    def _build(self) -> None:
        for rel, text in self._read_all():
            if text is None:
                continue
            idx = len(self.files)
            self.files.append(rel)
            first = self.first_file
            for tok in set(IDENT.findall(text)):
                if tok not in first:
                    first[tok] = idx
            if "-" in text:
                self.dashed.update(DASHED.findall(text))
            low = rel.lower()
            name = low.rsplit("/", 1)[-1]
            if low.endswith((".py", ".pyi", ".pyw")):
                self._python(rel, text)
            elif low.endswith((".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts", ".vue", ".svelte")):
                self._js(rel, text)
            elif low.endswith((".ps1", ".psm1")):
                for m in PS_FUNC.finditer(text):
                    self._def(m.group(1), rel, self._lineno(text, m.start()), "function")
            elif low.endswith((".bat", ".cmd")):
                for m in BAT_LABEL.finditer(text):
                    self._def(m.group(1), rel, self._lineno(text, m.start()), "label")
            elif kind_of(rel) == "code":
                for m in GENERIC_DEF.finditer(text):
                    self._def(m.group(1), rel, self._lineno(text, m.start()), "def")
            if name == "package.json":
                self._package_json(rel, text)
            elif name == "pyproject.toml":
                self._pyproject(rel, text)
            elif name in ("makefile", "gnumakefile") or name.endswith(".mk"):
                self.make[rel] = {m.group(1) for m in MAKE_TARGET.finditer(text) if not m.group(1).startswith(".")}
            elif name == "justfile":
                self.make[rel] = {m.group(1) for m in JUST_RECIPE.finditer(text)}
            elif name.startswith("requirements") and name.endswith((".txt", ".in")):
                self.pins[rel] = self._requirements(text)
            elif name in ("capability.json", "manifest.json", "app.json", "plugin.json"):
                self._json_manifest(rel, text)
            elif name == "cargo.toml":
                self._toml_version(rel, text)
            self._count_tests(rel, low, text)
        for rel in self.inv.files:
            low = rel.lower()
            if low.endswith(".py"):
                parts = rel[:-3].split("/")
                self.local_modules.add(parts[-1])
                if parts[-1] == "__init__" and len(parts) > 1:
                    self.local_modules.add(parts[-2])
            elif low.endswith((".js", ".ts", ".mjs", ".cjs")):
                self.local_modules.add(rel.rsplit("/", 1)[-1].rsplit(".", 1)[0])

    def _lineno(self, text: str, pos: int) -> int:
        if text is not self._nl_text:
            self._nl_text, self._nl = text, newlines(text)
        return bisect_right(self._nl, pos) + 1

    def _def(self, name: str, rel: str, line: int, kind: str) -> None:
        self.defs.setdefault(name, []).append((rel, line, kind))

    def _python(self, rel: str, text: str) -> None:
        # Regexes, not ast: ten times faster and good enough to say "defined here".
        nl = None
        for m in PY_DEF.finditer(text):
            if nl is None:
                nl = newlines(text)
            name = m.group(1) or m.group(2)
            self._def(name, rel, bisect_right(nl, m.start()) + 1, "function" if m.group(1) else "class")
        for m in PY_ASSIGN.finditer(text):
            if nl is None:
                nl = newlines(text)
            self._def(m.group(1), rel, bisect_right(nl, m.start()) + 1, "variable")
        for m in PY_IMPORT.finditer(text):
            if m.group(1):
                self.imports.add(m.group(1).split(".")[0])
            else:
                for part in m.group(2).split(","):
                    self.imports.add(part.strip().split(".")[0].split(" ")[0])
        vm = VERSION_ASSIGN.search(text)
        if vm:
            self._set_manifest(rel, vm.group(1), weak=True)

    def _js(self, rel: str, text: str) -> None:
        for m in JS_IMPORT.finditer(text):
            spec = m.group(1)
            if spec.startswith("@"):
                spec = "/".join(spec.split("/")[:2])
            else:
                spec = spec.split("/")[0]
            if spec and not spec.startswith("node:"):
                self.imports.add(spec)
        for m in JS_DEF.finditer(text):
            name = m.group(1) or m.group(2) or m.group(3)
            if name:
                self._def(name, rel, self._lineno(text, m.start()), "def")

    def _package_json(self, rel: str, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        if not isinstance(data, dict):
            return
        scripts = data.get("scripts") if isinstance(data.get("scripts"), dict) else {}
        self.npm[rel] = {"scripts": scripts, "name": data.get("name")}
        if isinstance(data.get("version"), str):
            self._set_manifest(rel, data["version"])
        deps = {}
        for key in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
            if isinstance(data.get(key), dict):
                deps.update({k: str(v) for k, v in data[key].items()})
        if deps:
            self.pins[rel] = deps
        for k in deps:
            self.imports.add(k)

    def _pyproject(self, rel: str, text: str) -> None:
        try:
            import tomllib
        except ImportError:          # Python 3.10: only the version, by regex
            m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
            if m:
                self._set_manifest(rel, m.group(1))
            return
        try:
            data = tomllib.loads(text)
        except Exception:
            return
        proj = data.get("project") or {}
        poetry = (data.get("tool") or {}).get("poetry") or {}
        version = proj.get("version") or poetry.get("version")
        if isinstance(version, str):
            self._set_manifest(rel, version)
        pins = {}
        for dep in proj.get("dependencies") or []:
            m = REQ_LINE.match(str(dep))
            if m:
                pins[m.group(1).lower()] = (m.group(3) or "").replace(" ", "")
        if pins:
            self.pins[rel] = pins

    def _toml_version(self, rel: str, text: str) -> None:
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        if m:
            self._set_manifest(rel, m.group(1))

    def _json_manifest(self, rel: str, text: str) -> None:
        try:
            data = json.loads(text)
        except ValueError:
            return
        if isinstance(data, dict) and isinstance(data.get("version"), str):
            self._set_manifest(rel, data["version"])

    def _set_manifest(self, rel: str, version: str, weak: bool = False) -> None:
        d = rel.rsplit("/", 1)[0] if "/" in rel else ""
        if weak:
            # __version__ in pkg/__init__.py describes the project one level up
            d = d.rsplit("/", 1)[0] if "/" in d else ""
            if d in self.manifests:
                return
        self.manifests[d] = {"file": rel, "version": version}

    @staticmethod
    def _requirements(text: str) -> dict:
        pins = {}
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith(("#", "-")):
                continue
            m = REQ_LINE.match(line)
            if m:
                pins[m.group(1).lower()] = (m.group(3) or "").replace(" ", "")
        return pins

    def _count_tests(self, rel: str, low: str, text: str) -> None:
        name = low.rsplit("/", 1)[-1]
        if low.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py")):
            self.tests[rel] = len(PY_TEST.findall(text))
        elif re.search(r"\.(test|spec)\.[cm]?[jt]sx?$", name) or "/__tests__/" in low:
            self.tests[rel] = len(JS_TEST.findall(text))

    # -- queries ---------------------------------------------------------
    def has(self, name: str) -> bool:
        return name in self.first_file

    def where(self, name: str) -> tuple | None:
        """(path, line) of the best place that mentions `name` (a definition if any)."""
        d = self.defs.get(name)
        if d:
            return d[0][0], d[0][1]
        idx = self.first_file.get(name)
        if idx is None:
            return None
        rel = self.files[idx]
        text = self.inv.text(rel) or ""
        m = re.search(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])", text)
        line = self._lineno(text, m.start()) if m else 1
        return rel, line

    def manifest_for(self, doc_dir: str) -> dict | None:
        return self.manifests.get(doc_dir)

    def tests_under(self, d: str) -> int:
        pre = d + "/" if d else ""
        return sum(n for f, n in self.tests.items() if f.startswith(pre))
