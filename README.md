# Meinya MD to HTML

Biến file Markdown (`.md`) thành trang HTML trình bày sẵn. Mở bằng Chrome hoặc Edge là đọc được ngay, không cần máy chủ và không cần mạng.

![Giao diện app: cột nguồn, xem trước, tùy chọn](docs/01-giao-dien.png)

## Bắt đầu nhanh

1. Tải repo về (nút **Code → Download ZIP**) rồi giải nén vào một thư mục.
2. Bấm đúp **`run.bat`**. Lần đầu máy tự tạo `.venv` và cài `pywebview` đúng bản đã ghim (cần Internet một lần; Python 3.10 trở lên từ python.org, nhớ tick *Add Python to PATH*).
3. Thả một file `.md` vào cửa sổ. App tự tạo file HTML cạnh file gốc và hiện bản xem trước.

Chạy lại sau này chỉ cần bấm `run.bat`.

## Tính năng

| Tính năng | Có sẵn | Tải khi cần |
|---|---|---|
| Chuyển Markdown thành HTML, CLI một file hoặc cả thư mục (chỉ dùng thư viện chuẩn của Python) | ✅ | |
| App desktop 3 cột: nguồn, xem trước, tùy chọn; tự cập nhật khi file đổi | ✅ | |
| Mục lục, bảng kiểu GitHub, khối code có nút Copy và Wrap, callout 5 loại, task list, chế độ Sáng/Tối | ✅ | |
| Xuất một file hoặc tất cả, cache cạnh file gốc hoặc trong thư mục của tool | ✅ | |
| Cửa sổ desktop (`pywebview` 6.2.1 và các thư viện nó kéo theo) | | Không có. Lần đầu chạy app, `run.bat` cài sẵn, khoảng 3 MB trên đĩa (đo trong venv mới, không tính pip) |

Không có thành phần nào phải bấm bật để tải thêm. Chạy CLI không cần cài gì thêm ngoài Python.

## Yêu cầu

- Windows 10 hoặc 11 cho app desktop.
- Python 3.10 trở lên.
- Microsoft Edge WebView2 Runtime cho app desktop. Windows 10/11 thường có sẵn; thiếu thì cài từ trang của Microsoft.

## Dòng lệnh

| Cách | Lệnh |
|---|---|
| App desktop | Double-click `run.bat`, thả `.md` vào cửa sổ |
| Kéo-thả vào launcher | Thả file `.md` lên `run.bat`, chạy CLI |
| CLI một file | `.venv\Scripts\python.exe md_to_html.py TAILIEU.md [-o web.html] [--title T] [--eyebrow E] [--lang vi] [--date 20/09/2026] [--no-toc]` |
| CLI cả thư mục | `.venv\Scripts\python.exe md_to_html.py THU_MUC\ [-o OUT_DIR] [--recursive]` |

Mặc định `x.md` ra `x.html` cùng thư mục. Tool không bao giờ ghi đè file đầu vào.

Nếu chỉ cần CLI, có thể chạy thẳng `python md_to_html.py TAILIEU.md` với Python 3.10 trở lên, không cần `run.bat`.

## Hỗ trợ và giới hạn

Hỗ trợ: tiêu đề và mục lục đánh số, bảng kiểu GitHub, khối code có nút Copy và Wrap, callout 5 loại (NOTE, TIP, IMPORTANT, WARNING, CAUTION), danh sách lồng và task list, ảnh kèm chú thích, chế độ Sáng/Tối, số từ và thời gian đọc.

Không hỗ trợ: footnote, Mermaid, KaTeX (công thức giữ nguyên dạng chữ), tô màu cú pháp theo ngôn ngữ, ghép nhiều file thành một trang, setext heading.

Bảo mật: nội dung Markdown được escape khi ra HTML, nhưng tool không được thiết kế làm bộ lọc cho nội dung không tin cậy. Chỉ render file bạn tin.

## Test

```bat
.venv\Scripts\python.exe -m pip install pytest
.venv\Scripts\python.exe -m pytest tests -q
```

`pytest` không đi kèm app, chỉ cài khi bạn muốn chạy test. Nếu chưa cài `pywebview`, hai file test giao diện (`test_api.py`, `test_drop.py`) bị bỏ qua, phần còn lại vẫn chạy.

## Giấy phép

- Mã của repo: MIT, xem [LICENSE](LICENSE).
- Thư viện cài khi chạy `run.bat`:

| Thư viện | Phiên bản | Giấy phép |
|---|---|---|
| pywebview | 6.2.1 | BSD-3-Clause |
| pythonnet | 3.2.1 | MIT |
| clr-loader | 0.3.1 | MIT |
| cffi | 2.1.1 | MIT-0 |
| pycparser | 3.1 | BSD-3-Clause |
| proxy_tools | 0.1.0 | MIT |
| bottle | 0.13.4 | MIT |
| typing_extensions | 4.16.0 | PSF-2.0 |

---

## English

MD to HTML converts Markdown files into self-contained HTML pages that open offline in Chrome or Edge. It has a Windows desktop app (pywebview, three-pane preview with auto-cache) and a command-line tool. Table of contents, dark/light mode, code copy buttons and GitHub-style callouts are included.

- **Quick start:** download the ZIP, double-click `run.bat` (first run creates `.venv` and installs the pinned `pywebview`; Python 3.10+ needed), then drop a `.md` file into the window.
- **Downloaded on demand:** nothing. The app installs `pywebview` and its dependencies (about 3 MB on disk) on first run.
- **Requirements:** Python 3.10+, Microsoft Edge WebView2 Runtime (Windows, for the desktop app).
- **Tests:** `.venv\Scripts\python.exe -m pip install pytest`, then `.venv\Scripts\python.exe -m pytest tests -q`.
- **License:** MIT.
