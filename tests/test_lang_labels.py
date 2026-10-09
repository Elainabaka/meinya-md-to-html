"""Nhan giao dien theo ngon ngu: vi giu nguyen tung byte, en la tieng Anh that.

Golden tests/fixtures/md_to_html_golden_*.html duoc sinh tu ban md_to_html.py truoc
khi them nhan theo lang (git HEAD), voi cung mau md va cung date_str.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from md_to_html import convert, doc_stats  # noqa: E402
from mdhtml.bridge import preview_stats, preview_stats_of_text, render_text  # noqa: E402
from main import fatal_message, saved_ui_lang  # noqa: E402

FIX = ROOT / "tests" / "fixtures"
SAMPLE = (FIX / "md_to_html_sample_vi.md").read_text(encoding="utf-8")


def _golden(name: str) -> str:
    # Checkout tren Windows (autocrlf) co the doi LF thanh CRLF; so noi dung, khong so line ending.
    return (FIX / name).read_bytes().replace(b"\r\n", b"\n").decode("utf-8")


def test_vi_output_byte_identical_to_head():
    page = convert(SAMPLE, source_name="demo.md", date_str="20/09/2026", lang="vi")
    assert page.encode("utf-8") == _golden("md_to_html_golden_vi.html").encode("utf-8")


def test_vi_notoc_custom_title_eyebrow_identical_to_head():
    page = convert(SAMPLE, source_name="demo.md", date_str="20/09/2026", lang="vi",
                   doc_title="Tiêu đề tùy chỉnh", eyebrow="Tuỳ chỉnh", with_toc=False)
    assert page == _golden("md_to_html_golden_vi_notoc.html")


def test_unknown_lang_keeps_vi_labels_identical_to_head():
    page = convert(SAMPLE, source_name="demo.md", date_str="20/09/2026", lang="xx")
    assert page == _golden("md_to_html_golden_unknown.html")


def test_en_page_is_english_without_vi_chrome():
    page = convert(SAMPLE, source_name="demo.md", date_str="20/09/2026", lang="en")
    assert '<html lang="en">' in page
    for s in ["Technical document", "Contents", "Filter sections...", "Back to top",
              "Source:", "Made by", "Document /", "☀ Light", "Copy link", "Copied",
              "Wrap long lines", "min read", "code blocks", "<span>Tip</span>",
              "<span>Important</span>", "<span>Warning</span>", "<span>Caution</span>",
              "Offline document page"]:
        assert s in page, s
    # Chu Viet trong khung trang khong duoc con sot (noi dung tai lieu thi giu nguyen).
    for s in ["Mục lục", "Tài liệu /", "Nguồn:", "Tạo bởi", "phút đọc", "Tài liệu kỹ thuật",
              "☀ Sáng", "☾ Tối", "Đã copy", "Xuống dòng code dài", "Về đầu trang",
              "Lọc mục", "Trang tài liệu offline", "<span>Mẹo</span>", "<span>Cảnh báo</span>",
              "<span>Quan trọng</span>", "<span>Nguy hiểm</span>"]:
        assert s not in page, s


def test_en_eyebrow_default_follows_lang_but_typed_eyebrow_stays():
    default = convert(SAMPLE, source_name="demo.md", lang="en")
    assert 'class="doc-eyebrow">Technical document<' in default
    typed = convert(SAMPLE, source_name="demo.md", lang="en", eyebrow="Ghi chú riêng")
    assert 'class="doc-eyebrow">Ghi chú riêng<' in typed
    assert "Technical document" not in typed


def test_doc_stats_labels_and_plurals():
    body = '<table><figure class="code">'
    assert doc_stats("one two", body, "en") == "2 words · ~1 min read · 1 table · 1 code block"
    assert doc_stats("một hai", body, "vi") == "2 từ · ~1 phút đọc · 1 bảng · 1 code"
    assert doc_stats("one", "", "en") == "1 word · ~1 min read"
    body2 = "<table></table><table></table><figure class=\"code\"></figure><figure class=\"code\"></figure>"
    assert doc_stats("", body2, "en").endswith("2 tables · 2 code blocks")


def test_bridge_preview_stats_follow_ui_language():
    text = "# A\n\nHi there.\n"
    assert preview_stats_of_text(text, "x.md") == \
        "x.md: 4 dòng · 3 từ · ~1 phút · 0 h2 · 0 h3 · 0 dòng bảng · 0 code"
    assert preview_stats_of_text(text, "x.md", "vi") == preview_stats_of_text(text, "x.md")
    en = preview_stats_of_text(text, "x.md", "en")
    assert en == "x.md: 4 lines · 3 words · ~1 min · 0 h2 · 0 h3 · 0 table lines · 0 code"
    assert preview_stats(str(ROOT / "khong-co.md")) == "Chua chon file."
    assert preview_stats(str(ROOT / "khong-co.md"), "en") == "No file selected."


def test_bridge_render_text_en_page_and_default_stats():
    r = render_text("# Title\n\nBody.\n", "x.md", lang="en")
    assert r["ok"] and '<html lang="en">' in r["html"] and "Technical document" in r["html"]
    assert "x.md" in r["stats"]


def test_fatal_message_vi_unchanged_and_en_english():
    title, text = fatal_message("vi", "boom")
    assert title == "MD to HTML · Error"
    assert text == "Meinya MD to HTML không thể khởi động:\n\nboom\n\nChi tiết: md_to_html_error.log"
    title_en, text_en = fatal_message("en", "boom")
    assert title_en == "MD to HTML · Error"
    assert "could not start" in text_en and "boom" in text_en and "md_to_html_error.log" in text_en
    assert "không" not in text_en


def test_saved_ui_lang_reads_state_and_defaults_vi(tmp_path):
    assert saved_ui_lang(tmp_path) == "vi"
    (tmp_path / ".md_to_html_state.json").write_text(json.dumps({"ui_lang": "en"}), "utf-8")
    assert saved_ui_lang(tmp_path) == "en"
    (tmp_path / ".md_to_html_state.json").write_text(json.dumps({"ui_lang": "fr"}), "utf-8")
    assert saved_ui_lang(tmp_path) == "vi"
    (tmp_path / ".md_to_html_state.json").write_text("khong phai json", "utf-8")
    assert saved_ui_lang(tmp_path) == "vi"
