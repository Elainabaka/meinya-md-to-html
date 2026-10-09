"""Data model shared by the engine, the reports, the MCP server and the hook."""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field

ERROR, WARNING, INFO = "error", "warning", "info"
SEVERITY_RANK = {INFO: 0, WARNING: 1, ERROR: 2}


@dataclass
class Claim:
    """One checkable statement a doc makes about the repo."""

    kind: str           # path, link, command, symbol, flag, subcommand, npm, make, decision, version, dep
    text: str           # as written in the doc
    target: str         # normalized thing to check
    doc: str            # doc path, relative to the scan root, posix
    line: int
    col: int = 1
    ctx: str = "inline"  # inline, fence, link, tree, heading, prose
    extra: dict = field(default_factory=dict)
    status: str = "unchecked"  # ok, broken, stale, external, skipped, unchecked
    where: str = ""     # where it was found (path or path:line) when ok


@dataclass
class Finding:
    rule: str
    severity: str
    path: str           # file the finding points at (a doc, or code for rule violations)
    line: int
    col: int
    message: str
    claim: str = ""
    evidence: list = field(default_factory=list)  # [{"kind": "git"|"code"|"doc", ...}]
    suggestion: str = ""
    fingerprint: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def fingerprint(rule: str, path: str, claim: str, line_text: str) -> str:
    """Stable id for baselines: survives the line moving up or down."""
    norm = re.sub(r"\s+", " ", line_text).strip()
    raw = f"{rule}\x00{path}\x00{claim}\x00{norm}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# Messages: rule -> (english, vietnamese). Fields are filled with str.format.
