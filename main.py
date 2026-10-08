from __future__ import annotations

import sys
import traceback
from pathlib import Path


def _fatal(root: Path, exc: Exception):
    try:
        (root / "md_to_html_error.log").write_text(traceback.format_exc(), "utf-8")
    except Exception:
        pass
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.user32.MessageBoxW(
                0,
                f"Meinya MD to HTML không thể khởi động:\n\n{exc}\n\nChi tiết: md_to_html_error.log",
                "MD to HTML · Error", 0x10)
            return
        except Exception:
            pass
    print(f"[MD to HTML] Fatal: {exc}", file=sys.stderr)


def extract_dropped_paths(event) -> list:
    """Trich full path .md tu pywebview DOM drop event.

    pywebview mo rong DropEvent voi duong dan that phia Python:
    event['dataTransfer']['files'][i]['pywebviewFullPath'] (ban cu ghi
    'domTransfer'). Ho tro ca 2 key de chiu nhieu version.
    """
    try:
        transfer = event.get("dataTransfer") or event.get("domTransfer") or {}
        files = transfer.get("files") or []
    except AttributeError:
        return []
    out = []
    for f in files:
        try:
            p = f.get("pywebviewFullPath")
        except AttributeError:
            continue
        if p and str(p).lower().endswith(".md"):
            out.append(str(p))
    return out


def make_drop_handler(api, window):
    """Tao callback cho DOM drop event: them path that + bao frontend refresh.

    Ham thuan (khong import webview) de test duoc headless; register_drop_handler
    boc no bang DOMEventHandler that.
    """
    def on_drop(event):
        try:
            paths = extract_dropped_paths(event)
            if not paths:
                return
            api.add_dropped_paths(paths)
            try:
                window.evaluate_js("window.__mdRefresh && window.__mdRefresh()")
            except Exception:
                pass
        except Exception:
            pass

    return on_drop


def register_drop_handler(window, api) -> bool:
    """Dang ky drop-native len window pywebview. Tra False khi renderer/khong
    ho tro -> UI giu fallback stage text (add_dropped_files)."""
    try:
        from webview.dom import DOMEventHandler

        window.dom.document.events.drop += DOMEventHandler(
            make_drop_handler(api, window), True, True)
        return True
    except Exception:
        return False


def main():
    import webview
    from api import MdHtmlAPI

    root = Path(__file__).resolve().parent
    api = MdHtmlAPI(root)
    window = webview.create_window(
        "Meinya MD to HTML",
        url=(root / "web" / "index.html").as_uri(),
        js_api=api,
        width=1440,
        height=900,
        min_size=(1120, 700),
        background_color="#0b0b0c",
        text_select=True,
    )
    api.bind_window(window)

    def bind(window):
        register_drop_handler(window, api)
        try:
            window.events.closed += lambda: api.close()
        except Exception:
            pass

    webview.start(bind, window, debug=False)


if __name__ == "__main__":
    root = Path(__file__).resolve().parent
    try:
        main()
    except Exception as exc:
        _fatal(root, exc)
