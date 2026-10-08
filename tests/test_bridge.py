import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[1]))
from mdhtml.bridge import batch_convert, preview_stats, render_text, run_convert, suggest_output


def test_suggest_output_same_name_html():
    assert Path(suggest_output("C:/docs/bao-cao.md")) == Path("C:/docs/bao-cao.html")
    assert suggest_output("C:/docs/bao-cao.txt") == ""
    assert suggest_output("") == ""


def test_run_convert_writes_file(tmp_path):
    src = tmp_path / "demo.md"
    src.write_text("# Tieu de\n\nNoi dung **dam**.\n", encoding="utf-8")
    ok, msg, out = run_convert(str(src), "", title="", eyebrow="Test", no_toc=False)
    assert ok, msg
    assert Path(out).is_file()
    html = Path(out).read_text(encoding="utf-8")
    assert "Tieu de" in html and "<strong>dam</strong>" in html


def test_run_convert_rejects_bad_input(tmp_path):
    ok, msg, _ = run_convert(str(tmp_path / "khong-co.md"), "", no_toc=False)
    assert not ok and ".md" in msg
    src = tmp_path / "a.md"
    src.write_text("# A\n", encoding="utf-8")
    ok, _, _ = run_convert(str(src), str(src))
    assert not ok


def test_batch_convert_many_files(tmp_path):
    files = []
    for name in ("a.md", "b.md"):
        p = tmp_path / name
        p.write_text(f"# {name}\n\nNội dung.\n", encoding="utf-8")
        files.append(str(p))
    outdir = tmp_path / "out"
    results = batch_convert(files, out_dir=str(outdir), eyebrow="Test", lang="vi")
    assert len(results) == 2 and all(r[0] for r in results)
    assert (outdir / "a.html").is_file() and (outdir / "b.html").is_file()


def test_preview_stats_counts(tmp_path):
    src = tmp_path / "demo.md"
    src.write_text("# T\n\n## H2\n\n- [ ] task\n", encoding="utf-8")
    s = preview_stats(str(src))
    assert "1 h2" in s and "phút" in s


def test_render_text_shape():
    r = render_text("# Hello\n\nBody.\n", "x.md", date_str="20/09/2026")
    assert r["ok"] and "Hello" in r["html"] and "20/09/2026" in r["html"]
    assert "x.md" in r["stats"]


def test_run_convert_output_dir(tmp_path):
    src = tmp_path / "demo.md"
    src.write_text("# T\n", encoding="utf-8")
    outdir = tmp_path / "out"
    outdir.mkdir()
    ok, msg, out = run_convert(str(src), str(outdir))
    assert ok, msg
    assert Path(out) == outdir / "demo.html" and Path(out).is_file()
