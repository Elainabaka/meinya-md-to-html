import sys
import json
import threading
import time
from pathlib import Path

import pytest

webview = pytest.importorskip("webview")

sys.path.insert(0, str(Path(__file__).parents[1]))
import api as api_mod
from api import MdHtmlAPI


def make_api(tmp_path: Path) -> MdHtmlAPI:
    return MdHtmlAPI(tmp_path)


def test_initial_state_shape(tmp_path):
    api = make_api(tmp_path)
    st = api.initial_state()
    assert st["files"] == [] and st["output_dir"] == ""
    assert st["settings"]["lang"] == "vi"


def test_dialogs_degrade_gracefully_without_window(tmp_path):
    api = make_api(tmp_path)
    assert api.add_files() == []
    assert api.add_folder() == []
    assert api.choose_output() == ""


def test_drop_preview_remove_cleans_staging(tmp_path):
    api = make_api(tmp_path)
    res = api.add_dropped_files([{"name": "note.md", "text": "# Tieu de\n\nNoi dung.\n"}])
    assert res["added"] == 1 and len(res["files"]) == 1
    staged = Path(res["files"][0]["path"])
    assert staged.is_file() and ".drop_inbox" in str(staged)
    prev = api.get_preview(0, {"eyebrow": "Test", "lang": "vi", "no_toc": False, "date": "20/09/2026"})
    assert prev["ok"] and "Tieu de" in prev["html"] and "20/09/2026" in prev["html"]
    api.remove_file(0)
    assert not staged.exists()  # staged duoc don ngay khi roi queue


def test_start_batch_writes_outputs(tmp_path):
    api = make_api(tmp_path)
    api.add_dropped_files([
        {"name": "a.md", "text": "# A\n\nHi.\n"},
        {"name": "b.md", "text": "# B\n\nYo.\n"},
    ])
    assert api.start_batch({"eyebrow": "T", "lang": "vi"}) == {"ok": True}
    deadline = time.time() + 15
    last = {}
    while time.time() < deadline:
        last = api.batch_status()
        if not last["running"]:
            break
        time.sleep(0.05)
    assert not last["running"] and last["done"] == 2 and not last["errors"]
    assert len(last["outputs"]) == 2
    assert all(Path(o).is_file() for o in last["outputs"])


def test_get_preview_bad_index_and_title_override(tmp_path):
    api = make_api(tmp_path)
    assert api.get_preview(0, {})["ok"] is False
    api.add_dropped_files([{"name": "n.md", "text": "# Auto\n\nBody.\n"}])
    prev = api.get_preview(0, {"title": "Tay", "eyebrow": "E"})
    assert prev["ok"] and "Tay" in prev["html"] and "Auto" not in prev["html"].split("doc-title")[0]


def test_start_batch_empty_and_double_guard(tmp_path):
    api = make_api(tmp_path)
    assert api.start_batch({})["ok"] is False
    api.add_dropped_files([{"name": "a.md", "text": "# A\n"}])
    with api._job_lock:
        api._job["running"] = True
    try:
        r = api.start_batch({})
        assert r["ok"] is False and "batch" in r["error"].lower()
    finally:
        with api._job_lock:
            api._job["running"] = False


def test_merge_dir_and_dedupe(tmp_path):
    api = make_api(tmp_path)
    d = tmp_path / "docs"
    d.mkdir()
    (d / "one.md").write_text("# One\n", encoding="utf-8")
    (d / "ignore.txt").write_text("x", encoding="utf-8")
    api._merge_files([str(d)])
    assert len(api._files) == 1
    api._merge_files([str(d / "one.md")])  # trung -> khong them
    assert len(api._files) == 1


def test_drop_duplicate_and_junk(tmp_path):
    api = make_api(tmp_path)
    first = api.add_dropped_files([{"name": "n.md", "text": "# T\n"}])
    assert first["added"] == 1
    second = api.add_dropped_files([{"name": "n.md", "text": "# T\n"}])
    assert second["added"] == 0  # cung bytes -> tai dung, khong phinh _2
    junk = api.add_dropped_files([None, "x", {}, {"name": "e.md", "text": ""}])
    assert junk["added"] == 0 and len(junk["files"]) == 1
    assert api.add_dropped_files(None)["added"] == 0


