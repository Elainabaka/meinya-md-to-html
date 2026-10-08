"""Pure logic cho Meinya MD to HTML (khong Tk, khong webview, khong dialog).

UI (pywebview frontend) va CLI deu goi vao day. Core render nam o md_to_html.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from md_to_html import _convert_one, convert


def suggest_output(input_path: str) -> str:
    """Output mac dinh: cung ten, cung thu muc, doi duoi .html."""
    p = Path(input_path)
    if not input_path or p.suffix.lower() != ".md":
        return ""
    return str(p.with_suffix(".html"))


def preview_stats(input_path: str) -> str:
    """Thong ke nhanh de user quyet dinh truoc khi convert (khong dung Parser)."""
    p = Path(input_path or "")
    if not p.is_file():
        return "Chua chon file."
    try:
        text = p.read_text(encoding="utf-8-sig")
    except OSError as e:
        return f"Khong doc duoc: {e}"
    return preview_stats_of_text(text, p.name)


def preview_stats_of_text(text: str, name: str = "") -> str:
    lines = text.split("\n")
    h2 = sum(1 for ln in lines if re.match(r"^##\s+\S", ln.strip()))
    h3 = sum(1 for ln in lines if re.match(r"^###\s+\S", ln.strip()))
    code = sum(1 for ln in lines if ln.strip().startswith("```")) // 2
    tables = sum(1 for ln in lines if ln.strip().startswith("|"))
    words = len(re.findall(r"\w+", text, flags=re.UNICODE))
    mins = max(1, (words + 199) // 200)
    prefix = f"{name}: " if name else ""
    return (
        f"{prefix}{len(lines)} dòng · {words} từ · ~{mins} phút · "
        f"{h2} h2 · {h3} h3 · {tables} dòng bảng · {code} code"
    )


def run_convert(input_path: str, output_path: str, title: str = "",
                eyebrow: str = "", no_toc: bool = False, lang: str = "vi",
                date_str: str = "") -> tuple[bool, str, str]:
    """Convert 1 file. Tra (ok, message, output_path).

    Chi resolve/validate duong dan (adapter); doc + render + ghi nho
    single-writer md_to_html._convert_one de khoi drift voi CLI.
    """
    src = Path(input_path or "")
    if not src.is_file():
        return False, "Chua chon file .md dau vao.", ""
    out = Path(output_path or suggest_output(str(src)) or "")
    if not str(out):
        return False, "Khong xac dinh duoc file output.", ""
    if out.is_dir():
        out = out / (src.stem + ".html")
    try:
        if out.resolve() == src.resolve():
            return False, "File output trung file input.", ""
    except OSError:
        pass
    ok, msg = _convert_one(
        src, out, title.strip(), eyebrow.strip() or "Tài liệu kỹ thuật",
        (lang.strip() or "vi"), no_toc, date_str.strip(),
    )
    return (True, msg, str(out)) if ok else (False, msg, "")


def render_text(md_text: str, name: str, title: str = "", eyebrow: str = "",
                lang: str = "vi", no_toc: bool = False,
                date_str: str = "") -> dict:
    """Convert text truc tiep (phuc vu preview + file keo-tha)."""
    try:
        page = convert(
            md_text,
            source_name=name or "preview.md",
            doc_title=title.strip(),
            eyebrow=eyebrow.strip() or "Tài liệu kỹ thuật",
            lang=(lang.strip() or "vi"),
            with_toc=not no_toc,
            date_str=date_str.strip(),
        )
        return {"ok": True, "html": page, "stats": preview_stats_of_text(md_text, name)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def batch_convert(files: list[str], out_dir: str = "", eyebrow: str = "",
                  lang: str = "vi", no_toc: bool = False,
                  date_str: str = "") -> list[tuple[bool, str, str]]:
    """Convert nhieu file. Tra list (ok, msg, out)."""
    results: list[tuple[bool, str, str]] = []
    od = Path(out_dir) if out_dir.strip() else None
    for f in files:
        src = Path(f)
        if od is not None:
            out = od / (src.stem + ".html")
        else:
            out = Path(suggest_output(str(src)))
        ok, msg, out_path = run_convert(
            str(src), str(out), title="", eyebrow=eyebrow,
            no_toc=no_toc, lang=lang, date_str=date_str,
        )
        results.append((ok, msg, out_path))
    return results
