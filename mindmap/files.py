"""Repository inventory: which files exist, which are docs, which are code.

Git-aware: lists tracked + untracked-but-not-ignored files, and descends into
nested repositories (a directory with its own `.git`) even when the outer
repo ignores them. Without git it walks the tree with sane default ignores.

Privacy: paths that look like secrets (`secret`, `credential`, `cookie`,
`.env`, keys) are never read, whatever the ignore files say.
"""

from __future__ import annotations

import os
import subprocess
import threading
from pathlib import Path

DOC_EXT = {".md", ".markdown", ".mdx"}
CODE_EXT = {
    ".py", ".pyi", ".pyw", ".js", ".mjs", ".cjs", ".jsx", ".ts", ".tsx", ".mts", ".cts",
    ".go", ".rs", ".java", ".kt", ".kts", ".cs", ".fs", ".vb", ".c", ".h", ".cc", ".cpp",
    ".hpp", ".hh", ".m", ".mm", ".rb", ".php", ".swift", ".scala", ".lua", ".dart", ".ex",
    ".exs", ".erl", ".clj", ".r", ".jl", ".zig", ".nim", ".sh", ".bash", ".zsh", ".fish",
    ".ps1", ".psm1", ".psd1", ".bat", ".cmd", ".sql", ".vue", ".svelte", ".astro",
    ".groovy", ".gradle", ".pl", ".pm",
}
CONF_EXT = {
    ".json", ".jsonc", ".json5", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".conf",
    ".txt", ".html", ".htm", ".css", ".scss", ".less", ".xml", ".proto", ".graphql",
    ".gql", ".tf", ".hcl", ".mk", ".cmake", ".properties", ".in", ".spec",
}
SPECIAL_CODE = {
    "makefile", "gnumakefile", "dockerfile", "justfile", "procfile", "rakefile",
    "gemfile", "vagrantfile", "jenkinsfile", "cmakelists.txt", "build", "workspace",
}
# Generated or vendored files: never part of "the code" a doc talks about.
SKIP_NAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "poetry.lock", "uv.lock",
    "cargo.lock", "composer.lock", "gemfile.lock", "go.sum", "pipfile.lock",
}
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", ".venv", "venv", "env", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", ".nox", ".cache",
    "dist", "build", "site-packages", "target", ".next", ".nuxt", ".idea",
    ".vscode", ".gradle", "bower_components", "vendor", "graphify-out", ".eggs",
}
KEEP_HIDDEN_DIRS = {".github", ".claude", ".cursor", ".gemini", ".codex", ".agents", ".windsurf"}
# Generated content that git may still list: never "the code" a doc talks about.
GENERATED_DIRS = {
    "node_modules", "__pycache__", ".venv", "venv", "site-packages", "graphify-out",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".tox", "dist", ".next", ".nuxt",
    "coverage", "htmlcov", ".eggs",
}
PRIVATE_NAMES = {".env", ".npmrc", ".pypirc", ".netrc", "id_rsa", "id_ed25519", "id_ecdsa",
                 "credentials.json", "cookies.txt", "cookies.json", "cookies.sqlite"}
PRIVATE_EXT = {".pem", ".key", ".p12", ".pfx", ".keystore", ".jks", ".kdbx", ".cookies"}
PRIVATE_DIRS = {"cookie", "cookies"}
COOKIE_DATA_EXT = {".txt", ".json", ".sqlite", ".db", ".pkl"}
MAX_DOC_BYTES = 3_000_000
MAX_CODE_BYTES = 1_500_000


GIT_PATIENCE = 3        # calls that may run out of time in one run; after that git is stuck, not slow
GIT_GRACE = 5.0         # seconds a stopped git gets to hand back its pipes
_git_lock = threading.Lock()
_git_late = {"late": 0, "skipped": 0}


def git_trouble(reset: bool = False) -> dict:
    """Since the last reset: git calls that ran out of time (`late`), and calls not made after
    `GIT_PATIENCE` of those (`skipped`). A run that has any of them is missing answers, and says so."""
    with _git_lock:
        seen = dict(_git_late)
        if reset:
            _git_late.update(late=0, skipped=0)
    return seen


