"""Ngon ngu giao dien vi/en: tu dien trong web/app.js, khoa data-i18n trong web/index.html, va cau noi
ngon ngu trong api.py (set_ui_lang, initial_state.ui_lang, thong bao backend, Mind Map theo ngon ngu).

Phan kiem tu dien doc file tinh, khong can cua so app. Phan api chay tren repo git tam.
"""

import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

webview = pytest.importorskip("webview")
pytest.importorskip("mindmap")

ROOT = Path(__file__).parents[1]
sys.path.insert(0, str(ROOT))
import api as api_mod  # noqa: E402
from api import MdHtmlAPI, UI_TEXT, _norm_lang, ui_text  # noqa: E402
from mindmap_fixture import Repo  # noqa: E402

JS = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
HTML = (ROOT / "web" / "index.html").read_text(encoding="utf-8")

# chu co dau tieng Viet (ca hoa, thuong)
VI_RE = re.compile("[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", re.I)


def _dict_pairs(lang: str) -> list:
    """Cap (khoa, gia tri) trong I18N[lang] cua app.js, theo tung dong."""
    start = JS.index("const I18N = {")
    head = JS.index(f"\n  {lang}: {{", start)
    end = JS.index("\n  }", head)
    return re.findall(r'^\s+"([^"]+)": "([^"]*)",?$', JS[head:end], re.M)


def _dict(lang: str) -> dict:
    pairs = _dict_pairs(lang)
    assert len({k for k, _ in pairs}) == len(pairs), f"khoa trung trong I18N.{lang}"
    return dict(pairs)


def _used_keys() -> set:
    keys = set(re.findall(r'\bt\("([\w.]+)"', JS))
    for line in JS.splitlines():
        if line.startswith(("const MM_SEV_KEY", "const MM_TIER_KEY")):
            keys |= {k for k in re.findall(r'"([\w.]+)"', line) if "." in k}
    for base in re.findall(r'\bplural\("([\w.]+)"', JS):
        keys |= {base + "1", base + "N"}
    keys |= set(re.findall(r'data-i18n(?:-html|-title|-placeholder)?="([^"]+)"', HTML))
    return keys


def test_both_languages_have_the_same_keys():
    vi, en = _dict("vi"), _dict("en")
    assert set(vi) == set(en), (sorted(set(vi) ^ set(en)))
    assert all(vi[k] and en[k] for k in vi), "co khoa rong"


def test_placeholders_match_between_languages():
    vi, en = _dict("vi"), _dict("en")
    for k in vi:
        assert sorted(re.findall(r"\{(\w+)\}", vi[k])) == sorted(re.findall(r"\{(\w+)\}", en[k])), k


def test_every_key_used_by_code_exists_in_both_languages():
    vi, en = _dict("vi"), _dict("en")
    missing = sorted(k for k in _used_keys() if k not in vi or k not in en)
    assert not missing, missing


def test_every_dictionary_key_is_referenced():
    # khoa ternary (t(cond ? "a" : "b")) va khoa ghep (plural) van duoc tinh la dung
    unused = []
    for k in _dict("vi"):
        if f'"{k}"' in JS or f'"{k}"' in HTML:
            continue
        m = re.match(r"^(.*)(1|N)$", k)
        if m and f'"{m.group(1)}"' in JS and k in _used_keys():
            continue
        unused.append(k)
    assert not unused, unused


def test_english_dictionary_has_no_vietnamese_letters():
    bad = {k: v for k, v in _dict("en").items() if VI_RE.search(v)}
    assert not bad, bad


def test_static_html_keys_are_wired_to_js():
    # #btnLang la nut chuyen ngon ngu; app.js phai gan su kien cho no
    assert 'id="btnLang"' in HTML and 'getElementById' in JS and '$("btnLang")' in JS
    assert 'data-i18n-title="lang.title"' in HTML