def test_cancel_batch_deterministic(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    api.add_dropped_files([{"name": f"{c}.md", "text": f"# {c}\n"} for c in "abc"])
    gate = threading.Event()

    def slow_fake(src, out, **kw):
        gate.wait(timeout=10)
        return True, "ok", out

    monkeypatch.setattr(api_mod, "run_convert", slow_fake)
    assert api.start_batch({}) == {"ok": True}
    deadline = time.time() + 10
    while time.time() < deadline and not api.batch_status()["running"]:
        time.sleep(0.01)
    api.cancel_batch()
    gate.set()
    last = {}
    while time.time() < deadline:
        last = api.batch_status()
        if not last["running"]:
            break
        time.sleep(0.02)
    assert last["cancelled"] is True and last["done"] < 3


def test_legacy_home_migration(tmp_path, monkeypatch):
    fake_home = tmp_path / "home.json"
    fake_home.write_text('{"out_dir": "", "eyebrow": "Cu", "lang": "en", "no_toc": true}',
                         encoding="utf-8")
    monkeypatch.setattr(api_mod, "LEGACY_HOME_STATE", fake_home)
    st = make_api(tmp_path).initial_state()["settings"]
    assert st["eyebrow"] == "Cu" and st["lang"] == "en" and st["no_toc"] is True


# -- v2.1: auto-cache + live preview --


def add_real(api: MdHtmlAPI, tmp_path: Path, name: str = "doc.md", text: str = "# T\n\nNoi dung.\n"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    api.add_dropped_paths([str(p)])
    return p


def test_preview_info_caches_beside_source(tmp_path):
    api = make_api(tmp_path)
    add_real(api, tmp_path)
    r = api.preview_info(0, {"eyebrow": "E", "lang": "vi", "date": "20/09/2026"})
    assert r["ok"] and r["state"] == "rendered" and r["fallback"] is False
    out = Path(r["out"])
    assert out == tmp_path / "doc.html" and out.is_file()
    assert r["url"].startswith("file:///") and "?v=" in r["url"]
    assert "20/09/2026" in out.read_text(encoding="utf-8")
    r2 = api.preview_info(0, {"eyebrow": "E", "lang": "vi", "date": "20/09/2026"})
    assert r2["ok"] and r2["state"] == "fresh" and r2["out"] == r["out"]


def test_preview_info_never_overwrites_foreign_html(tmp_path):
    api = make_api(tmp_path)
    add_real(api, tmp_path)
    foreign = tmp_path / "doc.html"
    foreign.write_text("<html>nguoi dung</html>", encoding="utf-8")
    r = api.preview_info(0, {})
    assert r["ok"] and r["fallback"] is True
    assert foreign.read_text(encoding="utf-8") == "<html>nguoi dung</html>"
    assert Path(r["out"]).parent.parent == api.cache_root()


def test_preview_info_inline_fallback_when_write_fails(tmp_path, monkeypatch):
    api = make_api(tmp_path)
    add_real(api, tmp_path, text="# Inline\n\nBody.\n")

    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(api_mod.cache, "atomic_write_text", boom)
    r = api.preview_info(0, {})
    assert r["ok"] and r.get("inline") is True and "Inline" in r["html"]


def test_watch_poll_rerenders_on_external_change(tmp_path):
    api = make_api(tmp_path)
    md = add_real(api, tmp_path, text="# A\n\nBan dau.\n")
    api.preview_info(0, {"date": "20/09/2026"})
    out = tmp_path / "doc.html"
    before = out.read_text(encoding="utf-8")
    time.sleep(0.02)
    md.write_text("# A\n\nDa sua boi agent.\n", encoding="utf-8")
    deadline = time.time() + 6
    while time.time() < deadline:
        api.watch_poll()
        if out.read_text(encoding="utf-8") != before:
            break
        time.sleep(0.1)
    after = out.read_text(encoding="utf-8")
    assert after != before and "Da sua boi agent" in after


def test_watch_poll_marks_missing_file(tmp_path):
    api = make_api(tmp_path)
    md = add_real(api, tmp_path)
    api.preview_info(0, {})
    md.unlink()
    deadline = time.time() + 6
    state = ""
    while time.time() < deadline:
        st = api.watch_poll()
        state = st["files"][0]["state"] if st["files"] else ""
        if state == "missing":
            break
        time.sleep(0.1)
    assert state == "missing"


def test_sync_all_caches_every_file(tmp_path):
    api = make_api(tmp_path)
    for name in ("a.md", "b.md"):
        (tmp_path / name).write_text(f"# {name}\n\nNoi dung.\n", encoding="utf-8")
    api.add_dropped_paths([str(tmp_path / "a.md"), str(tmp_path / "b.md")])
    assert api.sync_all({"date": "20/09/2026"}) == {"ok": True}
    deadline = time.time() + 10
    while time.time() < deadline and api.batch_status()["running"]:
        time.sleep(0.05)
    st = api.batch_status()
    assert not st["running"] and st["kind"] == "cache" and st["done"] == 2 and not st["errors"]
    assert (tmp_path / "a.html").is_file() and (tmp_path / "b.html").is_file()


def test_set_options_persists_and_switches_cache_mode(tmp_path):
    api = make_api(tmp_path)
    add_real(api, tmp_path)
    api.preview_info(0, {"date": "20/09/2026"})
    beside = tmp_path / "doc.html"
    assert beside.is_file()
    r = api.set_options(cache_mode="tool", watch=False)
    assert r["ok"] and r["cache_mode"] == "tool" and r["watch"] is False
    assert not beside.exists()  # don .html do tool tao khi doi sang cache trong tool
    r2 = api.preview_info(0, {"date": "20/09/2026"})
    assert r2["ok"] and Path(r2["out"]).parent.parent == api.cache_root()
    st = make_api(tmp_path).initial_state()
    assert st["cache_mode"] == "tool" and st["watch"] is False


def test_export_current_writes_clean_html(tmp_path):
    class FakeWindow:
        def __init__(self, result):
            self._result = result

        def create_file_dialog(self, *a, **k):
            return self._result

    api = make_api(tmp_path)
    add_real(api, tmp_path, text="# Xuat\n\nBody.\n")
    dest = tmp_path / "out" / "clean.html"
    api.bind_window(FakeWindow(str(dest)))
    r = api.export_current(0, {"eyebrow": "E", "date": "20/09/2026"})
    assert r["ok"] and Path(r["path"]) == dest and dest.is_file()
    assert "mdhtml:cache" not in dest.read_text(encoding="utf-8")
