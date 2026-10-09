"""Convert Markdown (.md) sang trang HTML tài liệu, đọc dễ, offline 100%.

Chi dung stdlib (khong can pip). Ho tro: heading + anchor, TOC sidebar,
bang GFM, code fence co nut copy, blockquote -> callout, list lồng nhau,
inline code/bold/italic/link/image, khoi math $$...$$ giu nguyen.

Dung:
    python md_to_html.py INPUT.md
    python md_to_html.py INPUT.md -o OUTPUT.html
    python md_to_html.py THU_MUC/ [-o OUT_DIR] [--recursive]
    python md_to_html.py INPUT.md --title "Tieu de" --eyebrow "..." --date "20/09/2026" --no-toc
"""

import argparse
import html
import re
import sys
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


# ---------------------------------------------------------------- parser

def _slug(text: str) -> str:
    s = html.unescape(re.sub(r"<[^>]+>", "", text)).strip().lower()
    s = re.sub(r"[^\w\s\-.]", "", s, flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", s).strip("-") or "section"


# Nhan giao dien trang. vi la ban goc; lang bat dau bang "en" -> tieng Anh;
# moi lang khac (xx, rong) -> tieng Viet nhu cu. Them ngon ngu = them mot dict.
_LABELS = {
    "vi": {
        "crumb": "Tài liệu /",
        "theme_light": "☀ Sáng",
        "theme_dark": "☾ Tối",
        "toc": "Mục lục",
        "toc_filter": "Lọc mục...",
        "source": "Nguồn:",
        "made_by": "Tạo bởi",
        "footer": "Trang tài liệu offline — mở bằng trình duyệt, không cần mạng.",
        "totop": "Về đầu trang",
        "copy": "Copy",
        "copied": "Đã copy",
        "wrap": "Wrap",
        "unwrap": "Unwrap",
        "wrap_title": "Xuống dòng code dài",
        "copy_link": "Copy link",
        "eyebrow": "Tài liệu kỹ thuật",
        "words_one": "từ",
        "words_many": "từ",
        "read": "phút đọc",
        "tables_one": "bảng",
        "tables_many": "bảng",
        "codes_one": "code",
        "codes_many": "code",
        "callout_note": "Note",
        "callout_tip": "Mẹo",
        "callout_important": "Quan trọng",
        "callout_warning": "Cảnh báo",
        "callout_caution": "Nguy hiểm",
    },
    "en": {
        "crumb": "Document /",
        "theme_light": "☀ Light",
        "theme_dark": "☾ Dark",
        "toc": "Contents",
        "toc_filter": "Filter sections...",
        "source": "Source:",
        "made_by": "Made by",
        "footer": "Offline document page: open in any browser, no network needed.",
        "totop": "Back to top",
        "copy": "Copy",
        "copied": "Copied",
        "wrap": "Wrap",
        "unwrap": "Unwrap",
        "wrap_title": "Wrap long lines",
        "copy_link": "Copy link",
        "eyebrow": "Technical document",
        "words_one": "word",
        "words_many": "words",
        "read": "min read",
        "tables_one": "table",
        "tables_many": "tables",
        "codes_one": "code block",
        "codes_many": "code blocks",
        "callout_note": "Note",
        "callout_tip": "Tip",
        "callout_important": "Important",
        "callout_warning": "Warning",
        "callout_caution": "Caution",
    },
}
_CALLOUT_ICON = {"note": "ℹ", "tip": "✓", "important": "❗", "warning": "⚠", "caution": "⛔"}
_VI_EYEBROW = _LABELS["vi"]["eyebrow"]


def _is_en(lang: str) -> bool:
    return str(lang or "").strip().lower().startswith("en")


def _labels(lang: str) -> dict:
    return _LABELS["en"] if _is_en(lang) else _LABELS["vi"]

_CALLOUT_RE = re.compile(r"^\[!(note|tip|important|warning|caution)\]\s*(.*)$", re.IGNORECASE)

# Link an toan: chi render <a> cho scheme biet + relative. Moi scheme la
# (javascript:, data:, vbscript:, ...) bi ha cap thanh text/code vi output
# HTML duoc chia se cho nguoi khac mo bang browser.
_SAFE_LINK_PREFIXES = ("http://", "https://", "#", "mailto:")
_UNSAFE_SCHEME_RE = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")


def _split_table_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [c.strip() for c in line.split("|")]


def _is_delim_row(cells: list[str]) -> bool:
    return bool(cells) and all(re.fullmatch(r":?-{1,}:?", c) for c in cells)


class Parser:
    """Markdown -> HTML fragment (body) + TOC entries. Giu thu tu, don gian."""

    def __init__(self, lang: str = "vi") -> None:
        self.toc: list[tuple[int, str, str]] = []  # (level, id, text-html)
        self._used_ids: dict[str, int] = {}
        self.L = _labels(lang)

    def _uid(self, base: str) -> str:
        n = self._used_ids.get(base, 0)
        self._used_ids[base] = n + 1
        return base if n == 0 else f"{base}-{n}"

    # -- inline ---------------------------------------------------------
    def inline(self, text: str) -> str:
        codes: list[str] = []

        def stash(m: re.Match) -> str:
            codes.append(html.escape(m.group(1), quote=False))
            return f"\ue000{len(codes) - 1}\ue001"

        t = re.sub(r"`([^`]+?)`", stash, text)
        t = html.escape(t, quote=False)
        # image truoc link
        t = re.sub(
            r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)',
            lambda m: '<img src="{}" alt="{}"{}>'.format(
                html.escape(m.group(2), quote=True),
                html.escape(m.group(1), quote=True),
                ' title="{}"'.format(html.escape(m.group(3), quote=True)) if m.group(3) else "",
            ),
            t,
        )

        def link(m: re.Match) -> str:
            label, href = m.group(1), m.group(2).strip()
            href = re.sub(r'\s+"[^"]*"$', "", href).strip()
            href_e = html.escape(href, quote=True)
            ph = re.fullmatch("\ue000(\\d+)\ue001", label)
            if href.startswith("file:///"):
                # Link file:// mo tu browser thuong bi chan / dai dong:
                # hien gon thay vi anchor chet. Nhan code giu nguyen <code>.
                if ph:
                    return f"<code>{codes[int(ph.group(1))]}</code>"
                return label
            if ph:
                label = f"<code>{codes[int(ph.group(1))]}</code>"
            href_low = href.lower()
            if href_low.startswith(_SAFE_LINK_PREFIXES):
                return '<a href="{}">{}</a>'.format(href_e, label)
            if _UNSAFE_SCHEME_RE.match(href):
                # Scheme la (javascript:, data:, ...) -> ha cap nhu file:///.
                return label
            return '<a href="{}">{}</a>'.format(href_e, label)

        t = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", link, t)
        t = re.sub(r"\*\*([^*]+?)\*\*", r"<strong>\1</strong>", t)
        t = re.sub(r"(?<!\w)\*([^*\n]+?)\*(?!\w)", r"<em>\1</em>", t)
        t = re.sub(r"~~([^~]+?)~~", r"<del>\1</del>", t)
        for i, code in enumerate(codes):
            t = t.replace(f"\ue000{i}\ue001", f"<code>{code}</code>")
        return t

    # -- blocks ---------------------------------------------------------
    def parse(self, src: str) -> str:
        lines = src.replace("\t", "    ").split("\n")
        out: list[str] = []
        i, n = 0, len(lines)
        while i < n:
            line = lines[i]
            s = line.strip()
            if not s:
                i += 1
                continue
            if re.fullmatch(r"-{3,}|\*{3,}|_{3,}", s):
                out.append("<hr>")
                i += 1
                continue
            m = re.match(r"^(#{1,4})\s+(.*)$", s)
            if m:
                level = len(m.group(1))
                text = self.inline(m.group(2).strip())
                hid = self._uid(_slug(re.sub(r"<[^>]+>", "", text)))
                if level in (2, 3):
                    self.toc.append((level, hid, text))
                out.append(f'<h{level} id="{hid}">{text}</h{level}>')
                i += 1
                continue
            if s.startswith("```"):
                lang = s[3:].strip().split()[0] if len(s) > 3 else ""
                buf: list[str] = []
                i += 1
                while i < n and not lines[i].strip().startswith("```"):
                    buf.append(lines[i].rstrip())
                    i += 1
                i += 1  # dong ```
                code = html.escape("\n".join(buf), quote=False)
                label = html.escape(lang) if lang else "text"
                L = self.L
                out.append(
                    '<figure class="code"><figcaption>'
                    f'<span class="dot"></span><span class="dot"></span>'
                    f'<span class="lang">{label}</span>'
                    f'<button class="copy" type="button">{L["copy"]}</button>'
                    f'<button class="wrap" type="button" title="{L["wrap_title"]}">{L["wrap"]}</button>'
                    f"</figcaption><pre><code>{code}</code></pre></figure>"
                )
                continue
            if s.startswith("$$"):
                buf = [s[2:]] if len(s) > 2 and not s.endswith("$$") else []
                if s.endswith("$$") and len(s) > 2:
                    buf = [s[2:-2]]
                    i += 1
                else:
                    i += 1
                    while i < n and not lines[i].strip().endswith("$$"):
                        buf.append(lines[i].strip())
                        i += 1
                    if i < n:
                        buf.append(lines[i].strip()[:-2])
                        i += 1
                out.append(
                    '<div class="math">{}</div>'.format(
                        html.escape("\n".join(b for b in buf if b), quote=False)
                    )
                )
                continue
            if s.startswith(">"):
                buf = []
                while i < n and lines[i].strip().startswith(">"):
                    buf.append(lines[i].strip()[1:].lstrip())
                    i += 1
                # Callout kieu GitHub/Quarto: > [!NOTE] Tieu de ...
                first = next((b for b in buf if b), "")
                m_call = _CALLOUT_RE.match(first)
                if m_call:
                    kind = m_call.group(1).lower()
                    rest_title = m_call.group(2).strip()
                    label, icon = self.L["callout_" + kind], _CALLOUT_ICON[kind]
                    # Phan than: cac dong sau dong marker
                    idx = buf.index(first)
                    body_lines = [b for b in buf[idx + 1:] if b]
                    if len(buf) == idx + 1 and rest_title:
                        # 1 dong duy nhat: rest la body
                        body_html = self.inline(rest_title)
                        title_html = ""
                    else:
                        body_html = self.inline(" ".join(body_lines)) if body_lines else ""
                        title_html = self.inline(rest_title) if rest_title else ""
                    title_row = f'<p class="callout-title"><span class="ico">{icon}</span><span>{label}</span>'
                    if title_html:
                        title_row += f'<span class="callout-custom"> — {title_html}</span>'
                    title_row += "</p>"
                    body_row = f"<p>{body_html}</p>" if body_html else ""
                    out.append(f'<aside class="callout callout-{kind}">{title_row}{body_row}</aside>')
                else:
                    inner = " ".join(b for b in buf if b)
                    out.append(f'<aside class="callout"><p>{self.inline(inner)}</p></aside>')
                continue
            if s.startswith("|") and i + 1 < n and _is_delim_row(
                _split_table_row(lines[i + 1])
            ):
                head = _split_table_row(s)
                delim = _split_table_row(lines[i + 1])
                aligns = []
                for d in delim:
                    if d.startswith(":") and d.endswith(":"):
                        aligns.append(' style="text-align:center"')
                    elif d.endswith(":"):
                        aligns.append(' style="text-align:right"')
                    else:
                        aligns.append("")
                i += 2
                rows: list[list[str]] = []
                while i < n and lines[i].strip().startswith("|"):
                    rows.append(_split_table_row(lines[i]))
                    i += 1
                th = "".join(
                    f"<th{a}>{self.inline(c)}</th>" for c, a in zip(head, aligns)
                )
                trs = "".join(
                    "<tr>"
                    + "".join(
                        f"<td{a}>{self.inline(c)}</td>"
                        for c, a in zip(r + [""] * len(head), aligns)
                    )
                    + "</tr>"
                    for r in rows
                )
                out.append(
                    '<div class="table-wrap"><table><thead><tr>'
                    f"{th}</tr></thead><tbody>{trs}</tbody></table></div>"
                )
                continue
            if re.match(r"^(\d+[.)]|[-*+])\s+\S", s):
                html_list, i = self._parse_list(lines, i)
                out.append(html_list)
                continue
            # doan van: gom cac dong lien ke
            buf = [s]
            i += 1
            while i < n and lines[i].strip() and not re.match(
                r"^(#{1,4}\s|```|\$\$|>|\||\d+[.)]\s+|[-*+]\s+\S|-{3,}$)",
                lines[i].strip(),
            ):
                buf.append(lines[i].strip())
                i += 1
            # Anh dung rieng 1 dong -> figure + caption de de hieu
            if len(buf) == 1:
                m_img = re.fullmatch(
                    r'!\[([^\]]*)\]\(([^)\s]+)(?:\s+"([^"]*)")?\)', buf[0]
                )
                if m_img:
                    alt, src, title = m_img.group(1), m_img.group(2), m_img.group(3) or ""
                    cap = title.strip() or alt.strip()
                    fig = '<figure class="fig"><img src="{}" alt="{}"{}>'.format(
                        html.escape(src, quote=True),
                        html.escape(alt, quote=True),
                        f' title="{html.escape(title, quote=True)}"' if title else "",
                    )
                    if cap:
                        fig += f"<figcaption>{html.escape(cap, quote=False)}</figcaption>"
                    fig += "</figure>"
                    out.append(fig)
                    continue
            out.append(f"<p>{self.inline(' '.join(buf))}</p>")
        return "\n".join(out)

    def _parse_list(self, lines: list[str], start: int) -> tuple[str, int]:
        raw: list[tuple[int, bool, str, bool | None]] = []  # (indent, ordered, html, checked)
        i, n = start, len(lines)
        while i < n:
            s = lines[i].strip()
            m = re.match(r"^(\d+[.)]|[-*+])\s+(.*)$", s)
            if not m:
                # Dong tiep tuc cua item sau cung (vi du cong thuc tach dong)
                if raw and s and not s.startswith(("|", "```", ">", "#")):
                    ind, od, prev, chk = raw[-1]
                    raw[-1] = (ind, od, prev + " " + self.inline(s), chk)
                    i += 1
                    continue
                break
            indent = len(lines[i]) - len(lines[i].lstrip(" "))
            ordered = bool(re.match(r"^\d", m.group(1)))
            content = m.group(2).strip()
            checked: bool | None = None
            m_task = re.match(r"^\[([ xX])\]\s+(.*)$", content)
            if m_task:
                checked = m_task.group(1).lower() == "x"
                content = m_task.group(2).strip()
            item_html = self.inline(content)
            if checked is not None:
                box = '<input type="checkbox" disabled{}> '.format(" checked" if checked else "")
                item_html = f"{box}{item_html}"
            raw.append((indent, ordered, item_html, checked))
            i += 1
        if not raw:
            return "", start
        html_list, _ = self._build_list(raw, 0, raw[0][0])
        return html_list, i

    def _build_list(
        self, raw: list[tuple[int, bool, str, bool | None]], pos: int, base: int
    ) -> tuple[str, int]:
        tag = "ol" if raw[pos][1] else "ul"
        has_task = any(c is not None for _, _, _, c in raw[pos:])
        cls = f' class="task-list"' if (tag == "ul" and has_task) else ""
        parts: list[str] = []
        while pos < len(raw):
            ind, _, text, chk = raw[pos]
            if ind < base:
                break
            if ind > base:
                sub, pos = self._build_list(raw, pos, ind)
                parts[-1] = parts[-1][:-5] + sub + "</li>"
                continue
            # tach khoi f-string: Python < 3.12 cam dau \ trong bieu thuc f-string
            task = ' class="task"' if chk is not None else ""
            parts.append(f"<li{task}>{text}</li>")
            pos += 1
        return f"<{tag}{cls}>{''.join(parts)}</{tag}>", pos


