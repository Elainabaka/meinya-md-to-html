from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import webview

from mdhtml import cache
from mdhtml.bridge import preview_stats, render_text, run_convert, suggest_output

STATE_NAME = ".md_to_html_state.json"
INBOX_NAME = ".drop_inbox"
CACHE_DIR_NAME = ".cache"
LEGACY_HOME_STATE = Path.home() / ".md_to_html.json"
MAX_DROP_BYTES = 20_000_000
WATCH_INTERVAL = 1.2
CACHE_PRUNE_DAYS = 30

DEFAULT_SETTINGS = {"eyebrow": "Tài liệu kỹ thuật", "lang": "vi", "no_toc": False, "date": ""}


def _open_path(path: str):
    if sys.platform == "win32":
        os.startfile(path)  # noqa: S606 -- local user-selected folder
    elif sys.platform == "darwin":
        subprocess.Popen(["open", path])
    else:
        subprocess.Popen(["xdg-open", path])


def _reveal_path(path: str):
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", path])  # noqa: S603,S607
    else:
        _open_path(str(Path(path).parent))


def _file_brief(path: Path) -> dict:
    return {"name": path.name, "path": str(path), "stats": preview_stats(str(path))}


def _norm_key(path) -> str:
    try:
        return os.path.normcase(str(Path(path).resolve()))
    except OSError:
        return os.path.normcase(str(Path(path).absolute()))


def _tool_version(root: Path) -> str:
    """Version duy nhat tu capability.json (single source of truth)."""
    try:
        return json.loads((root / "capability.json").read_text("utf-8"))["version"]
    except Exception:
        return "2.2.0"


def _sanitize_settings(settings: dict | None) -> dict:
    s = settings or {}
    return {
        "title": str(s.get("title", "")).strip(),
        "eyebrow": str(s.get("eyebrow", "")).strip(),
        "lang": (str(s.get("lang", "vi")).strip() or "vi"),
        "no_toc": bool(s.get("no_toc", False)),
        "date": str(s.get("date", "")).strip(),
    }


