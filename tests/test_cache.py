import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from mdhtml import cache


def fake_render(text, name, settings):
    return {"ok": True, "html": f"<html><body><h1>{name}</h1><p>{len(text)}</p></body></html>",
            "stats": "1 dòng · 2 từ"}


def make_md(tmp_path, name="doc.md", text="# T\n\nNoi dung.\n"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def test_settings_key_stable_and_sensitive():
    a = {"eyebrow": "E", "lang": "vi", "no_toc": False, "date": "20/09/2026"}
    b = dict(a)
    assert cache.settings_key(a) == cache.settings_key(b)
    b["no_toc"] = True
    assert cache.settings_key(a) != cache.settings_key(b)
    # date trong = hom nay
    empty = dict(a, date="")
    today = dict(a, date=datetime.now().strftime("%d/%m/%Y"))
    assert cache.settings_key(empty) == cache.settings_key(today)


def test_cache_target_modes(tmp_path):
    src = tmp_path / "sub" / "doc.md"
    beside = cache.cache_target(src, "beside", tmp_path / "cache")
    assert beside == src.with_suffix(".html")
    tool = cache.cache_target(src, "tool", tmp_path / "cache")
    assert tool.parent.parent == tmp_path / "cache"
    assert tool.name == "doc.html"
    assert len(tool.parent.name) == 12


def test_marker_roundtrip_and_position():
    page = "<html><body><p>x</p></body></html>"
    marker = {"v": 2, "key": "abc", "src": "doc.md", "mtime": 1, "size": 2, "date": "20/09/2026"}
    out = cache.embed_marker(page, marker)
    assert cache.read_marker(out) == marker
    assert out.index("mdhtml:cache") < out.index("</body>")
    assert cache.read_marker("<html>khong co marker</html>") is None
    assert cache.read_marker("<!-- mdhtml:cache {broken json} -->") is None


def test_decide_states(tmp_path):
    src = make_md(tmp_path)
    st = src.stat()
    key = cache.settings_key({"eyebrow": "E"})
    good = {"v": cache.CACHE_VERSION, "key": key, "src": "doc.md",
            "mtime": int(st.st_mtime_ns), "size": int(st.st_size)}
    target = tmp_path / "doc.html"
    assert cache.decide(target, None, st, key, "doc.md") == "missing"
    target.write_text("<html></html>", encoding="utf-8")
    assert cache.decide(target, None, st, key, "doc.md") == "foreign"
    assert cache.decide(target, dict(good), st, key, "doc.md") == "fresh"
    assert cache.decide(target, dict(good, key="khac"), st, key, "doc.md") == "stale"
    assert cache.decide(target, dict(good, v=1), st, key, "doc.md") == "stale"
    assert cache.decide(target, dict(good, src="khac.md"), st, key, "doc.md") == "stale"
    assert cache.decide(target, dict(good, mtime=0), st, key, "doc.md") == "stale"
    assert cache.decide(target, dict(good, size=0), st, key, "doc.md") == "stale"


def test_ensure_renders_then_reuses(tmp_path):
    src = make_md(tmp_path)
    calls = []

    def render(text, name, settings):
        calls.append(name)
        return fake_render(text, name, settings)

    r1 = cache.ensure(src, {"eyebrow": "E", "date": "20/09/2026"},
                      cache_dir=tmp_path / "cache", render=render)
    assert r1["ok"] and r1["state"] == "rendered" and not r1["fallback"]
    out = Path(r1["path"])
    assert out == tmp_path / "doc.html" and out.is_file()
    assert cache.read_marker(out.read_text(encoding="utf-8"))["v"] == cache.CACHE_VERSION

    r2 = cache.ensure(src, {"eyebrow": "E", "date": "20/09/2026"},
                      cache_dir=tmp_path / "cache", render=render)
    assert r2["state"] == "fresh" and len(calls) == 1

    r3 = cache.ensure(src, {"eyebrow": "Khac", "date": "20/09/2026"},
                      cache_dir=tmp_path / "cache", render=render)
    assert r3["state"] == "rendered" and len(calls) == 2

    r4 = cache.ensure(src, {"eyebrow": "Khac", "date": "20/09/2026"},
                      cache_dir=tmp_path / "cache", render=render, force=True)
    assert r4["state"] == "rendered" and len(calls) == 3


def test_ensure_detects_source_change(tmp_path):
    src = make_md(tmp_path)
    settings = {"eyebrow": "E", "date": "20/09/2026"}
    cache.ensure(src, settings, cache_dir=tmp_path / "cache", render=fake_render)
    time.sleep(0.01)
    src.write_text("# T\n\nNoi dung dai hon nhieu.\n", encoding="utf-8")
    r = cache.ensure(src, settings, cache_dir=tmp_path / "cache", render=fake_render)
    assert r["state"] == "rendered"


def test_ensure_never_overwrites_foreign_html(tmp_path):
    src = make_md(tmp_path)
    foreign = tmp_path / "doc.html"
    foreign.write_text("<html>cua nguoi dung</html>", encoding="utf-8")
    r = cache.ensure(src, {"eyebrow": "E", "date": "20/09/2026"},
                     cache_dir=tmp_path / "cache", render=fake_render)
    assert r["ok"] and r["fallback"] is True
    assert foreign.read_text(encoding="utf-8") == "<html>cua nguoi dung</html>"
    assert Path(r["path"]).parent.parent == tmp_path / "cache"
    assert Path(r["path"]).is_file()


def test_ensure_tool_mode_and_missing_source(tmp_path):
    src = make_md(tmp_path)
    r = cache.ensure(src, {"date": "20/09/2026"}, mode="tool",
                     cache_dir=tmp_path / "cache", render=fake_render)
    assert r["ok"] and Path(r["path"]).parent.parent == tmp_path / "cache"
    r2 = cache.ensure(tmp_path / "khong-co.md", {}, render=fake_render)
    assert not r2["ok"] and r2["state"] == "missing"


def test_ensure_render_error_is_reported(tmp_path):
    src = make_md(tmp_path)

    def bad_render(text, name, settings):
        return {"ok": False, "error": "boom"}

    r = cache.ensure(src, {}, cache_dir=tmp_path / "cache", render=bad_render)
    assert not r["ok"] and r["state"] == "error" and "boom" in r["msg"]


def test_content_hash_changes(tmp_path):
    src = make_md(tmp_path)
    h1 = cache.content_hash(src)
    src.write_text("# Khac\n", encoding="utf-8")
    assert cache.content_hash(src) != h1
