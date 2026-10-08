# MD to HTML

Biến file Markdown (`.md`) thành trang web `.html` trình bày sẵn. Mở bằng Chrome hoặc Edge là đọc được ngay, không cần máy chủ, không cần mạng sau lần cài đầu.

App desktop có 3 cột: thả file `.md` vào là tool tự tạo HTML và xem trước ngay. Sửa file bên ngoài thì phần xem trước tự cập nhật. Phần lõi chuyển đổi và CLI chỉ dùng thư viện chuẩn của Python.

## Cài đặt (Windows)

- Python 3.10 trở lên. Khi cài, tick **Add Python to PATH**.
- Microsoft Edge WebView2 Runtime. Windows 10/11 thường có sẵn; thiếu thì cài từ trang của Microsoft.
- Lần đầu chạy app cần Internet một lần để cài `pywebview` (ghim phiên bản 6.2.1 trong `requirements.txt`).

## Cách chạy

| Cách | Lệnh |
|---|---|
| App desktop (khuyên dùng) | Double-click `run.bat`, thả `.md` vào cửa sổ |
| Kéo-thả vào launcher | Thả file `.md` lên `run.bat`, chạy CLI |
| CLI một file | `.venv\Scripts\python.exe md_to_html.py TAILIEU.md [-o web.html] [--title T] [--eyebrow E] [--lang vi] [--date 20/09/2026] [--no-toc]` |
| CLI cả thư mục | `.venv\Scripts\python.exe md_to_html.py THU_MUC\ [-o OUT_DIR] [--recursive]` |

Mặc định `x.md` ra `x.html` cùng thư mục. Tool không bao giờ ghi đè file đầu vào.

Lưu ý: `run.bat` tạo `.venv` và cài `pywebview` trước khi chạy CLI, nên lần đầu cần Internet. Nếu chỉ cần CLI, có thể chạy thẳng `python md_to_html.py TAILIEU.md` (Python 3.10+, không cần cài gì thêm).

## Hỗ trợ và giới hạn

Hỗ trợ: tiêu đề và mục lục đánh số, bảng kiểu GitHub, khối code có nút Copy và Wrap, callout 5 loại (NOTE, TIP, IMPORTANT, WARNING, CAUTION), danh sách lồng và task list, ảnh kèm chú thích, chế độ Sáng/Tối, số từ và thời gian đọc.

Không hỗ trợ: footnote, Mermaid, KaTeX (công thức giữ nguyên dạng chữ), tô màu cú pháp theo ngôn ngữ, ghép nhiều file thành một trang, setext heading.

Bảo mật: nội dung Markdown được escape khi ra HTML, nhưng tool không được thiết kế làm bộ lọc cho nội dung không tin cậy. Chỉ render file bạn tin.

## Test

```
pip install pytest
python -m pytest tests -q
```

Nếu chưa cài `pywebview`, hai file test giao diện (`test_api.py`, `test_drop.py`) bị bỏ qua, phần còn lại vẫn chạy.

## Giấy phép

MIT, xem [LICENSE](LICENSE). Thư viện dùng kèm: `pywebview` (BSD 3-Clause).

---

## English

MD to HTML converts Markdown files into self-contained HTML pages that open offline in Chrome or Edge. It has a Windows desktop app (pywebview, three-pane preview with auto-cache) and a command-line tool. Table of contents, dark/light mode, code copy buttons and GitHub-style callouts are included.

- Requirements: Python 3.10+, Microsoft Edge WebView2 Runtime (Windows).
- Run: double-click `run.bat`, or `python md_to_html.py file.md`.
- The converter and CLI use only the Python standard library. Only the desktop app needs `pywebview` (pinned to 6.2.1).
- Tests: `pip install pytest`, then `python -m pytest tests -q`.
- License: MIT.
