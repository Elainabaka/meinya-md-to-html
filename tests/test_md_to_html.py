from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parents[1]))
from md_to_html import Parser, convert, main

SAMPLE = """# Tieu de chinh
## Phu de ngan

> **Ghi chu quan trong** ve du an.

## Cai dat & Su dung

1. **Buoc mot**: chay `python x.py`.
2. Buoc hai voi $x^2$ inline.

| Cot A | Cot B |
|---|---|
| a1 | b1 |

```python
print("hello")
```

$$
E = mc^2
$$

Xem [converter](src/a.py) va [ngoai](https://example.com).
"""


def test_headings_toc_and_title_split():
    page = convert(SAMPLE, source_name="demo.md")
    assert '<h1 class="doc-title">Tieu de chinh</h1>' in page
    assert '<p class="doc-sub">Phu de ngan</p>' in page
    assert 'href="#cai-dat-su-dung"' in page
    assert "Phu de ngan</a>" not in page  # subtitle khong lap lai trong TOC


def test_blocks_render():
    page = convert(SAMPLE, source_name="demo.md")
    assert '<aside class="callout">' in page
    assert "<table>" in page and "<th>Cot A</th>" in page
    assert '<figure class="code">' in page
    assert 'print(&quot;hello&quot;)' in page or "print(" in page
    assert '<div class="math">' in page
    assert "<ol>" in page and "<strong>Buoc mot</strong>" in page
    assert "<code>python x.py</code>" in page


def test_links_and_escaping():
    page = convert('<p>x</p>\n\nXem [a](https://example.com) <script>alert(1)</script>\n', source_name="d.md")
    assert 'href="https://example.com"' in page
    assert "<script>alert" not in page


def test_nested_list_keeps_hierarchy():
    md = "- Cha\n  - Con mot\n  - Con hai\n- Chu hai\n"
    page = convert(md, source_name="d.md")
    assert "<li>Cha<ul><li>Con mot</li><li>Con hai</li></ul></li>" in page


def test_code_label_link_no_nested_code():
    page = convert("Xem [`curriculum.py`](file:///e:/Meinya choi osu/curriculum.py).\n", source_name="d.md")
    assert "<code><code>" not in page
    assert "<code>curriculum.py</code>" in page
    assert "file:///" not in page
    page = convert("Xem [curriculum](file:///e:/Meinya choi osu/x.py).\n", source_name="d.md")
    assert "file:///" not in page and "<a href=" not in page
    assert "curriculum" in page


def test_unsafe_schemes_downgraded_to_text():
    page = convert("Xem [x](javascript:alert(1)) va [y](JaVaScRiPt:alert(2)).\n", source_name="d.md")
    assert "<a href=" not in page
    assert "javascript:" not in page.lower()
    assert "x" in page and "y" in page
    page = convert("Xem [d](data:text/html,<script>alert(1)</script>).\n", source_name="d.md")
    assert "<a href=" not in page and "<script>alert" not in page


def test_unsafe_scheme_code_label_no_nested_code():
    page = convert("Chay [`rm -rf /`](javascript:evil()).\n", source_name="d.md")
    assert "<a href=" not in page
    assert "<code><code>" not in page
    assert "<code>rm -rf /</code>" in page


def test_safe_and_relative_links_still_linked():
    page = convert("Xem [a](https://example.com) [b](HTTP://example.com) [c](docs/a.md) [d](#muc).\n",
                   source_name="d.md")
    assert page.count("<a href=") == 4


def test_main_writes_file(tmp_path):
    src = tmp_path / "doc.md"
    src.write_text("# Hello\n\nNoi dung.\n", encoding="utf-8")
    assert main([str(src)]) == 0
    out = tmp_path / "doc.html"
    assert out.is_file()
    text = out.read_text(encoding="utf-8")
    assert "Hello" in text and "md_to_html.py" in text


def test_main_missing_input(tmp_path):
    assert main([str(tmp_path / "khong-co.md")]) == 1


def test_callout_typed_five_kinds():
    md = "> [!NOTE] Ghi nhớ\n>\n> Nội dung note.\n\n> [!WARNING] Cẩn thận\n>\n> Đừng xóa.\n"
    page = convert(md, source_name="d.md")
    assert 'class="callout callout-note"' in page
    assert 'class="callout callout-warning"' in page
    assert "Nội dung note" in page


def test_callout_plain_keeps_old_class():
    page = convert("> Ghi chú thường.\n", source_name="d.md")
    assert '<aside class="callout"><p>' in page


def test_task_list_checkbox():
    page = convert("- [ ] Việc chưa xong\n- [x] Việc xong\n", source_name="d.md")
    assert 'type="checkbox"' in page and "checked" in page
    assert 'class="task-list"' in page


def test_standalone_image_becomes_figure():
    page = convert('![Biểu đồ](fig.png "Caption hay")\n', source_name="d.md")
    assert '<figure class="fig">' in page and "Caption hay" in page


def test_stats_and_fixed_date():
    page = convert("# A\n\nNội dung test.\n", source_name="d.md", date_str="20/09/2026")
    assert "20/09/2026" in page and "từ" in page and "phút đọc" in page


def test_main_batch_directory(tmp_path):
    (tmp_path / "a.md").write_text("# A\n\nHi.\n", encoding="utf-8")
    (tmp_path / "b.md").write_text("# B\n\nYo.\n", encoding="utf-8")
    outdir = tmp_path / "out"
    assert main([str(tmp_path), "-o", str(outdir)]) == 0
    assert (outdir / "a.html").is_file() and (outdir / "b.html").is_file()
