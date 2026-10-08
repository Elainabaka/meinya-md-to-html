"""Cache HTML cho Meinya MD to HTML — pure stdlib, khong UI, khong dialog.

Trach nhiem:
- Quyet dinh file .html dich (canh file .md hoac trong cache cua tool).
- Nhung marker `<!-- mdhtml:cache {...} -->` vao HTML de biet cache con dung
  (settings + mtime + size cua nguon) — file .html tu mo ta trang thai cache.
- Khong bao gio ghi de file .html khong phai cua tool (khong marker): fallback
  sang cache dir + co `fallback=True` cho UI bao nguoi dung.

Ghi file nguyen tu (tmp + os.replace) qua md_to_html.atomic_write_text.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from md_to_html import atomic_write_text

CACHE_VERSION = 2
CACHE_MODES = ("beside", "tool")

MARKER_RE = re.compile(r"<!--\s*mdhtml:cache\s+(\{.*?\})\s*-->")
_BODY_END_RE = re.compile(r"</body>", re.IGNORECASE)


def effective_date(date_str: str) -> str:
    """Ngay hien thi: user nhap hoac hom nay (dd/mm/yyyy)."""
    return (date_str or "").strip() or datetime.now().strftime("%d/%m/%Y")


def settings_key(settings: dict) -> str:
    """Fingerprint cua settings anh huong noi dung render (khong gom path)."""
    s = settings or {}
    payload = {
        "title": str(s.get("title", "")).strip(),
        "eyebrow": str(s.get("eyebrow", "")).strip(),
        "lang": str(s.get("lang", "vi")).strip() or "vi",
        "no_toc": bool(s.get("no_toc", False)),
        "date": effective_date(str(s.get("date", ""))),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:16]


def cache_target(src: Path, mode: str, cache_dir: Path) -> Path:
    """Duong dan .html dich theo mode. mode la ('beside'|'tool')."""
    if mode == "tool":
        digest = hashlib.sha1(str(src.parent).encode("utf-8")).hexdigest()[:12]
        return Path(cache_dir) / digest / (src.stem + ".html")
    return src.with_suffix(".html")


def read_marker(html_text: str) -> dict | None:
    m = MARKER_RE.search(html_text or "")
    if not m:
        return None
    try:
        data = json.loads(m.group(1))
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


def embed_marker(html_text: str, marker: dict) -> str:
    """Chen marker ngay truoc </body> (khong doi hien thi trang)."""
    tag = f"<!-- mdhtml:cache {json.dumps(marker, ensure_ascii=False, sort_keys=True)} -->"
    m = None
    for m in _BODY_END_RE.finditer(html_text):
        pass
    if m is None:
        return html_text + "\n" + tag + "\n"
    return html_text[:m.start()] + tag + "\n" + html_text[m.start():]


def make_marker(src: Path, src_stat, key: str, date_str: str) -> dict:
    return {
        "v": CACHE_VERSION,
        "key": key,
        "src": src.name,
        "mtime": int(src_stat.st_mtime_ns),
        "size": int(src_stat.st_size),
        "date": date_str,
    }


def decide(target: Path, marker: dict | None, src_stat, key: str, src_name: str) -> str:
    """'missing' | 'foreign' | 'stale' | 'fresh' cho file .html dich."""
    try:
        if not target.is_file():
            return "missing"
    except OSError:
        return "missing"
    if marker is None:
        return "foreign"
    if int(marker.get("v", -1)) != CACHE_VERSION:
        return "stale"
    if marker.get("key") != key or marker.get("src") != src_name:
        return "stale"
    try:
        if int(marker.get("mtime", -1)) != int(src_stat.st_mtime_ns):
            return "stale"
        if int(marker.get("size", -1)) != int(src_stat.st_size):
            return "stale"
    except (TypeError, ValueError):
        return "stale"
    return "fresh"


def content_hash(path: Path) -> str:
    """sha1 noi dung file — de skip render khi bytes khong doi."""
    h = hashlib.sha1()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _render(text: str, name: str, settings: dict) -> dict:
    from mdhtml.bridge import render_text
    s = settings or {}
    return render_text(
        text, name,
        title=str(s.get("title", "")),
        eyebrow=str(s.get("eyebrow", "")),
        lang=str(s.get("lang", "vi")),
        no_toc=bool(s.get("no_toc", False)),
        date_str=str(s.get("date", "")),
    )


def ensure(src, settings: dict, *, mode: str = "beside", cache_dir=None,
           force: bool = False, render=None) -> dict:
    """Dam bao co ban .html cache dung cho `src`. Tra dict trang thai.

    state: 'fresh'   — cache con dung, khong render lai
           'rendered'— vua render + ghi
           'missing' — khong thay/khong doc duoc file nguon
           'error'   — render hoac ghi loi
    """
    src = Path(src)
    cache_dir = Path(cache_dir) if cache_dir else src.parent / ".md_to_html_cache"
    render = render or _render
    name = src.name
    if not src.is_file():
        return {"ok": False, "state": "missing", "path": "", "fallback": False,
                "msg": "Khong thay file nguon."}
    try:
        src_stat = src.stat()
    except OSError as exc:
        return {"ok": False, "state": "missing", "path": "", "fallback": False,
                "msg": f"Khong doc duoc file nguon: {exc}"}

    key = settings_key(settings)
    fallback = False
    target = cache_target(src, mode, cache_dir)

    if target.is_file():
        try:
            existing = target.read_text(encoding="utf-8", errors="replace")
        except OSError:
            existing = ""
        marker = read_marker(existing)
        state = decide(target, marker, src_stat, key, name)
        if state == "foreign" and mode == "beside":
            # File .html khong phai cua tool: khong ghi de, lui ve cache dir.
            fallback = True
            target = cache_target(src, "tool", cache_dir)
            if target.is_file():
                try:
                    existing = target.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    existing = ""
                marker = read_marker(existing)
                state = decide(target, marker, src_stat, key, name)
        if state == "fresh" and not force:
            try:
                size = target.stat().st_size
            except OSError:
                size = 0
            return {"ok": True, "state": "fresh", "path": str(target),
                    "fallback": fallback, "msg": "", "stats": "",
                    "mtime": int(src_stat.st_mtime_ns), "size": int(src_stat.st_size),
                    "out_size": int(size), "date": effective_date(str((settings or {}).get("date", "")))}

    try:
        text = src.read_text(encoding="utf-8-sig")
    except OSError as exc:
        return {"ok": False, "state": "error", "path": "", "fallback": fallback,
                "msg": f"Khong doc duoc file: {exc}"}

    res = render(text, name, settings)
    if not res.get("ok"):
        return {"ok": False, "state": "error", "path": "", "fallback": fallback,
                "msg": str(res.get("error") or "Render loi.")}

    marker = make_marker(src, src_stat, key, effective_date(str((settings or {}).get("date", ""))))
    page = embed_marker(res["html"], marker)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(target, page)
    except OSError as exc:
        return {"ok": False, "state": "error", "path": "", "fallback": fallback,
                "msg": f"Khong ghi duoc cache: {exc}"}

    return {"ok": True, "state": "rendered", "path": str(target), "fallback": fallback,
            "msg": "", "stats": str(res.get("stats", "")),
            "mtime": int(src_stat.st_mtime_ns), "size": int(src_stat.st_size),
            "out_size": len(page.encode("utf-8")), "date": marker["date"]}
