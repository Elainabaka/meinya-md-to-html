"""Tiny git repos for the Mind Map tests: write files, commit them at fixed dates."""

from __future__ import annotations

import atexit
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

GIT_ENV = {
    "GIT_AUTHOR_NAME": "test", "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test", "GIT_COMMITTER_EMAIL": "test@example.com",
    "GIT_CONFIG_NOSYSTEM": "1",
}
def remove_tree(path) -> None:
    """rmtree that also removes git's read-only object files on Windows."""
    def force(func, p, _exc):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    if sys.version_info >= (3, 12):
        shutil.rmtree(path, onexc=force)
    else:
        shutil.rmtree(path, onerror=force)


_CACHE = tempfile.mkdtemp(prefix="mindmap-cache-")
os.environ["MINDMAP_CACHE_DIR"] = _CACHE     # never write the index cache into the real user folder
atexit.register(lambda: remove_tree(_CACHE) if os.path.isdir(_CACHE) else None)


class Repo:
    def __init__(self, git: bool = True):
        self.root = Path(tempfile.mkdtemp(prefix="mindmap-test-")).resolve()
        self.day = 0
        if git:
            self.git("init", "-q")
            self.git("config", "core.autocrlf", "false")
            self.git("config", "commit.gpgsign", "false")

    def git(self, *args: str) -> str:
        env = dict(os.environ, **GIT_ENV)
        stamp = f"2026-01-{self.day + 1:02d}T12:00:00+00:00"
        env["GIT_AUTHOR_DATE"] = env["GIT_COMMITTER_DATE"] = stamp
        out = subprocess.run(["git", *args], cwd=self.root, env=env, capture_output=True)
        if out.returncode:
            raise RuntimeError(out.stderr.decode("utf-8", "replace"))
        return out.stdout.decode("utf-8", "replace")

    def write(self, rel: str, text: str) -> "Repo":
        p = self.root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8", newline="\n")
        return self

    def remove(self, rel: str) -> "Repo":
        (self.root / rel).unlink()
        return self

    def commit(self, msg: str = "change") -> "Repo":
        self.day += 1
        self.git("add", "-A")
        self.git("commit", "-q", "-m", msg)
        return self

    def mv(self, a: str, b: str) -> "Repo":
        (self.root / b).parent.mkdir(parents=True, exist_ok=True)
        self.git("mv", a, b)
        return self

    def cleanup(self) -> None:
        if self.root.is_dir():
            remove_tree(self.root)


def run(repo: Repo, **kw):
    from mindmap import engine
    return engine.run(repo.root, **kw)


def rules(res, path: str | None = None) -> list:
    """[(rule, severity, path, line)] for quick asserts."""
    return [(f.rule, f.severity, f.path, f.line) for f in res.findings if path is None or f.path == path]