def _stop(proc: subprocess.Popen) -> None:
    """End a git that ran out of time, with whatever it started. `git` can be a launcher for the real
    git, and an alias or a filter adds a shell: when only the first process is killed, the others keep
    our pipe open, and reading it to the end waits for them (22 minutes, once, on a 120 second limit)."""
    if os.name == "nt":
        try:
            subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
        except (OSError, subprocess.SubprocessError):
            pass
    try:
        proc.kill()
    except OSError:
        pass
    try:
        proc.communicate(timeout=GIT_GRACE)
    except (OSError, ValueError, subprocess.SubprocessError):
        pass            # something still holds the pipe: leave it, the run goes on


def run_git(args: list[str], cwd: Path, *, stdin: bytes | None = None,
            timeout: float = 120, ok_codes=(0,)) -> bytes | None:
    """Run git, return stdout bytes, or None if git failed, is missing or ran out of time.

    Git never reads the caller's own input: for the MCP server that is the protocol stream."""
    with _git_lock:
        if _git_late["late"] >= GIT_PATIENCE:
            _git_late["skipped"] += 1
            return None
    try:
        proc = subprocess.Popen(
            ["git", "-c", "core.quotepath=off", *args], cwd=str(cwd),
            stdin=subprocess.DEVNULL if stdin is None else subprocess.PIPE,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        )
    except OSError:
        return None
    try:
        out, _ = proc.communicate(stdin, timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(proc)
        with _git_lock:
            _git_late["late"] += 1
        return None
    except (OSError, subprocess.SubprocessError):
        _stop(proc)
        return None
    if proc.returncode not in ok_codes:
        return None
    return out


def is_private(rel: str) -> bool:
    """Files that may hold secret values. Mind Map never reads them."""
    low = rel.lower()
    parts = low.split("/")
    name = parts[-1]
    if name in PRIVATE_NAMES or name.startswith(".env."):
        return not name.endswith((".example", ".sample", ".template"))
    ext = os.path.splitext(name)[1]
    if ext in PRIVATE_EXT or ("cookie" in name and ext in COOKIE_DATA_EXT):
        return True
    return "secret" in low or not PRIVATE_DIRS.isdisjoint(parts[:-1])


def kind_of(rel: str) -> str:
    """'doc', 'code', 'conf' or '' (not text we care about)."""
    name = rel.rsplit("/", 1)[-1].lower()
    if name in SKIP_NAMES or name.endswith((".min.js", ".min.css", ".map")):
        return ""
    ext = os.path.splitext(name)[1]
    if ext in DOC_EXT:
        return "doc"
    if ext in CODE_EXT or name in SPECIAL_CODE:
        return "code"
    if ext in CONF_EXT:
        return "conf"
    return ""


class Inventory:
    """All files under `root` that Mind Map may look at."""

    def __init__(self, root: Path, *, use_git: bool = True, nested: bool = True,
                 exclude: list[str] | None = None):
        self.root = Path(root).resolve()
        self.use_git = use_git
        self.repos: dict[str, Path] = {}   # rel dir ('' = root) -> git top-level
        self.files: list[str] = []
        self.links: set[str] = set()       # symlinks: the path exists, the text belongs to another file
        self.exclude = exclude or []
        self._texts: dict[str, str | None] = {}
        seen: set[str] = set()
        if use_git and self._git_top(self.root):
            self._list_git(self.root, "", seen, nested)
        else:
            self._walk(seen)
        if self.exclude:
            from .globs import match_any
            self.files = [f for f in self.files if not match_any(f, self.exclude)]
        self.files.sort()
        self.file_set = set(self.files)
        self.docs = [f for f in self.files if kind_of(f) == "doc" and f not in self.links]
        self.code = [f for f in self.files if kind_of(f) in ("code", "conf") and f not in self.links
                     and not self._rendered_doc(f)]
        dirs: set[str] = set()
        for f in self.files:
            parts = f.split("/")[:-1]
            for i in range(1, len(parts) + 1):
                dirs.add("/".join(parts[:i]))
        self.dir_set = dirs

    # -- listing ---------------------------------------------------------
    @staticmethod
    def _git_top(path: Path) -> Path | None:
        out = run_git(["rev-parse", "--show-toplevel"], path, timeout=20)
        if not out:
            return None
        return Path(out.decode("utf-8", "replace").strip())

    def _list_git(self, base: Path, prefix: str, seen: set[str], nested: bool) -> None:
        top = self._git_top(base)
        if top is None:
            return
        self.repos[prefix.rstrip("/")] = top
        out = run_git(["ls-files", "-co", "--exclude-standard", "-z"], base)
        if out is None:
            return
        # git's own record of links: Windows checks a link out as a one-line text file, Linux as a real link
        modes = run_git(["ls-files", "-s", "-z"], base) or b""
        links = {raw.split(b"\t", 1)[-1].decode("utf-8", "replace")
                 for raw in modes.split(b"\0") if raw.startswith(b"120000 ")}
        nested_dirs: list[str] = []
        for raw in out.split(b"\0"):
            if not raw:
                continue
            rel = raw.decode("utf-8", "replace")
            if rel.endswith("/"):
                if (base / rel / ".git").exists():
                    nested_dirs.append(rel)
                continue
            full = prefix + rel
            if full in seen or is_private(full):
                continue
            if any(seg.lower() in GENERATED_DIRS for seg in rel.split("/")[:-1]):
                continue
            if rel in links or (base / rel).is_symlink():
                seen.add(full)
                self.files.append(full)
                self.links.add(full)
                continue
            if (base / rel / ".git").exists():   # submodule gitlink
                nested_dirs.append(rel + "/")
                continue
            if not (base / rel).is_file():        # tracked but deleted in the work tree
                continue
            seen.add(full)
            self.files.append(full)
        if nested:
            ign = run_git(["ls-files", "-o", "-i", "--exclude-standard", "--directory", "-z"], base)
            for raw in (ign or b"").split(b"\0"):
                rel = raw.decode("utf-8", "replace")
                if rel.endswith("/") and (base / rel / ".git").exists():
                    nested_dirs.append(rel)
            for rel in sorted(set(nested_dirs)):
                if is_private(prefix + rel):
                    continue
                self._list_git(base / rel, prefix + rel, seen, nested)

    def _walk(self, seen: set[str]) -> None:
        root = self.root
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in SKIP_DIRS
                and (not d.startswith(".") or d in KEEP_HIDDEN_DIRS)
            ]
            rel_dir = Path(dirpath).relative_to(root).as_posix()
            rel_dir = "" if rel_dir == "." else rel_dir + "/"
            for name in filenames:
                full = rel_dir + name
                if full in seen or is_private(full):
                    continue
                seen.add(full)
                self.files.append(full)
                if os.path.islink(os.path.join(dirpath, name)):
                    self.links.add(full)

    def _rendered_doc(self, rel: str) -> bool:
        """x.html next to x.md is a rendering of the doc, not code."""
        low = rel.lower()
        if not low.endswith((".html", ".htm")):
            return False
        stem = rel.rsplit(".", 1)[0]
        return any(stem + ext in self.file_set for ext in (".md", ".MD", ".markdown"))

    # -- access ----------------------------------------------------------
    def abspath(self, rel: str) -> Path:
        return self.root / rel

    def text(self, rel: str) -> str | None:
        """Decoded text of a doc/code file, or None (binary, too big, private)."""
        if rel in self._texts:
            return self._texts[rel]
        txt = None
        if not is_private(rel):
            limit = MAX_DOC_BYTES if kind_of(rel) == "doc" else MAX_CODE_BYTES
            try:
                p = self.root / rel
                if p.stat().st_size <= limit:
                    data = p.read_bytes()
                    if b"\0" not in data[:8192]:
                        txt = data.decode("utf-8", "replace")
            except OSError:
                txt = None
        if kind_of(rel) == "doc":
            self._texts[rel] = txt          # docs are small and read many times
        return txt

    def repo_of(self, rel: str) -> str:
        """Scan-root-relative dir of the git repo that owns `rel` ('' = root)."""
        best = ""
        for r in self.repos:
            if r and (rel == r or rel.startswith(r + "/")) and len(r) > len(best):
                best = r
        return best

    def exists(self, rel: str) -> bool:
        return rel in self.file_set or rel in self.dir_set