MESSAGES = {
    "path-moved": (
        "`{claim}` no longer exists; it did when this line was written ({when})",
        "`{claim}` không còn; lúc viết dòng này ({when}) nó vẫn có",
    ),
    "path-removed-now": (
        "`{claim}` was removed in the working tree (still in HEAD)",
        "`{claim}` vừa bị xóa trong cây làm việc (HEAD vẫn có)",
    ),
    "path-missing": (
        "`{claim}` does not exist (and did not when this line was written)",
        "`{claim}` không tồn tại (lúc viết dòng này cũng chưa có)",
    ),
    "link-broken": (
        "link target `{claim}` does not exist",
        "link trỏ tới `{claim}` không tồn tại",
    ),
    "link-unverified": (
        "site addresses with no page in the repo ({count}): {sample}; if the site makes these pages itself, nothing is wrong",
        "địa chỉ site không có trang nào trong repo ({count}): {sample}; nếu site tự sinh các trang này thì không sao",
    ),
    "link-case": (
        "link target `{claim}` is spelled `{real}` in the repo: it opens on Windows and macOS, and breaks on GitHub and Linux",
        "link trỏ tới `{claim}` nhưng trong repo tên là `{real}`: trên Windows và macOS vẫn mở được, lên GitHub và Linux thì hỏng",
    ),
    "anchor-unverified": (
        "no heading `#{anchor}` in `{target}`; an id that only the built site has (from a component, a plugin, data) would explain it",
        "`{target}` không có mục `#{anchor}`; có thể đây là id chỉ có trên site đã dựng (do component, plugin hoặc dữ liệu sinh ra)",
    ),
    "anchor-missing": (
        "no heading `#{anchor}` in `{target}`",
        "`{target}` không có mục `#{anchor}`",
    ),
    "command-missing": (
        "command refers to `{claim}`, which does not exist",
        "lệnh gọi `{claim}`, thứ này không tồn tại",
    ),
    "npm-script-missing": (
        "`{claim}`: no script `{name}` in {manifest}",
        "`{claim}`: {manifest} không có script `{name}`",
    ),
    "make-target-missing": (
        "`{claim}`: no target `{name}` in {manifest}",
        "`{claim}`: {manifest} không có target `{name}`",
    ),
    "flag-removed": (
        "`{flag}` was removed from `{script}` after this line was written ({when})",
        "`{script}` đã bỏ cờ `{flag}` sau khi dòng này được viết ({when})",
    ),
    "flag-missing": (
        "`{script}` has no option `{flag}`",
        "`{script}` không có cờ `{flag}`",
    ),
    "subcommand-missing": (
        "`{script}` has no subcommand `{name}`",
        "`{script}` không có lệnh con `{name}`",
    ),
    "symbol-gone": (
        "`{claim}` is gone from the code; it existed when this line was written ({when})",
        "`{claim}` không còn trong code; lúc viết dòng này ({when}) nó vẫn có",
    ),
    "symbol-removed-now": (
        "`{claim}` was just removed from the code (still in HEAD)",
        "`{claim}` vừa bị xóa khỏi code (HEAD vẫn có)",
    ),
    "decision-unknown": (
        "decision {claim} is not in {log}",
        "quyết định {claim} không có trong {log}",
    ),
    "decision-superseded": (
        "decision {claim} was replaced by {by}; check this line still holds",
        "quyết định {claim} đã bị thay bởi {by}; xem dòng này còn đúng không",
    ),
    "decision-amended": (
        "decision {claim} was partly replaced by {by}",
        "quyết định {claim} đã bị thay một phần bởi {by}",
    ),
    "version-mismatch": (
        "doc says version {claim}, {manifest} says {actual}",
        "tài liệu ghi phiên bản {claim}, {manifest} ghi {actual}",
    ),
    "dep-mismatch": (
        "doc says `{claim}`, {manifest} has `{actual}`",
        "tài liệu ghi `{claim}`, {manifest} ghi `{actual}`",
    ),
    "copies-diverged": (
        "the same sentence in {other} has different numbers ({mine} here, {theirs} there); this copy is older",
        "câu này cũng có ở {other} nhưng khác số ({mine} ở đây, {theirs} ở kia); bản này cũ hơn",
    ),
    "rule-violation": (
        "breaks the rule in {doc}: \"{rule_text}\"",
        "phạm luật ghi ở {doc}: \"{rule_text}\"",
    ),
    "rule-invalid": (
        "cannot read this mindmap rule: {error}",
        "không đọc được luật mindmap này: {error}",
    ),
    "table-shape": (
        "{bad} of {rows} table rows have {cells} cells instead of {header}",
        "{bad}/{rows} dòng của bảng có {cells} ô thay vì {header}",
    ),
    "stale-risk": (
        "code this doc describes changed after the doc: {files}",
        "code mà tài liệu này mô tả đã đổi sau lần sửa tài liệu cuối: {files}",
    ),
    "path-gone": (
        "`{claim}` is no longer in the repo",
        "`{claim}` không còn trong repo",
    ),
    "path-typo": (
        "`{claim}` does not exist; did you mean `{near}`?",
        "`{claim}` không tồn tại; có phải ý là `{near}`?",
    ),
    "table-orphan": (
        "{rows} lines from here start with `|` but are not part of a table (the table above ends at line {end}); they show as plain text",
        "{rows} dòng từ đây bắt đầu bằng `|` nhưng không thuộc bảng nào (bảng phía trên dừng ở dòng {end}); chúng hiện ra như chữ thường",
    ),
    "foreign-links": (
        "{broken} of {total} relative links here point to files this repo never had; the doc looks copied from another project",
        "{broken}/{total} link tương đối ở đây trỏ tới file repo này chưa từng có; tài liệu có vẻ chép từ dự án khác",
    ),
}


def message(rule: str, lang: str, **kw) -> str:
    en, vi = MESSAGES[rule]
    template = vi if lang == "vi" else en
    try:
        return template.format(**kw)
    except (KeyError, IndexError):
        return template


NOTES_VI = {
    "committed, removed in the working tree": "đã commit, đang bị xóa ở bản làm việc",
    "existed when the line was written": "còn có lúc viết dòng này",
    "last seen here": "thấy lần cuối ở đây",
    "deleted": "bị xóa",
    "renamed": "đổi tên",
    "(blank line)": "(dòng trống)",
}
NOTE_FORMS_VI = (
    (re.compile(r"^(`[^`]+`) was a subcommand when the line was written$"), r"\1 là lệnh con lúc viết dòng này"),
    (re.compile(r"^(`[^`]+`) was here$"), r"\1 từng ở đây"),
    (re.compile(r"^(`[^`]+`) was used here$"), r"\1 từng được dùng ở đây"),
    (re.compile(r"^removed by this commit: (.*)$", re.S), r"bị bỏ ở commit này: \1"),
    (re.compile(r"^the heading (`.+?`) was removed by this commit: (.*)$", re.S), r"mục \1 bị bỏ ở commit này: \2"),
)


def evidence_text(text: str, lang: str) -> str:
    """Evidence notes are written in English; translate the fixed ones."""
    if lang != "vi" or not text:
        return text
    if text in NOTES_VI:
        return NOTES_VI[text]
    for rx, repl in NOTE_FORMS_VI:
        if rx.match(text):
            return rx.sub(repl, text)
    return text