@pytest.mark.skipif(shutil.which("node") is None, reason="khong co node de kiem cu phap app.js")
def test_app_js_parses():
    r = subprocess.run(["node", "--check", str(ROOT / "web" / "app.js")], capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")


# ---------- backend: api.py ----------

def wait_done(api: MdHtmlAPI, timeout: float = 60.0) -> dict:
    deadline = time.time() + timeout
    st = api.mindmap_status()
    while st["running"] and time.time() < deadline:
        time.sleep(0.05)
        st = api.mindmap_status()
    assert not st["running"], "soat chua xong sau 60 giay"
    return st


def finding_messages(api: MdHtmlAPI, path: str) -> list:
    r = api.mindmap_findings(path)
    assert r["ok"] is True, r
    return [f["message"] for f in r["findings"]]


def test_norm_lang_accepts_only_vi_and_en():
    assert _norm_lang(" EN ") == "en"
    assert _norm_lang("vi") == "vi"
    assert _norm_lang("fr") == ""
    assert _norm_lang(None) == ""


def test_ui_text_lookup_and_fallback():
    assert ui_text("no_file") == "Chưa chọn file."
    assert ui_text("no_file", "en") == "No file selected."
    assert ui_text("read_failed", "en", exc="x") == "Could not read the file: x"
    assert ui_text("no_file", "de") == "Chưa chọn file."      # ngon ngu la -> tieng Viet
    assert ui_text("khong_co_khoa") == "khong_co_khoa"        # khoa la -> chinh khoa do


def test_vi_messages_are_unchanged_from_the_owner_version():
    # chu tieng Viet cu cua chu nhan: khong duoc doi khi them tieng Anh
    assert UI_TEXT["vi"]["no_file"] == "Chưa chọn file."
    assert UI_TEXT["vi"]["render_error"] == "Lỗi render."
    assert UI_TEXT["vi"]["folder_gone"] == "Thư mục này không còn tồn tại."
    assert UI_TEXT["vi"]["check_error"] == "Không soát được thư mục này: {detail}"
    assert UI_TEXT["en"].keys() == UI_TEXT["vi"].keys()
    assert not [k for k, v in UI_TEXT["en"].items() if VI_RE.search(v)]


def test_initial_state_reports_saved_language_or_empty(tmp_path):
    api = MdHtmlAPI(tmp_path)
    assert api.initial_state()["ui_lang"] == ""               # chua luu: giao dien tu doan theo trinh duyet
    assert MdHtmlAPI(tmp_path).initial_state()["settings"]["lang"] == "vi"


def test_set_ui_lang_persists_and_reloads(tmp_path):
    api = MdHtmlAPI(tmp_path)
    assert api.set_ui_lang("en") == {"ok": True, "lang": "en", "saved": True}
    assert api.initial_state()["ui_lang"] == "en"
    assert MdHtmlAPI(tmp_path).initial_state()["ui_lang"] == "en"   # doc lai tu file trang thai


def test_set_ui_lang_without_persist_keeps_saved_value(tmp_path):
    api = MdHtmlAPI(tmp_path)
    api.set_ui_lang("en")
    assert api.set_ui_lang("vi", persist=False) == {"ok": True, "lang": "vi", "saved": False}
    assert api.initial_state()["ui_lang"] == "en"          # file van ghi en
    assert MdHtmlAPI(tmp_path).initial_state()["ui_lang"] == "en"


def test_set_ui_lang_rejects_unknown_language_in_current_language(tmp_path):
    api = MdHtmlAPI(tmp_path)
    r = api.set_ui_lang("fr")
    assert r["ok"] is False and r["error"] == "Ngôn ngữ không được hỗ trợ."
    api.set_ui_lang("en", persist=False)
    assert api.set_ui_lang("fr")["error"] == "Unsupported language."


def test_backend_messages_follow_ui_language(tmp_path):
    api = MdHtmlAPI(tmp_path)
    missing = str(tmp_path / "khong-co-thu-muc")
    assert api.mindmap_start(root=missing) == {"ok": False, "error": "Thư mục này không còn tồn tại."}
    api.set_ui_lang("en", persist=False)
    assert api.mindmap_start(root=missing) == {"ok": False, "error": "This folder no longer exists."}
    assert api.mindmap_findings("README.md") == {"ok": False, "error": "No check results yet."}


def test_mindmap_engine_language_follows_ui_and_cache_is_per_language(tmp_path):
    repo = Repo()
    try:
        repo.write("README.md", "# Demo\n\nXem [ban cu](docs/gone.md).\n").commit("init")
        api = MdHtmlAPI(tmp_path)
        api.set_ui_lang("en", persist=False)
        r = api.mindmap_start(root=str(repo.root))
        assert r["ok"] is True and r["cached"] is False
        wait_done(api)
        en = finding_messages(api, "README.md")
        assert en and not [m for m in en if VI_RE.search(m)], en

        # cung thu muc, cung ngon ngu: dung cache
        assert api.mindmap_start(root=str(repo.root))["cached"] is True

        # doi ngon ngu giao dien: khong dung cache cua tieng Anh, soat lai bang tieng Viet
        api.set_ui_lang("vi", persist=False)
        r = api.mindmap_start(root=str(repo.root))
        assert r["ok"] is True and r["cached"] is False
        wait_done(api)
        vi = finding_messages(api, "README.md")
        assert vi and [m for m in vi if VI_RE.search(m)], vi
        assert vi != en

        # tham so lang ghi de ngon ngu giao dien cho lan goi do
        r = api.mindmap_start(root=str(repo.root), force=True, lang="en")
        assert r["cached"] is False
        wait_done(api)
        assert not [m for m in finding_messages(api, "README.md") if VI_RE.search(m)]
    finally:
        repo.cleanup()