# ---------------------------------------------------------------- template

CSS = r"""
:root{color-scheme:light dark;--font:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif;--mono:ui-monospace,"SF Mono","Cascadia Code",Consolas,"Liberation Mono",monospace}
[data-theme="light"]{--bg:#f6f6f4;--paper:#ffffff;--ink:#1c1917;--muted:#78716c;--faint:#a8a29e;--line:#e7e5e4;--line-soft:#f0eeec;--accent:#c2417a;--accent-ink:#9d2c5e;--code-bg:#f5f4f3;--callout-bg:#fdf4f7;--callout-line:#f0b8d2;--math-bg:#fafaf9;--th-bg:#faf9f8;--shadow:0 1px 2px rgba(28,25,23,.05)}
[data-theme="dark"]{--bg:#121110;--paper:#1c1a19;--ink:#e9e6e3;--muted:#a8a29e;--faint:#78716c;--line:#2e2b29;--line-soft:#262423;--accent:#f472a8;--accent-ink:#f9a8c9;--code-bg:#141312;--callout-bg:#241a1f;--callout-line:#6b2c47;--math-bg:#171514;--th-bg:#201d1c;--shadow:0 1px 2px rgba(0,0,0,.4)}
*{box-sizing:border-box}html{scroll-behavior:smooth;scroll-padding-top:76px}
body{margin:0;background:var(--bg);color:var(--ink);font-family:var(--font);font-size:16px;line-height:1.8;-webkit-font-smoothing:antialiased}
a{color:var(--accent-ink);text-decoration:none;border-bottom:1px solid transparent}
article a:hover{border-bottom-color:currentColor}
.topbar{position:sticky;top:0;z-index:50;background:color-mix(in srgb,var(--paper) 88%,transparent);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.topbar-in{max-width:1120px;margin:0 auto;padding:0 24px;height:58px;display:flex;align-items:center;gap:12px}
.crumbs{font-size:13px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.crumbs b{color:var(--ink);font-weight:600}
.progress{position:absolute;left:0;bottom:-1px;height:2px;width:0;background:var(--accent)}
.theme-btn{margin-left:auto;flex:none;font:inherit;font-size:13px;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:8px;padding:6px 12px;cursor:pointer}
.theme-btn:hover{color:var(--ink);border-color:var(--faint)}
.layout{max-width:1120px;margin:0 auto;padding:40px 24px 90px;display:grid;grid-template-columns:232px minmax(0,1fr);gap:56px}
.toc{position:sticky;top:98px;align-self:start;max-height:calc(100vh - 130px);overflow:auto;font-size:13.5px}
.toc h2{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:var(--faint);margin:0 0 10px;font-weight:700}
.toc a{display:block;color:var(--muted);padding:4px 0 4px 14px;border-left:2px solid var(--line);line-height:1.55}
.toc a.l3{padding-left:28px;font-size:12.5px}
.toc a:hover{color:var(--ink)}
.toc a.active{color:var(--accent-ink);border-left-color:var(--accent);font-weight:600}
article{min-width:0;background:var(--paper);border:1px solid var(--line);border-radius:16px;padding:48px 56px;box-shadow:var(--shadow)}
.doc-eyebrow{font-size:12.5px;font-weight:700;letter-spacing:.12em;text-transform:uppercase;color:var(--accent-ink);margin:0 0 12px}
.doc-title{font-size:2rem;line-height:1.25;letter-spacing:-.025em;margin:0 0 10px;font-weight:750}
.doc-sub{font-size:1.2rem;line-height:1.5;letter-spacing:-.01em;color:var(--muted);font-weight:500;margin:0 0 8px}
.doc-meta{font-size:13px;color:var(--faint);margin:18px 0 0;padding-top:16px;border-top:1px solid var(--line-soft)}
article h2{font-size:1.45rem;letter-spacing:-.02em;line-height:1.35;margin:2.4em 0 .7em;padding-bottom:.4em;border-bottom:1px solid var(--line);font-weight:700}
article h3{font-size:1.15rem;letter-spacing:-.01em;margin:2em 0 .5em;font-weight:700}
article h4{font-size:1rem;margin:1.6em 0 .4em;font-weight:700}
article h2:hover .anchor,article h3:hover .anchor{opacity:1}
.anchor{opacity:0;margin-left:8px;font-size:.75em;font-weight:400;transition:opacity .15s}
article p{margin:0 0 1.1em}
article ul,article ol{margin:0 0 1.2em;padding-left:1.6em}
article li{margin-bottom:.45em}
article li::marker{color:var(--accent-ink)}
article code{font-family:var(--mono);font-size:.85em;background:var(--code-bg);border:1px solid var(--line-soft);border-radius:6px;padding:.15em .4em;white-space:break-spaces}
.callout{background:var(--callout-bg);border:1px solid var(--line);border-left:3px solid var(--accent);border-radius:0 10px 10px 0;padding:14px 18px;margin:1.4em 0;font-size:.95rem}
.callout p{margin:0}
.math{background:var(--math-bg);border:1px solid var(--line-soft);border-radius:10px;padding:16px 20px;margin:1.3em 0;font-family:var(--mono);font-size:.9rem;text-align:center;overflow-x:auto;white-space:pre-wrap}
.table-wrap{overflow-x:auto;margin:1.4em 0;border:1px solid var(--line);border-radius:10px}
table{width:100%;border-collapse:collapse;font-size:.875rem;line-height:1.6;margin:0}
th,td{padding:10px 14px;border-bottom:1px solid var(--line-soft);text-align:left;vertical-align:top}
thead th{background:var(--th-bg);font-size:.72rem;letter-spacing:.07em;text-transform:uppercase;color:var(--muted);border-bottom:1px solid var(--line);white-space:nowrap}
tbody tr:last-child td{border-bottom:0}
tbody tr:hover td{background:color-mix(in srgb,var(--accent) 4%,transparent)}
figure.code{margin:1.4em 0;border:1px solid var(--line);border-radius:10px;overflow:hidden}
figure.code figcaption{display:flex;align-items:center;gap:7px;background:var(--th-bg);border-bottom:1px solid var(--line);padding:8px 12px;font-family:var(--mono);font-size:12px;color:var(--muted)}
figure.code .dot{width:10px;height:10px;border-radius:50%;background:var(--line)}
figure.code .lang{margin-left:4px}
figure.code .copy{margin-left:auto;font-family:var(--font);font-size:12px;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px;padding:3px 10px;cursor:pointer}
figure.code .copy:hover{color:var(--ink);border-color:var(--faint)}
figure.code .wrap{font-family:var(--font);font-size:12px;color:var(--muted);background:transparent;border:1px solid var(--line);border-radius:6px;padding:3px 10px;cursor:pointer}
figure.code .wrap:hover{color:var(--ink);border-color:var(--faint)}
figure.code.wrap pre{white-space:pre-wrap;word-break:break-word}
figure.code pre{margin:0;background:var(--code-bg);padding:16px 18px;overflow-x:auto;font-family:var(--mono);font-size:13.5px;line-height:1.7}
figure.code pre code{background:none;border:0;padding:0;font-size:inherit}
.callout-title{display:flex;align-items:center;gap:8px;font-weight:700;margin:0 0 6px;font-size:.9rem}
.callout-title .ico{flex:none;width:22px;height:22px;border-radius:6px;display:inline-flex;align-items:center;justify-content:center;font-size:13px;border:1px solid var(--line)}
.callout-custom{font-weight:600}
.callout-note{border-left-color:#2563eb;background:color-mix(in srgb,#2563eb 7%,var(--paper))}
.callout-note .ico{color:#2563eb;border-color:#2563eb}
.callout-tip{border-left-color:#16a34a;background:color-mix(in srgb,#16a34a 7%,var(--paper))}
.callout-tip .ico{color:#16a34a;border-color:#16a34a}
.callout-important{border-left-color:#9333ea;background:color-mix(in srgb,#9333ea 8%,var(--paper))}
.callout-important .ico{color:#9333ea;border-color:#9333ea}
.callout-warning{border-left-color:#d97706;background:color-mix(in srgb,#d97706 8%,var(--paper))}
.callout-warning .ico{color:#d97706;border-color:#d97706}
.callout-caution{border-left-color:#dc2626;background:color-mix(in srgb,#dc2626 8%,var(--paper))}
.callout-caution .ico{color:#dc2626;border-color:#dc2626}
.task-list{list-style:none;padding-left:1.2em}
.task-list .task{display:flex;gap:8px;align-items:baseline}
.task input{flex:none;width:15px;height:15px;transform:translateY(2px);accent-color:var(--accent)}
figure.fig{margin:1.6em 0;text-align:center}
figure.fig img{display:block;margin:0 auto}
figure.fig figcaption{font-size:13px;color:var(--muted);margin-top:8px}
article{counter-reset:h2}
article h2{counter-increment:h2;counter-reset:h3}
article h2::before{content:counter(h2)". ";color:var(--faint);font-weight:600}
article h3{counter-increment:h3}
article h3::before{content:counter(h2)"."counter(h3)" ";color:var(--faint);font-weight:600}
.toc-filter{width:100%;font:inherit;font-size:13px;color:var(--ink);background:var(--paper);border:1px solid var(--line);border-radius:8px;padding:7px 10px;margin:0 0 10px}
.toc a.hide{display:none}
.toc .n{color:var(--faint);font-variant-numeric:tabular-nums;margin-right:6px}
.table-wrap{max-height:min(70vh,640px)}
thead th{position:sticky;top:0;z-index:2}
hr{border:0;border-top:1px solid var(--line);margin:2.5em 0}
img{max-width:100%;border-radius:8px}
footer{max-width:1120px;margin:0 auto;padding:0 24px 48px;color:var(--faint);font-size:13px}
.totop{position:fixed;right:22px;bottom:22px;width:40px;height:40px;border-radius:50%;border:1px solid var(--line);background:var(--paper);color:var(--muted);font-size:18px;cursor:pointer;opacity:0;pointer-events:none;transition:opacity .2s;box-shadow:var(--shadow)}
.totop.show{opacity:1;pointer-events:auto}
@media(max-width:900px){.layout{grid-template-columns:1fr;gap:0}.toc{display:none}article{padding:28px 22px}}
@media print{.topbar,.toc,.theme-btn,.totop,.progress,.copy,.wrap,.toc-filter{display:none!important}.layout{display:block;padding:0}article{border:0;box-shadow:none}body{background:#fff}table,figure.code,figure.fig,.callout,.math{page-break-inside:avoid}article h2{page-break-after:avoid}}
"""