class MdHtmlAPI:
    """Backend cho UI pywebview. Frontend goi qua window.pywebview.api.*."""

    def __init__(self, root: Path):
        self._root = root
        self._state_file = root / STATE_NAME
        self._window = None
        self._files: list[Path] = []
        self._output_dir: Path | None = None
        self._job_lock = threading.Lock()
        self._render_lock = threading.Lock()
        self._job: dict[str, Any] = {
            "running": False, "kind": "", "done": 0, "total": 0, "current": "",
            "outputs": [], "errors": [], "cancelled": False,
        }
        self._cancel = threading.Event()
        self._status: dict[str, dict] = {}
        self._seen: dict[str, tuple] = {}
        self._pending: dict[str, tuple] = {}
        self._rev = 0
        self._settings: dict = {}
        self._saved = self._load_state()
        saved_output = self._saved.get("output_dir")
        if saved_output and Path(saved_output).is_dir():
            self._output_dir = Path(saved_output)
        self._cache_mode = self._saved.get("cache_mode", "beside")
        if self._cache_mode not in cache.CACHE_MODES:
            self._cache_mode = "beside"
        self._watch_enabled = bool(self._saved.get("watch", True))
        self._prune_inbox()
        self._prune_cache()
        self._stop = threading.Event()
        threading.Thread(target=self._watch_loop, name="mdhtml-watch", daemon=True).start()

    def bind_window(self, window):
        self._window = window

    def close(self):
        self._stop.set()

    # -- state --
    def _load_state(self) -> dict:
        try:
            return json.loads(self._state_file.read_text("utf-8"))
        except Exception:
            pass
        # Migrate 1 lan tu settings thoi Tkinter (v1.x).
        try:
            if LEGACY_HOME_STATE.is_file():
                old = json.loads(LEGACY_HOME_STATE.read_text("utf-8"))
                return {
                    "output_dir": old.get("out_dir", ""),
                    "settings": {
                        "eyebrow": old.get("eyebrow", ""),
                        "lang": old.get("lang", "vi"),
                        "no_toc": bool(old.get("no_toc", False)),
                        "date": "",
                    },
                }
        except Exception:
            pass
        return {}

    def _save_state(self, extra: dict | None = None):
        state = dict(self._saved)
        state.update({
            "output_dir": str(self._output_dir) if self._output_dir else "",
            "cache_mode": self._cache_mode,
            "watch": self._watch_enabled,
        })
        if extra:
            state.update(extra)
        self._saved = state
        try:
            self._state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), "utf-8")
        except Exception:
            pass

    def initial_state(self):
        return {
            "files": self._files_payload(include_stats=True),
            "output_dir": str(self._output_dir) if self._output_dir else "",
            "settings": self._saved.get("settings", dict(DEFAULT_SETTINGS)),
            "cache_mode": self._cache_mode,
            "watch": self._watch_enabled,
            "revision": self._rev,
            "version": _tool_version(self._root),
        }

    def _files_payload(self, include_stats: bool = False) -> list:
        out = []
        for p in self._files:
            item = _file_brief(p) if include_stats else {"name": p.name, "path": str(p), "stats": ""}
            item.update(self._rec(p, create=False))
            out.append(item)
        return out

    def _rec(self, path, create: bool = True) -> dict:
        key = _norm_key(path)
        rec = self._status.get(key)
        if rec is None and create:
            rec = {
                "state": "pending", "out": "", "fallback": False, "msg": "",
                "mtime": 0, "size": 0, "hash": "", "revision": 0, "at": 0.0, "stats": "",
            }
            self._status[key] = rec
        return rec or {}

    def cache_root(self) -> Path:
        return self._root / CACHE_DIR_NAME / "html"

    def _prune_cache(self):
        """Don cache cu (chi trong cache root cua tool)."""
        try:
            root = self.cache_root()
            if not root.is_dir():
                return
            cutoff = time.time() - CACHE_PRUNE_DAYS * 86400
            for old in root.rglob("*"):
                try:
                    if old.is_file() and old.stat().st_mtime < cutoff:
                        old.unlink()
                except OSError:
                    pass
            for d in sorted(root.rglob("*"), reverse=True):
                try:
                    if d.is_dir() and not any(d.iterdir()):
                        d.rmdir()
                except OSError:
                    pass
        except OSError:
            pass

    # -- dialogs (native, qua webview window) --
    def _file_dialog(self, *, multiple=False):
        if not self._window:
            return []
        file_types = ("Markdown (*.md)", "All files (*.*)")
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.OPEN, allow_multiple=multiple, file_types=file_types)
        except Exception:
            try:
                result = self._window.create_file_dialog(
                    webview.OPEN_DIALOG, allow_multiple=multiple, file_types=file_types)
            except Exception:
                return []
        if not result:
            return []
        if isinstance(result, str):
            return [result]
        return list(result)

    def _folder_dialog(self):
        if not self._window:
            return None
        try:
            result = self._window.create_file_dialog(webview.FileDialog.FOLDER)
        except Exception:
            try:
                result = self._window.create_file_dialog(webview.FOLDER_DIALOG)
            except Exception:
                return None
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    def _save_dialog(self, default_name: str, directory: str):
        if not self._window:
            return None
        try:
            result = self._window.create_file_dialog(
                webview.FileDialog.SAVE, directory=directory or "",
                save_filename=default_name, file_types=("HTML (*.html)",))
        except Exception:
            try:
                result = self._window.create_file_dialog(
                    webview.SAVE_DIALOG, directory=directory or "",
                    save_filename=default_name, file_types=("HTML (*.html)",))
            except Exception:
                return None
        if not result:
            return None
        if isinstance(result, (list, tuple)):
            return str(result[0]) if result else None
        return str(result)

    # -- queue --
    def _merge_files(self, paths):
        existing = set()
        for p in self._files:
            existing.add(_norm_key(p))
        for raw in paths:
            p = Path(raw)
            if p.suffix.lower() != ".md" or not p.is_file():
                if p.is_dir():
                    for child in sorted(p.glob("*.md")):
                        self._merge_files([str(child)])
                continue
            key = _norm_key(p)
            if key not in existing:
                existing.add(key)
                self._files.append(p)

    def _schedule_sync(self):
        """Auto-cache: render nen cho moi file vua vao queue (chi khi co UI)."""
        if self._window is None or not self._files:
            return
        with self._job_lock:
            if self._job.get("running"):
                return
        self.sync_all(self._settings or self._saved.get("settings", {}))

    def add_files(self):
        self._merge_files(self._file_dialog(multiple=True))
        self._schedule_sync()
        return self._files_payload()

    def add_folder(self, recursive: bool = False):
        folder = self._folder_dialog()
        if folder:
            base = Path(folder)
            pat = "**/*.md" if recursive else "*.md"
            try:
                self._merge_files([str(p) for p in sorted(base.glob(pat)) if p.is_file()])
            except OSError:
                pass
        self._schedule_sync()
        return self._files_payload()

    def _inbox(self) -> Path:
        return self._root / INBOX_NAME

    def _prune_inbox(self):
        try:
            inbox = self._inbox()
            if not inbox.is_dir():
                return
            now = time.time()
            for old in inbox.iterdir():
                try:
                    if old.is_file() and now - old.stat().st_mtime > 7 * 86400:
                        old.unlink()
                except OSError:
                    pass
        except OSError:
            pass

    def _drop_staged(self, path: Path):
        """Xoa file staged (.drop_inbox) khi roi queue — ca cache .html cua no."""
        try:
            inbox = self._inbox().resolve()
            target = path.resolve()
            if inbox not in target.parents or not target.is_file():
                return
            with self._job_lock:
                running = bool(self._job.get("running"))
            if running:
                return
            cached = target.with_suffix(".html")
            for f in (cached, cached.with_suffix(".html.tmp"), target):
                try:
                    if f.is_file():
                        f.unlink()
                except OSError:
                    pass
            self._status.pop(_norm_key(target), None)
            self._seen.pop(_norm_key(target), None)
            self._pending.pop(_norm_key(target), None)
        except OSError:
            pass

    def add_dropped_files(self, files):
        """Nhan file keo-tha dang text {name, text} (fallback khi renderer khong
        lo path that; duong chinh la add_dropped_paths qua DOM drop event)."""
        inbox = self._inbox()
        try:
            inbox.mkdir(parents=True, exist_ok=True)
        except OSError:
            return {"files": self._files_payload(), "added": 0}
        self._prune_inbox()
        fresh: list[str] = []
        for item in files or []:
            try:
                if not isinstance(item, dict):
                    continue
                text = item.get("text") or ""
                if not text or len(text) > MAX_DROP_BYTES:
                    continue
                name = Path(str(item.get("name") or "dropped.md")).name.strip()
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name)[:120] or "dropped.md"
                if not name.lower().endswith(".md"):
                    name = f"{Path(name).stem or 'dropped'}.md"
                dest = inbox / name
                raw_bytes = text.encode("utf-8")
                if self._queue_has_bytes(raw_bytes):
                    continue
                if dest.is_file():
                    try:
                        same = dest.read_bytes() == raw_bytes
                    except OSError:
                        same = False
                    if not same:
                        i = 2
                        while True:
                            cand = inbox / f"{Path(name).stem}_{i}.md"
                            if not cand.exists():
                                dest = cand
                                break
                            i += 1
                        dest.write_bytes(raw_bytes)
                else:
                    dest.write_bytes(raw_bytes)
                fresh.append(str(dest))
            except Exception:
                continue
        before = len(self._files)
        if fresh:
            self._merge_files(fresh)
        self._schedule_sync()
        return {"files": self._files_payload(), "added": len(self._files) - before}

    @staticmethod
    def _norm_bytes(data: bytes) -> bytes:
        # Windows tu dich \n -> \r\n khi ghi text: so sanh sau normalize.
        return data.replace(b"\r\n", b"\n")

    def _queue_has_bytes(self, data: bytes) -> bool:
        """True neu 1 file trong queue co noi dung giong het (de tranh staged trung)."""
        if len(data) > MAX_DROP_BYTES:
            return False
        want = self._norm_bytes(data)
        for p in self._files:
            try:
                if p.is_file() and abs(p.stat().st_size - len(data)) <= 1024 \
                        and self._norm_bytes(p.read_bytes()) == want:
                    return True
            except OSError:
                continue
        return False

    def add_dropped_paths(self, paths):
        """Drop-native: nhan full path that tu OS (pywebview DOM drop event)."""
        picked: list[str] = []
        for raw in paths or []:
            try:
                p = Path(str(raw))
            except Exception:
                continue
            if p.suffix.lower() == ".md" and p.is_file():
                picked.append(str(p))
        before = len(self._files)
        if picked:
            self._merge_files(picked)
        added = len(self._files) - before
        if picked:
            self._drop_staged_duplicates_of(picked)
        self._schedule_sync()
        return {"files": self._files_payload(), "added": added}

    def _drop_staged_duplicates_of(self, real_paths) -> None:
        """Go queue entry staged (.drop_inbox) co bytes giong file that vua them.
        Chi xoa staged, khong bao gio xoa file that cua user."""
        try:
            inbox = self._inbox().resolve()
        except OSError:
            return
        for raw in real_paths:
            try:
                rp = Path(str(raw)).resolve()
                if rp.suffix.lower() != ".md" or not rp.is_file():
                    continue
                if rp.stat().st_size > MAX_DROP_BYTES + 1024:
                    continue
                data = self._norm_bytes(rp.read_bytes())
            except OSError:
                continue
            keep: list[Path] = []
            for p in self._files:
                try:
                    tp = p.resolve()
                except OSError:
                    keep.append(p)
                    continue
                if inbox in tp.parents and tp != rp:
                    try:
                        if tp.is_file() and abs(tp.stat().st_size - len(data)) <= 1024 \
                                and self._norm_bytes(tp.read_bytes()) == data:
                            try:
                                tp.unlink()
                            except OSError:
                                pass
                            continue
                    except OSError:
                        pass
                keep.append(p)
            self._files = keep

    def remove_file(self, index: int):
        try:
            removed = self._files.pop(int(index))
        except Exception:
            removed = None
        if removed is not None:
            self._drop_staged(removed)
        return self._files_payload()

    def clear_files(self):
        removed, self._files = list(self._files), []
        for p in removed:
            self._drop_staged(p)
        return []

    def file_stats(self, index: int):
        try:
            p = self._files[int(index)]
        except Exception:
            return {"ok": False, "error": "Chưa chọn file."}
        return {"ok": True, "stats": preview_stats(str(p)), "name": p.name}

    # -- options --
    def _cleanup_beside_caches(self):
        """Doi sang mode 'tool': go cac .html do tool tao canh file .md
        (chi xoa khi con marker cua tool dung cho chinh file do)."""
        for p in self._files:
            target = Path(cache.cache_target(p, "beside", self.cache_root()))
            try:
                if not target.is_file():
                    continue
                text = target.read_text(encoding="utf-8", errors="replace")
                marker = cache.read_marker(text)
                if marker and marker.get("src") == p.name:
                    target.unlink()
            except OSError:
                continue

    def set_options(self, cache_mode: str | None = None, watch: bool | None = None):
        changed = False
        if cache_mode in cache.CACHE_MODES and cache_mode != self._cache_mode:
            if cache_mode == "tool":
                self._cleanup_beside_caches()
            self._cache_mode = cache_mode
            changed = True
        if watch is not None and bool(watch) != self._watch_enabled:
            self._watch_enabled = bool(watch)
            changed = True
        if changed:
            self._save_state()
            if self._files and self._window is not None:
                self.sync_all(self._settings or self._saved.get("settings", {}), force=True)
        return {"ok": True, "cache_mode": self._cache_mode, "watch": self._watch_enabled}

    # -- cache / preview --
    def _render_one(self, src: Path, settings: dict, force: bool = False) -> dict:
        with self._render_lock:
            res = cache.ensure(src, settings, mode=self._cache_mode,
                               cache_dir=self.cache_root(), force=force)
        rec = self._rec(src)
        if res.get("ok"):
            if res.get("state") == "rendered":
                try:
                    rec["hash"] = cache.content_hash(src)
                except OSError:
                    pass
                rec["revision"] = int(rec.get("revision", 0)) + 1
            rec.update(state="fresh", out=res.get("path", ""), fallback=bool(res.get("fallback")),
                       msg="", mtime=int(res.get("mtime", 0)), size=int(res.get("size", 0)),
                       out_size=int(res.get("out_size", 0)),
                       stats=str(res.get("stats", "") or rec.get("stats", "")), at=time.time())
            self._seen[_norm_key(src)] = (int(res.get("mtime", 0)), int(res.get("size", 0)))
        else:
            rec.update(state=str(res.get("state", "error")), msg=str(res.get("msg", "")),
                       fallback=bool(res.get("fallback")))
        self._rev += 1
        return res

    def _file_url(self, path: str, token="0") -> str:
        try:
            uri = Path(path).resolve().as_uri()
        except ValueError:
            return ""
        return f"{uri}?v={token}"

    def preview_info(self, index: int, settings: dict):
        """Ensure cache cho file index roi tra URL file .html cho iframe."""
        try:
            p = self._files[int(index)]
        except Exception:
            return {"ok": False, "error": "Chưa có file để xem."}
        s = _sanitize_settings(settings)
        self._settings = s
        self._save_state({"settings": s})
        res = self._render_one(p, s)
        rec = self._rec(p, create=False)
        if res.get("ok"):
            return {
                "ok": True, "name": p.name, "path": str(p), "out": res.get("path", ""),
                "url": self._file_url(res.get("path", ""),
                                      f"{int(rec.get('revision', 0))}-{int(res.get('mtime', 0))}"),
                "stats": str(res.get("stats", "") or preview_stats(str(p))),
                "state": res.get("state", "fresh"), "fallback": bool(res.get("fallback")),
                "revision": int(rec.get("revision", 0)), "date": str(res.get("date", "")),
                "out_size": int(rec.get("out_size", 0)),
            }
        # Khong ghi duoc cache (quyen/od) -> render inline de van xem duoc.
        try:
            md_text = p.read_text(encoding="utf-8-sig")
        except OSError as exc:
            return {"ok": False, "error": f"Không đọc được file: {exc}"}
        single = len(self._files) == 1
        inline = render_text(
            md_text, p.name, title=(s["title"] if single else ""), eyebrow=s["eyebrow"],
            lang=s["lang"], no_toc=s["no_toc"], date_str=s["date"])
        if not inline.get("ok"):
            return {"ok": False, "error": str(inline.get("error") or res.get("msg") or "Lỗi render.")}
        return {"ok": True, "inline": True, "html": inline["html"], "stats": inline["stats"],
                "name": p.name, "path": str(p), "out": "", "url": "", "state": "inline",
                "fallback": True, "revision": int(rec.get("revision", 0)),
                "error": res.get("msg", "")}

    def get_preview(self, index: int, settings: dict):
        """Legacy: render truc tiep khong ghi cache (fallback + test)."""
        try:
            p = self._files[int(index)]
        except Exception:
            return {"ok": False, "error": "Chưa có file để preview."}
        try:
            md_text = p.read_text(encoding="utf-8-sig")
        except OSError as exc:
            return {"ok": False, "error": f"Không đọc được file: {exc}"}
        s = settings or {}
        single = len(self._files) == 1
        res = render_text(
            md_text, p.name,
            title=(str(s.get("title", "")).strip() if single else ""),
            eyebrow=str(s.get("eyebrow", "")), lang=str(s.get("lang", "vi")),
            no_toc=bool(s.get("no_toc", False)), date_str=str(s.get("date", "")),
        )
        if not res.get("ok"):
            return res
        res["name"] = p.name
        self._save_state({"settings": _sanitize_settings(s)})
        return res

    def watch_poll(self):
        """Poll trang thai (cho badge + live reload). Khong doc lai file."""
        with self._job_lock:
            job = dict(self._job)
        return {"revision": self._rev, "job": job, "files": self._files_payload()}

    def _watch_loop(self):
        while not self._stop.wait(WATCH_INTERVAL):
            try:
                if not self._watch_enabled or not self._files:
                    continue
                with self._job_lock:
                    if self._job.get("running"):
                        continue
                settings = self._settings or self._saved.get("settings", {})
                for p in list(self._files):
                    key = _norm_key(p)
                    try:
                        st = p.stat()
                    except OSError:
                        rec = self._status.get(key)
                        if rec and rec.get("state") != "missing":
                            rec.update(state="missing", msg="File đã bị xoá hoặc đổi tên.")
                            self._rev += 1
                        continue
                    cur = (int(st.st_mtime_ns), int(st.st_size))
                    if self._seen.get(key) == cur:
                        continue
                    if self._pending.get(key) == cur:
                        self._pending.pop(key, None)
                        self._seen[key] = cur
                        self._rerender(p, settings)
                    else:
                        self._pending[key] = cur
                        rec = self._status.get(key)
                        if rec and rec.get("state") in ("fresh", "pending", "stale"):
                            rec["state"] = "stale"
                            self._rev += 1
            except Exception:
                continue

    def _rerender(self, src: Path, settings: dict):
        """File doi tren disk: bo qua neu bytes khong doi, nguoc lai render lai."""
        try:
            rec = self._status.get(_norm_key(src))
            if rec and rec.get("hash"):
                try:
                    if cache.content_hash(src) == rec["hash"]:
                        try:
                            st = src.stat()
                            rec.update(mtime=int(st.st_mtime_ns), size=int(st.st_size),
                                       state="fresh", msg="")
                        except OSError:
                            pass
                        self._rev += 1
                        return
                except OSError:
                    pass
            self._render_one(src, settings)
        except Exception:
            pass

    # -- output / export --
    def choose_output(self):
        folder = self._folder_dialog()
        if folder:
            self._output_dir = Path(folder)
            self._save_state()
        return str(self._output_dir) if self._output_dir else ""

    def open_output(self):
        target = str(self._output_dir) if self._output_dir else ""
        if not target or not Path(target).is_dir():
            return {"ok": False, "error": "Chưa có thư mục output để mở."}
        try:
            _open_path(target)
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    def export_current(self, index: int, settings: dict):
        """Xuat HTML sach (khong marker) ra noi user chon. Mac dinh canh file goc."""
        try:
            src = self._files[int(index)]
        except Exception:
            return {"ok": False, "error": "Chưa chọn file."}
        if not self._window:
            return {"ok": False, "error": "Không mở được hộp thoại lưu."}
        dest = self._save_dialog(src.stem + ".html", str(src.parent))
        if not dest:
            return {"ok": False, "cancelled": True}
        s = _sanitize_settings(settings)
        self._settings = s
        single = len(self._files) == 1
        ok, msg, out = run_convert(
            str(src), str(dest), title=(s["title"] if single else ""),
            eyebrow=s["eyebrow"], no_toc=s["no_toc"], lang=s["lang"], date_str=s["date"])
        return {"ok": ok, "path": out, "msg": msg} if ok else {"ok": False, "error": msg}

    def export_all(self, settings: dict):
        """Chon thu muc roi xuat tat ca (job nen, tai dung start_batch)."""
        folder = self._folder_dialog()
        if not folder:
            return {"ok": False, "cancelled": True}
        self._output_dir = Path(folder)
        self._save_state()
        return self.start_batch(settings)

    def open_in_browser(self, index: int, settings: dict):
        try:
            p = self._files[int(index)]
        except Exception:
            return {"ok": False, "error": "Chưa chọn file."}
        s = _sanitize_settings(settings)
        self._settings = s
        res = self._render_one(p, s)
        if not res.get("ok"):
            return {"ok": False, "error": res.get("msg") or "Chưa render được."}
        try:
            _open_path(res["path"])
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True, "path": res["path"]}

    def reveal(self, index: int):
        try:
            p = self._files[int(index)]
        except Exception:
            return {"ok": False, "error": "Chưa chọn file."}
        try:
            _reveal_path(str(p))
        except Exception as exc:
            return {"ok": False, "error": str(exc)}
        return {"ok": True}

    # -- batch (thread + polling, giong watermask) --
    def start_batch(self, settings: dict):
        with self._job_lock:
            if self._job.get("running"):
                return {"ok": False, "error": "Đang có một batch chạy."}
            if not self._files:
                return {"ok": False, "error": "Chưa có file đầu vào."}
            self._cancel.clear()
            self._job = {
                "running": True, "kind": "export", "done": 0, "total": len(self._files),
                "current": "Chuẩn bị…", "outputs": [], "errors": [], "cancelled": False,
                "started": time.time(),
            }
        s = _sanitize_settings(settings)
        self._settings = s
        self._save_state({"settings": s})
        files = [str(p) for p in self._files]
        out_dir = str(self._output_dir) if self._output_dir else ""
        single = len(files) == 1

        def worker():
            outputs, errors = [], []
            for i, f in enumerate(files):
                if self._cancel.is_set():
                    break
                src = Path(f)
                out = (Path(out_dir) / (src.stem + ".html")) if out_dir else Path(suggest_output(str(src)))
                ok, msg, out_path = run_convert(
                    str(src), str(out), title=(s["title"] if single else ""),
                    eyebrow=s["eyebrow"], no_toc=s["no_toc"], lang=s["lang"], date_str=s["date"])
                if ok:
                    outputs.append(out_path)
                else:
                    errors.append(msg)
                with self._job_lock:
                    self._job.update(done=i + 1, total=len(files), current=src.name)
            with self._job_lock:
                self._job.update(
                    running=False, current="Hoàn tất",
                    outputs=outputs, errors=errors,
                    cancelled=self._cancel.is_set(), finished=time.time())

        threading.Thread(target=worker, name="mdhtml-export", daemon=True).start()
        return {"ok": True}

    def sync_all(self, settings: dict, force: bool = False):
        """Auto-cache: render lai (neu can) cho tat ca file trong queue."""
        with self._job_lock:
            if self._job.get("running"):
                return {"ok": False, "error": "Đang có một batch chạy."}
            if not self._files:
                return {"ok": False, "error": "Chưa có file đầu vào."}
            self._cancel.clear()
            self._job = {
                "running": True, "kind": "cache", "done": 0, "total": len(self._files),
                "current": "Chuẩn bị…", "outputs": [], "errors": [], "cancelled": False,
                "started": time.time(),
            }
        s = _sanitize_settings(settings)
        self._settings = s
        self._save_state({"settings": s})
        files = [Path(p) for p in self._files]

        def worker():
            outputs, errors = [], []
            for i, src in enumerate(files):
                if self._cancel.is_set():
                    break
                res = self._render_one(src, s, force=force)
                if res.get("ok"):
                    outputs.append(res.get("path", ""))
                else:
                    errors.append(f"{src.name}: {res.get('msg', '')}")
                with self._job_lock:
                    self._job.update(done=i + 1, total=len(files), current=src.name)
            with self._job_lock:
                self._job.update(
                    running=False, current="Hoàn tất",
                    outputs=outputs, errors=errors,
                    cancelled=self._cancel.is_set(), finished=time.time())

        threading.Thread(target=worker, name="mdhtml-cache", daemon=True).start()
        return {"ok": True}

    def batch_status(self):
        with self._job_lock:
            return dict(self._job)

    def cancel_batch(self):
        self._cancel.set()
        return {"ok": True}
