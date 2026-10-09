"""Mind Map trong app MD to HTML: cau noi MdHtmlAPI (soat o nen, trang thai, phat hien, mo tai lieu).

Chay tren repo git tam (mindmap_fixture.Repo), khong dung cua so app.
"""

import json
import sys
import time
from pathlib import Path

import pytest

webview = pytest.importorskip("webview")
pytest.importorskip("mindmap")

sys.path.insert(0, str(Path(__file__).parents[1]))
import api as api_mod  # noqa: E402
from api import MdHtmlAPI  # noqa: E402
from mindmap_fixture import Repo  # noqa: E402


def make_api(tmp_path: Path) -> MdHtmlAPI:
    return MdHtmlAPI(tmp_path)


def wait_done(api: MdHtmlAPI, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    st = api.mindmap_status()
    while st["running"] and time.time() < deadline:
        time.sleep(0.05)
        st = api.mindmap_status()
    assert not st["running"], "soat chua xong sau 60 giay"
    return st


def doc_by_path(st: dict, path: str) -> dict:
    return next(d for d in st["docs"] if d["path"] == path)


def test_clean_repo_every_doc_is_clean(tmp_path):
    repo = Repo()
    try:
        repo.write("README.md", "# Demo\n\nXem [huong dan](docs/guide.md).\n")
        repo.write("docs/guide.md", "# Huong dan\n\nNoi dung ngan.\n").commit("init")
        api = make_api(tmp_path)
        r = api.mindmap_start(root=str(repo.root))
        assert r["ok"] is True and r["cached"] is False
        st = wait_done(api)
        assert st["error"] == ""
        assert st["summary"]["docs"] == 2
        assert st["summary"]["error"] == 0 and st["summary"]["warning"] == 0
        assert st["summary"]["git"] is True
        assert {d["path"] for d in st["docs"]} == {"README.md", "docs/guide.md"}
        assert all(d["tier"] == "clean" for d in st["docs"])
        json.dumps(st)
    finally:
        repo.cleanup()


def test_broken_link_makes_doc_error_with_finding(tmp_path):
    repo = Repo()
    try:
        repo.write("README.md", "# Demo\n\nXem [ban cu](docs/gone.md).\n").commit("init")
        api = make_api(tmp_path)
        assert api.mindmap_start(root=str(repo.root))["ok"] is True
        st = wait_done(api)
        readme = doc_by_path(st, "README.md")
        assert readme["tier"] == "error" and readme["error"] >= 1
        assert st["summary"]["error"] >= 1
        f = api.mindmap_findings("README.md")
        assert f["ok"] is True
        errors = [x for x in f["findings"] if x["severity"] == "error"]
        assert any(x["rule"] == "link-broken" and x["line"] == 3 for x in errors)
        assert all(isinstance(x["message"], str) and x["message"] for x in f["findings"])
        json.dumps(f)
    finally:
        repo.cleanup()


def test_folder_without_git_is_checked(tmp_path):
    folder = Repo(git=False)
    try:
        folder.write("a.md", "# A\n\nXem [b](b.md).\n").write("b.md", "# B\n\nNoi dung.\n")
        api = make_api(tmp_path)
        assert api.mindmap_start(root=str(folder.root))["ok"] is True
        st = wait_done(api)
        assert st["error"] == ""
        assert st["summary"]["git"] is False
        assert st["summary"]["docs"] == 2 and st["summary"]["error"] == 0
        json.dumps(st)
    finally:
        folder.cleanup()


def test_missing_folder_gives_message_not_exception(tmp_path):
    api = make_api(tmp_path)
    r = api.mindmap_start(root=str(tmp_path / "khong-co-thu-muc"))
    assert r["ok"] is False and r["error"]
    assert api.mindmap_status()["running"] is False


def test_nothing_to_scan_gives_message(tmp_path):
    api = make_api(tmp_path)
    r = api.mindmap_start()
    assert r["ok"] is False and "soát" in r["error"]


def test_engine_failure_is_readable_not_a_traceback(tmp_path, monkeypatch):
    import mindmap.engine as engine_mod

    def boom(*a, **k):
        raise RuntimeError("dong thu hai\nTraceback (most recent call last): ...")

    monkeypatch.setattr(engine_mod, "run", boom)
    repo = Repo(git=False).write("a.md", "# A\n")
    try:
        api = make_api(tmp_path)
        assert api.mindmap_start(root=str(repo.root))["ok"] is True
        st = wait_done(api)
        assert st["error"].startswith("Không soát được thư mục này")
        assert "dong thu hai" in st["error"] and "Traceback" not in st["error"]
        assert st["docs"] == [] and st["summary"] is None
        json.dumps(st)
    finally:
        repo.cleanup()


def test_second_start_while_running_is_refused(tmp_path):
    api = make_api(tmp_path)
    with api._mm_lock:
        api._mm["running"] = True
    try:
        r = api.mindmap_start(root=str(tmp_path))
        assert r["ok"] is False and "soát" in r["error"]
    finally:
        with api._mm_lock:
            api._mm["running"] = False


def test_same_root_is_cached_until_forced(tmp_path):
    repo = Repo().write("a.md", "# A\n").commit("init")
    try:
        api = make_api(tmp_path)
        assert api.mindmap_start(root=str(repo.root))["cached"] is False
        wait_done(api)
        again = api.mindmap_start(root=str(repo.root))
        assert again["ok"] is True and again["cached"] is True
        forced = api.mindmap_start(root=str(repo.root), force=True)
        assert forced["ok"] is True and forced["cached"] is False
        wait_done(api)
    finally:
        repo.cleanup()


def test_findings_for_unknown_or_outside_path_are_refused(tmp_path):
    repo = Repo().write("a.md", "# A\n").commit("init")
    try:
        api = make_api(tmp_path)
        assert api.mindmap_findings("a.md")["ok"] is False  # chua soat
        api.mindmap_start(root=str(repo.root))
        wait_done(api)
        assert api.mindmap_findings("khong-co.md")["ok"] is False
        assert api.mindmap_findings("../ngoai.md")["ok"] is False
    finally:
        repo.cleanup()


def test_open_doc_adds_it_to_queue_and_returns_index(tmp_path):
    repo = Repo().write("docs/guide.md", "# Huong dan\n\nNoi dung.\n").commit("init")
    try:
        api = make_api(tmp_path)
        api.mindmap_start(root=str(repo.root))
        wait_done(api)
        r = api.mindmap_open("docs/guide.md")
        assert r["ok"] is True and r["index"] == 0
        files = api.initial_state()["files"]
        assert len(files) == 1 and Path(files[0]["path"]).name == "guide.md"
        assert Path(files[0]["path"]).is_file()
        again = api.mindmap_open("docs/guide.md")  # da co trong hang doi: khong them lai
        assert again["ok"] is True and again["index"] == 0 and len(again["files"]) == 1
        json.dumps(r)
    finally:
        repo.cleanup()


def test_open_refuses_paths_outside_the_scan(tmp_path):
    repo = Repo().write("a.md", "# A\n").commit("init")
    outside = tmp_path / "ngoai.md"
    outside.write_text("# Ngoai\n", encoding="utf-8")
    try:
        api = make_api(tmp_path)
        api.mindmap_start(root=str(repo.root))
        wait_done(api)
        assert api.mindmap_open("../ngoai.md")["ok"] is False
        assert api.mindmap_open(str(outside))["ok"] is False
        assert api.mindmap_open("khong-co.md")["ok"] is False
        assert api.initial_state()["files"] == []
    finally:
        repo.cleanup()


def test_choose_root_without_window_is_cancelled(tmp_path):
    api = make_api(tmp_path)
    assert api.mindmap_choose_root() == {"ok": False, "cancelled": True}


def test_root_comes_from_nearest_git_folder(tmp_path):
    proj = tmp_path / "proj"
    (proj / ".git").mkdir(parents=True)
    (proj / "docs").mkdir()
    doc = proj / "docs" / "x.md"
    doc.write_text("# X\n", encoding="utf-8")
    assert api_mod._repo_root_for(doc) == proj
    plain = tmp_path / "plain"
    plain.mkdir()
    loose = plain / "y.md"
    loose.write_text("# Y\n", encoding="utf-8")
    assert api_mod._repo_root_for(loose) == plain


def test_pick_root_prefers_selected_file_repo(tmp_path):
    repo = Repo().write("docs/a.md", "# A\n").commit("init")
    try:
        api = make_api(tmp_path)
        api.add_dropped_paths([str(repo.root / "docs" / "a.md")])
        target, err = api._mm_pick_root(0, "")
        assert err == "" and target == repo.root
    finally:
        repo.cleanup()


def test_findings_outside_docs_form_their_own_group(tmp_path):
    repo = Repo()
    try:
        repo.write("AGENTS.md", "# Luat\n\n<!-- mindmap: forbid /FORBIDDEN_CALL/ in **/*.py -->\n")
        repo.write("src/app.py", "FORBIDDEN_CALL()\n").commit("init")
        api = make_api(tmp_path)
        api.mindmap_start(root=str(repo.root))
        st = wait_done(api)
        assert all(d["path"] != "src/app.py" for d in st["docs"])
        group = st["outside"]
        assert group is not None and group["count"] == 1 and group["error"] == 1 and group["tier"] == "error"
        assert st["summary"]["outside"] == 1
        out = api.mindmap_outside()
        assert out["ok"] is True and len(out["findings"]) == 1
        f = out["findings"][0]
        assert f["path"] == "src/app.py" and f["rule"] == "rule-violation" and f["severity"] == "error"
        json.dumps(st)
        json.dumps(out)
        assert api.mindmap_open("src/app.py")["ok"] is False  # khong co file de xem truoc
    finally:
        repo.cleanup()


def test_no_outside_group_when_every_finding_belongs_to_a_doc(tmp_path):
    repo = Repo().write("a.md", "# A\n\nXem [b](b.md).\n").write("b.md", "# B\n").commit("init")
    try:
        api = make_api(tmp_path)
        assert api.mindmap_outside()["ok"] is False  # chua soat
        api.mindmap_start(root=str(repo.root))
        st = wait_done(api)
        assert st["outside"] is None and st["summary"]["outside"] == 0
        assert api.mindmap_outside() == {"ok": True, "findings": []}
    finally:
        repo.cleanup()