_JS_TEMPLATE = r"""
(function(){var r=document.documentElement;var saved=null;try{saved=localStorage.getItem('md-theme')}catch(e){}
function theme(){return saved||(matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light')}
function apply(t){r.setAttribute('data-theme',t);var b=document.getElementById('themeBtn');if(b)b.textContent=t==='dark'?'@@theme_dark@@':'@@theme_light@@'}
apply(theme());var btn=document.getElementById('themeBtn');if(btn)btn.addEventListener('click',function(){var t=r.getAttribute('data-theme')==='dark'?'light':'dark';saved=t;try{localStorage.setItem('md-theme',t)}catch(e){}apply(t)});
function copyText(t,ok){function done(btn){if(!btn)return;var o=btn.textContent;btn.textContent='@@copied@@';setTimeout(function(){btn.textContent=o},1400)}
if(navigator.clipboard&&navigator.clipboard.writeText){navigator.clipboard.writeText(t).then(function(){done(document.activeElement)}).catch(function(){fallback()})}else{fallback()}
function fallback(){var ta=document.createElement('textarea');ta.value=t;document.body.appendChild(ta);ta.select();try{document.execCommand('copy');done(document.activeElement)}catch(e){}document.body.removeChild(ta)}}
document.querySelectorAll('figure.code').forEach(function(f){var b=f.querySelector('.copy');if(b)b.addEventListener('click',function(){copyText(f.querySelector('code').innerText);var o='@@copy@@';b.textContent='@@copied@@';setTimeout(function(){b.textContent=o},1400)});
var w=f.querySelector('.wrap');if(w)w.addEventListener('click',function(){f.classList.toggle('wrap');w.textContent=f.classList.contains('wrap')?'@@unwrap@@':'@@wrap@@'})});
var bar=document.getElementById('bar');addEventListener('scroll',function(){var h=document.documentElement;var p=h.scrollTop/Math.max(1,h.scrollHeight-h.clientHeight);if(bar)bar.style.width=(p*100)+'%';var tt=document.getElementById('totop');if(tt)tt.classList.toggle('show',h.scrollTop>800)},{passive:true});
var tt=document.getElementById('totop');if(tt)tt.addEventListener('click',function(){scrollTo({top:0,behavior:'smooth'})});
var links=Array.prototype.slice.call(document.querySelectorAll('.toc a'));var secs=links.map(function(a){return document.querySelector(a.getAttribute('href'))}).filter(Boolean);
if('IntersectionObserver' in window&&secs.length){var obs=new IntersectionObserver(function(es){es.forEach(function(e){if(e.isIntersecting){links.forEach(function(a){a.classList.toggle('active',a.getAttribute('href')==='#'+e.target.id)})}})},{rootMargin:'-20% 0px -70% 0px'});secs.forEach(function(s){obs.observe(s)})}
document.querySelectorAll('article h2[id],article h3[id]').forEach(function(h){var a=document.createElement('a');a.className='anchor';a.href='#'+h.id;a.title='@@copy_link@@';a.textContent='¶';a.addEventListener('click',function(ev){var url=location.href.split('#')[0]+'#'+h.id;if(navigator.clipboard&&navigator.clipboard.writeText){ev.preventDefault();navigator.clipboard.writeText(url);history.replaceState(null,'','#'+h.id);a.textContent='✓';setTimeout(function(){a.textContent='¶'},1200)}});h.appendChild(a)});
var tf=document.getElementById('tocFilter');if(tf){tf.addEventListener('input',function(){var q=tf.value.toLowerCase();document.querySelectorAll('.toc a').forEach(function(a){a.classList.toggle('hide',q&&a.textContent.toLowerCase().indexOf(q)<0)})})}
})();
// Host bridge: chi hoat dong khi trang duoc nhung trong iframe preview cua app
// (no-op khi mo standalone bang browser).
(function(){if(window.parent===window)return;
function post(o){try{window.parent.postMessage(o,'*')}catch(e){}}
post({t:'mdhtml:loaded'});
addEventListener('message',function(e){var d=e.data||{};if(d&&d.t==='mdhtml:scroll'){try{scrollTo(0,Number(d.y)||0)}catch(err){}}});
var t=null;addEventListener('scroll',function(){if(t)return;t=setTimeout(function(){t=null;post({t:'mdhtml:at',y:scrollY,h:document.documentElement.scrollHeight})},120)},{passive:true});
})();
"""

