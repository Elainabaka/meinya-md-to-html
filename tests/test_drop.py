import sys
from pathlib import Path

import pytest

webview = pytest.importorskip("webview")

sys.path.insert(0, str(Path(__file__).parents[1]))
import main as main_mod
from api import MdHtmlAPI


def make_api(tmp_path: Path) -> MdHtmlAPI:
    return MdHtmlAPI(tmp_path)


def test_extract_dropped_paths_both_keys():
    assert main_mod.extract_dropped_paths(
        {"dataTransfer": {"files": [
            {"pywebviewFullPath": "C:/a/b.md"},
            {"pywebviewFullPath": "C:/a/c.txt"},
            {},
        ]}}) == ["C:/a/b.md"]
    # Ban cu ghi 'domTransfer': van ho tro de chiu nhieu version.
    assert main_mod.extract_dropped_paths(
        {"domTransfer": {"files": [{"pywebviewFullPath": "/tmp/d.MD"}]}}) == ["/tmp/d.MD"]
    assert main_mod.extract_dropped_paths({}) == []
    assert main_mod.extract_dropped_paths(None) == []


def test_add_dropped_paths_filters_and_merges(tmp_path):
    api = make_api(tmp_path)
    real = tmp_path / "real.md"
    real.write_text("# R\n\nBody.\n", encoding="utf-8")
    (tmp_path / "note.txt").write_text("x", encoding="utf-8")
    res = api.add_dropped_paths(
        [str(real), str(tmp_path / "note.txt"), str(tmp_path / "nope.md"), "", None])
    assert res["added"] == 1
    assert Path(res["files"][0]["path"]) == real
    again = api.add_dropped_paths([str(real)])
    assert again["added"] == 0 and len(again["files"]) == 1


def test_staged_dupe_skipped_when_real_path_exists(tmp_path):
    api = make_api(tmp_path)
    real = tmp_path / "real.md"
    real.write_text("# R\n\nBody.\n", encoding="utf-8")
    api.add_dropped_paths([str(real)])
    dup = api.add_dropped_files([{"name": "real.md", "text": "# R\n\nBody.\n"}])
    assert dup["added"] == 0 and len(dup["files"]) == 1
    assert Path(dup["files"][0]["path"]) == real


def test_native_drop_replaces_staged_copy(tmp_path):
    api = make_api(tmp_path)
    staged = api.add_dropped_files([{"name": "q.md", "text": "# Q\n\nYo.\n"}])
    staged_path = Path(staged["files"][0]["path"])
    assert staged_path.is_file()
    real = tmp_path / "q.md"
    real.write_text("# Q\n\nYo.\n", encoding="utf-8")
    res = api.add_dropped_paths([str(real)])
    assert res["added"] == 1 and len(res["files"]) == 1
    assert Path(res["files"][0]["path"]) == real
    assert not staged_path.exists()


def test_drop_handler_flow_with_fake_window(tmp_path):
    api = make_api(tmp_path)
    real = tmp_path / "h.md"
    real.write_text("# H\n", encoding="utf-8")

    class FakeDrop:
        def __init__(self):
            self.handlers = []
        def __iadd__(self, h):
            self.handlers.append(h)
            return self

    class FakeWindow:
        def __init__(self):
            self.js = []
            self.drop = FakeDrop()
            events = type("E", (), {"drop": self.drop})()
            document = type("D", (), {"events": events})()
            self.dom = type("W", (), {"document": document})()
        def evaluate_js(self, code):
            self.js.append(code)

    win = FakeWindow()
    assert main_mod.register_drop_handler(win, api) is True
    handler = win.drop.handlers[0]
    cb = getattr(handler, "callback", handler)
    cb({"dataTransfer": {"files": [{"pywebviewFullPath": str(real)}]}})
    st = api.initial_state()
    assert len(st["files"]) == 1 and Path(st["files"][0]["path"]) == real
    assert win.js and "__mdRefresh" in win.js[0]


def test_register_drop_handler_degrades_without_dom(tmp_path):
    api = make_api(tmp_path)
    assert main_mod.register_drop_handler(object(), api) is False