_JS_TOKENS = ("theme_dark", "theme_light", "copied", "copy", "unwrap", "wrap", "copy_link")


def _js(L: dict) -> str:
    """JS cua trang: thay tung @@ma@@ bang nhan cua ngon ngu (vi cho ra y nguyen ban cu)."""
    out = _JS_TEMPLATE
    for k in _JS_TOKENS:
        out = out.replace(f"@@{k}@@", L[k])
    return out


JS = _js(_LABELS["vi"])

PAGE = """<!DOCTYPE html>
<html lang="{lang}">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>{css}</style>
</head>
<body>
<div class="topbar"><div class="topbar-in">
<span class="crumbs">{crumb}</span>
<button class="theme-btn" id="themeBtn" type="button">{theme_light}</button>
</div><div class="progress" id="bar"></div></div>
<div class="layout">
<nav class="toc" aria-label="{toc_title}"><h2>{toc_title}</h2>
<input class="toc-filter" id="tocFilter" type="search" placeholder="{toc_filter}" autocomplete="off">
<div class="toc-list" id="tocList">
{toc}
</div>
</nav>
<main><article>
<p class="doc-eyebrow">{eyebrow}</p>
<h1 class="doc-title">{title}</h1>
{sub}
{body}
<p class="doc-meta">{source_label} <code>{source}</code> · {made_by} <code>md_to_html.py</code> · {date} · {stats}</p>
</article></main>
</div>
<footer>{footer}</footer>
<button class="totop" id="totop" type="button" aria-label="{totop}">↑</button>
<script>{js}</script>
</body>
</html>
"""


def atomic_write_text(path: Path, text: str) -> None:
    """Ghi nguyen tu: tmp + replace de khong de lai file nua voi khi crash."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(path)


def _count(L: dict, key: str, n: int) -> str:
    return f"{n} {L[key + ('_one' if n == 1 else '_many')]}"


def doc_stats(md_text: str, body_html: str, lang: str = "vi") -> str:
    L = _labels(lang)
    words = len(re.findall(r"\w+", md_text, flags=re.UNICODE))
    mins = max(1, (words + 199) // 200)
    parts = [_count(L, "words", words), f"~{mins} {L['read']}"]
    tables = body_html.count("<table>")
    codes = body_html.count('<figure class="code">')
    if tables:
        parts.append(_count(L, "tables", tables))
    if codes:
        parts.append(_count(L, "codes", codes))
    return " · ".join(parts)


def convert(md_text: str, source_name: str, doc_title: str = "",
            eyebrow: str = "Tài liệu kỹ thuật", lang: str = "vi",
            with_toc: bool = True, date_str: str = "") -> str:
    L = _labels(lang)
    if _is_en(lang) and eyebrow in ("", _VI_EYEBROW):
        eyebrow = L["eyebrow"]
    p = Parser(lang)
    body = p.parse(md_text)
    # Tieu de: # dau tien -> title; ## ke tiep (neu sat sau) -> subtitle.
    title = doc_title
    sub = ""
    if not title:
        m = re.search(r'<h1 id="[^"]+">(.*?)</h1>', body)
        if m:
            title = html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))
            body = body.replace(m.group(0), "", 1)
    m2 = re.match(r"\s*<h2 id=\"[^\"]+\">(.*?)</h2>", body)
    if m2 and len(re.sub(r"<[^>]+>", "", m2.group(1))) < 140:
        sub = f'<p class="doc-sub">{m2.group(1)}</p>'
        body = body.replace(m2.group(0), "", 1)
    if not title:
        title = Path(source_name).stem
    toc_html = ""
    if with_toc:
        # Xac dinh subtitle bi tach de bo khoi TOC
        skip_first = False
        if sub and p.toc and p.toc[0][0] == 2:
            plain = re.sub(r"<[^>]+>", "", p.toc[0][2])
            if plain in sub:
                skip_first = True
        h2_num, h3_num = 0, 0
        parts = []
        for idx, (level, hid, text) in enumerate(p.toc):
            if idx == 0 and skip_first:
                continue
            if level == 2:
                h2_num += 1
                h3_num = 0
                num = f"{h2_num}."
            else:
                h3_num += 1
                num = f"{h2_num}.{h3_num}"
            parts.append(
                f'<a class="l{level}" href="#{hid}"><span class="n">{num}</span>{text}</a>'
            )
        toc_html = "\n".join(parts)
    date = date_str.strip() or datetime.now().strftime("%d/%m/%Y")
    stats = doc_stats(md_text, body, lang)
    return PAGE.format(
        lang=lang,
        title=html.escape(title, quote=False),
        css=CSS,
        js=_js(L),
        crumb=f"{L['crumb']} <b>{html.escape(title, quote=False)}</b>",
        eyebrow=html.escape(eyebrow),
        sub=sub,
        body=body,
        source=html.escape(source_name, quote=False),
        source_label=L["source"],
        made_by=L["made_by"],
        date=date,
        stats=stats,
        toc=toc_html,
        toc_title=L["toc"],
        toc_filter=L["toc_filter"],
        theme_light=L["theme_light"],
        footer=L["footer"],
        totop=L["totop"],
    )


def _convert_one(src: Path, out: Path, title: str, eyebrow: str,
                 lang: str, no_toc: bool, date_str: str) -> tuple[bool, str]:
    """Single-writer: CLI (main) va UI (mdhtml.bridge.run_convert) deu qua day.
    Doc utf-8-sig -> convert() -> ghi nguyen tu. Khong resolve output o day."""
    try:
        md_text = src.read_text(encoding="utf-8-sig")
    except OSError as e:
        return False, f"Khong doc duoc: {src} ({e})"
    page = convert(
        md_text,
        source_name=src.name,
        doc_title=title,
        eyebrow=eyebrow,
        lang=lang,
        with_toc=not no_toc,
        date_str=date_str,
    )
    try:
        out.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out, page)
    except OSError as e:
        return False, f"Khong ghi duoc: {out} ({e})"
    return True, f"OK: {src} -> {out} ({len(page) // 1024} KB)"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Convert Markdown sang HTML tai lieu offline.")
    ap.add_argument("input", help="File .md hoac thu muc chua .md")
    ap.add_argument("-o", "--output", default="", help="File .html (1 file) hoac thu muc ra (batch)")
    ap.add_argument("--title", default="", help="Tieu de trang (mac dinh: lay tu dong # dau tien; batch: bo qua)")
    ap.add_argument("--eyebrow", default="Tài liệu kỹ thuật", help="Dong chu nho tren tieu de")
    ap.add_argument("--lang", default="vi")
    ap.add_argument("--date", default="", help="Ngay hien thi (mac dinh: hom nay dd/mm/yyyy)")
    ap.add_argument("--recursive", action="store_true", help="Quet .md de quy khi input la thu muc")
    ap.add_argument("--no-toc", action="store_true", help="Tat muc luc sidebar")
    args = ap.parse_args(argv)

    src = Path(args.input)
    # Batch: input la thu muc
    if src.is_dir():
        pattern = "**/*.md" if args.recursive else "*.md"
        files = sorted(p for p in src.glob(pattern) if p.is_file())
        if not files:
            print(f"Khong thay file .md trong: {src}", file=sys.stderr)
            return 1
        out_dir = Path(args.output) if args.output else src
        if out_dir.suffix.lower() == ".html":
            print("Input la thu muc thi -o phai la thu muc, khong phai file .html.", file=sys.stderr)
            return 1
        ok_count = 0
        for f in files:
            if args.output:
                try:
                    rel = f.relative_to(src)
                except ValueError:
                    rel = Path(f.name)
                out = out_dir / rel.with_suffix(".html")
            else:
                out = f.with_suffix(".html")
            if out.resolve() == f.resolve():
                print(f"Bo qua (trung input): {f}", file=sys.stderr)
                continue
            ok, msg = _convert_one(f, out, "", args.eyebrow, args.lang, args.no_toc, args.date)
            print(msg, file=sys.stderr if not ok else sys.stdout)
            if ok:
                ok_count += 1
        print(f"Xong {ok_count}/{len(files)} file.")
        return 0 if ok_count == len(files) else 1
    if not src.is_file():
        print(f"Khong tim thay file: {src}", file=sys.stderr)
        return 1
    out = Path(args.output) if args.output else src.with_suffix(".html")
    if out.is_dir():
        out = out / (src.stem + ".html")
    if out.resolve() == src.resolve():
        print("File ra trung file vao.", file=sys.stderr)
        return 1

    ok, msg = _convert_one(src, out, args.title, args.eyebrow, args.lang, args.no_toc, args.date)
    print(msg, file=sys.stderr if not ok else sys.stdout)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
