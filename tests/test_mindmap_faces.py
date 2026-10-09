"""Mind Map faces: MCP server, Claude Code hook, impact, cost, context, reports, CLI."""

import io
import json
import os
import subprocess
import sys
import time

import pytest

from mindmap_fixture import HERE, Repo, run

pytest.importorskip("mindmap")      # a copy of this repo may carry the tests before the package


@pytest.fixture
def repo():
    r = Repo()
    r.write("src/app.py", "def build_index():\n    return 1\n\n\ndef keep():\n    return 2\n")
    r.write("AGENTS.md", "# Agents\n\nCall `build_index()` before `keep()`.\nSee [guide](docs/guide.md).\n")
    r.write("docs/guide.md", "# Guide\n\n## Setup\n\nInstall the tool, then index the files.\n")
    r.commit("start")
    yield r
    r.cleanup()


# -- MCP ----------------------------------------------------------------------------

def call(server, method, params=None, id=1):
    from mindmap.mcp import _process
    msg = {"jsonrpc": "2.0", "id": id, "method": method}
    if params is not None:
        msg["params"] = params
    return _process(server, msg)


def test_mcp_legacy_handshake_and_tools(repo):
    from mindmap.mcp import Server
    s = Server(repo.root)
    init = call(s, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})["result"]
    assert init["protocolVersion"] == "2025-06-18" and init["serverInfo"]["name"] == "meinya-mind-map"
    tools = call(s, "tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == {"check", "impact", "claims", "context", "cost"}
    assert all(t["annotations"]["readOnlyHint"] for t in tools)
    res = call(s, "tools/call", {"name": "check", "arguments": {"path": "AGENTS.md"}})["result"]
    assert res["isError"] is False and res["structuredContent"]["stats"]["docs"] == 1


def test_mcp_unknown_client_version_gets_a_supported_one(repo):
    from mindmap.mcp import LEGACY, Server
    init = call(Server(repo.root), "initialize", {"protocolVersion": "2099-01-01"})["result"]
    assert init["protocolVersion"] == LEGACY[0]


def test_mcp_modern_discover_and_version_errors(repo):
    from mindmap.mcp import META_SERVER, META_VERSION, Server
    s = Server(repo.root)
    d = call(s, "server/discover", {})["result"]
    assert d["resultType"] == "complete" and "2026-07-28" in d["supportedVersions"]
    assert d["_meta"][META_SERVER]["name"] == "meinya-mind-map"
    ok = call(s, "tools/list", {"_meta": {META_VERSION: "2026-07-28"}})["result"]
    assert ok["resultType"] == "complete" and ok["ttlMs"] > 0
    bad = call(s, "tools/list", {"_meta": {META_VERSION: "1999-01-01"}})["error"]
    assert bad["code"] == -32022 and bad["data"]["requested"] == "1999-01-01"


def test_mcp_errors_and_notifications(repo):
    from mindmap.mcp import Server, _process
    s = Server(repo.root)
    assert call(s, "nope")["error"]["code"] == -32601
    assert _process(s, {"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    assert _process(s, {"id": 1, "method": "ping"})["error"]["code"] == -32600
    out = call(s, "tools/call", {"name": "check", "arguments": {"path": "../outside.md"}})["result"]
    assert out["isError"] is True
    assert call(s, "prompts/get", {"name": "nope"})["error"]["code"] == -32602
    p = call(s, "prompts/get", {"name": "critic"})["result"]
    assert p["messages"][0]["content"]["text"]


def test_mcp_stdio_loop(repo):
    lines = [
        {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        [{"jsonrpc": "2.0", "id": 2, "method": "ping"}, {"jsonrpc": "2.0", "id": 3, "method": "prompts/list"}],
    ]
    stdin = "\n".join(json.dumps(x) for x in lines) + "\nnot json\n"
    out = subprocess.run([sys.executable, "-X", "utf8", "-m", "mindmap", "mcp", "--root", str(repo.root)],
                         input=stdin.encode(), capture_output=True, cwd=HERE.parent, timeout=120)
    replies = [json.loads(x) for x in out.stdout.decode().splitlines() if x.strip()]
    assert replies[0]["result"]["protocolVersion"] == "2025-11-25"
    assert sorted(r["id"] for r in replies[1]) == [2, 3]
    assert replies[2]["error"]["code"] == -32700


# -- hook ---------------------------------------------------------------------------

def test_hook_code_edit_points_at_stale_doc_lines(repo):
    from mindmap.hook import post_tool
    repo.write("src/app.py", "def make_index():\n    return 1\n\n\ndef keep():\n    return 2\n")
    text = post_tool(repo.root, {"tool_name": "Edit", "tool_input": {"file_path": str(repo.root / "src/app.py")}})
    assert "AGENTS.md:3" in text and "build_index" in text


def test_hook_doc_edit_reports_that_doc(repo):
    from mindmap.hook import post_tool
    repo.write("AGENTS.md", "# Agents\n\nSee [missing](docs/missing.md).\n")
    text = post_tool(repo.root, {"tool_name": "Write", "tool_input": {"file_path": "AGENTS.md"}})
    assert "AGENTS.md:3" in text and "not a verdict" in text       # the agent reads the line before editing


def test_mcp_check_asks_the_agent_to_read_the_line_in_context(repo):
    from mindmap.mcp import Server
    s = Server(repo.root)
    call(s, "initialize", {"protocolVersion": "2025-06-18", "capabilities": {}})
    assert "not a verdict" not in call(s, "tools/call", {"name": "check", "arguments": {}})["result"]["content"][0]["text"]
    repo.write("AGENTS.md", "# Agents\n\nSee [missing](docs/missing.md).\n")
    text = call(s, "tools/call", {"name": "check", "arguments": {}})["result"]["content"][0]["text"]
    assert "AGENTS.md:3" in text and "not a verdict" in text


def test_hook_session_start_and_quiet_cases(repo):
    from mindmap.hook import post_tool, session_start
    assert session_start(repo.root) == ""                     # instruction files are clean
    repo.write("src/app.py", "def keep():\n    return 2\n").commit("drop build_index")
    assert "AGENTS.md:3" in session_start(repo.root) and "not a verdict" in session_start(repo.root)
    assert post_tool(repo.root, {"tool_name": "Read", "tool_input": {"file_path": "AGENTS.md"}}) == ""
    assert post_tool(repo.root, {"tool_name": "Edit", "tool_input": {"file_path": "C:/elsewhere/x.py"}}) == ""


def test_hook_main_never_fails(repo, monkeypatch, capsys):
    from mindmap import hook
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    for raw in (b"not json", b"[1, 2]", b""):
        monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(raw)))
        assert hook.main("auto", str(repo.root)) == 0
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Write", "cwd": str(repo.root),
               "tool_input": {"file_path": "AGENTS.md"}}
    repo.write("AGENTS.md", "# Agents\n\nSee [missing](docs/missing.md).\n")
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    capsys.readouterr()
    assert hook.main("auto", None) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
    assert "AGENTS.md:3" in out["hookSpecificOutput"]["additionalContext"]


def _hook_out(hook, monkeypatch, capsys, payload) -> str:
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps(payload).encode())))
    capsys.readouterr()
    assert hook.main("auto", None) == 0
    out = capsys.readouterr().out
    return json.loads(out)["hookSpecificOutput"]["additionalContext"] if out else ""


def test_hook_root_is_the_project_dir_not_the_folder_the_agent_cd_into(repo, monkeypatch, capsys):
    from mindmap import hook
    repo.write("AGENTS.md", "# Agents\n\nSee [missing](docs/missing.md).\n")
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": str(repo.root / "src"),
               "tool_input": {"file_path": str(repo.root / "AGENTS.md")}}
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    assert _hook_out(hook, monkeypatch, capsys, payload) == ""           # the doc is outside `src/`
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo.root))
    assert "AGENTS.md:3" in _hook_out(hook, monkeypatch, capsys, payload)


def test_hook_says_so_when_it_cannot_check(repo, monkeypatch, capsys):
    from mindmap import hook

    def broken(root, data):
        raise RuntimeError("git is gone")
    monkeypatch.setattr(hook, "post_tool", broken)
    payload = {"hook_event_name": "PostToolUse", "tool_name": "Edit", "cwd": str(repo.root),
               "tool_input": {"file_path": "AGENTS.md"}}
    text = _hook_out(hook, monkeypatch, capsys, payload)
    assert "could not check" in text and "git is gone" in text


# -- impact, cost, context -------------------------------------------------------------

def test_impact_finds_doc_lines_for_removed_names(repo):
    from mindmap.impact import impact
    repo.write("src/app.py", "def keep():\n    return 2\n")
    hits = impact(repo.root)
    assert [(h.doc, h.line, h.term) for h in hits] == [("AGENTS.md", 3, "build_index")]


def test_impact_ignores_names_still_defined_elsewhere(repo):
    from mindmap.impact import impact
    repo.write("src/app.py", "def keep():\n    return 2\n")
    repo.write("src/other.py", "def build_index():\n    return 3\n")
    assert impact(repo.root) == []


def test_impact_skips_docs_marked_history_in_the_doc_or_the_config(repo):
    from mindmap.impact import impact
    repo.write(".mindmap.toml", 'history = ["notes/**"]\n')
    repo.write("PROMPT_SENT.md", "<!-- mindmap: history -->\n# Old prompt\n\nCall `build_index()` first.\n")
    repo.write("notes/old.md", "# Old\n\nCall `build_index()` first.\n").commit("notes")
    repo.write("src/app.py", "def keep():\n    return 2\n")
    assert [h.doc for h in impact(repo.root)] == ["AGENTS.md"]


def test_cost_counts_tokens_and_stale_lines(repo):
    from mindmap.cost import estimate_tokens, measure
    assert estimate_tokens("abcd" * 10) == 10
    repo.write("src/app.py", "def keep():\n    return 2\n").commit("drop")
    [row] = measure(repo.root)
    assert row["file"] == "AGENTS.md" and row["loaded"] == "every session"
    assert row["tokens"] > 0 and row["stale_lines"] == [3]


def test_context_picks_the_relevant_section(repo):
    from mindmap.context import build
    pack = build(repo.root, "install setup", budget=200)
    assert pack["sections"] and pack["sections"][0]["doc"] == "docs/guide.md"
    assert "Install the tool" in pack["text"] and pack["tokens"] <= 200


def test_context_marks_stale_lines(repo):
    from mindmap.context import build
    repo.write("src/app.py", "def keep():\n    return 2\n").commit("drop")
    pack = build(repo.root, "agents build_index", budget=400)
    assert "[stale]" in pack["text"]


def test_context_shows_a_section_that_two_copies_share_once(repo):
    from mindmap.context import build
    repo.write("public/guide.md", "# Guide\n\n## Setup\n\nInstall the tool, then index the files.\n").commit("copy")
    pack = build(repo.root, "install setup", budget=400)
    setups = [s for s in pack["sections"] if s["title"] == "Setup"]
    assert len(setups) == 1 and pack["text"].count("Install the tool") == 1


def test_mcp_context_puts_the_text_in_the_structured_result(repo):
    from mindmap.mcp import Server
    res = call(Server(repo.root), "tools/call", {"name": "context", "arguments": {"query": "install setup"}})["result"]
    assert "Install the tool" in res["structuredContent"]["text"]


# -- reports and CLI --------------------------------------------------------------------

def test_html_report_is_self_contained_and_escapes_doc_text(repo):
    from mindmap import htmlreport, report
    repo.write("docs/evil.md", "# x</script><script>alert(1)</script>\n\nSee [a](missing.md).\n").commit()
    res = run(repo)
    page = htmlreport.html(res, report.filter_findings(res.findings, "info"), "vi")
    assert "<script>alert(1)" not in page
    assert "http://" not in page.replace("http://www.w3.org", "") and "https://" not in page
    md = htmlreport.markdown(res, report.filter_findings(res.findings, "warning"), "en")
    assert "docs/evil.md" in md and "link-broken" in md


def cli(repo, *args):
    return subprocess.run([sys.executable, "-X", "utf8", "-m", "mindmap", *args], capture_output=True,
                          cwd=HERE.parent, timeout=180)


def test_cli_exit_codes_and_formats(repo):
    assert cli(repo, "check", str(repo.root)).returncode == 0
    repo.write("README.md", "# A\n\nSee [a](missing.md).\n").commit()
    assert cli(repo, "check", str(repo.root)).returncode == 1
    assert cli(repo, "check", str(repo.root), "--fail-on", "never").returncode == 0
    out = cli(repo, "check", str(repo.root), "-f", "json", "--fail-on", "never")
    data = json.loads(out.stdout.decode())
    assert data["findings"][0]["rule"] == "link-broken"
    sarif = json.loads(cli(repo, "check", str(repo.root), "-f", "sarif", "--fail-on", "never").stdout.decode())
    assert sarif["runs"][0]["results"][0]["ruleId"] == "link-broken"
    gh = cli(repo, "check", str(repo.root), "-f", "github", "--fail-on", "never").stdout.decode()
    assert gh.startswith("::error file=README.md,line=3")


def test_piped_output_survives_accents_where_the_console_is_not_utf8(repo):
    # redirected output on Windows defaults to the ANSI code page: an accented path used to stop the run
    repo.write("tài liệu/hướng dẫn.md", "# Hướng dẫn\n\nSee [a](thiếu.md).\n").commit()
    env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
    for args in (["check", str(repo.root), "--fail-on", "never"],
                 ["check", str(repo.root), "-f", "json", "--fail-on", "never"],
                 ["check", str(repo.root), "--baseline", "tài liệu/sổ.json", "--update-baseline"]):
        out = subprocess.run([sys.executable, "-m", "mindmap", *args], capture_output=True, cwd=HERE.parent,
                             env=env, timeout=180)
        assert out.returncode == 0, out.stderr.decode("utf-8", "replace")
        assert "tài liệu" in out.stdout.decode("utf-8"), args
    # the user chose an encoding that cannot hold the name: it is kept, the character is replaced
    out = subprocess.run([sys.executable, "-m", "mindmap", "check", str(repo.root), "--fail-on", "never"],
                         capture_output=True, cwd=HERE.parent, env=dict(env, PYTHONIOENCODING="ascii"), timeout=180)
    assert out.returncode == 0 and b"h??ng d?n.md" in out.stdout


def test_messages_and_summary_share_the_language_of_the_config(repo):
    repo.write(".mindmap.toml", 'lang = "vi"\n')
    repo.write("README.md", "# A\n\nSee [a](missing.md).\n").commit()
    out = cli(repo, "check", str(repo.root), "--fail-on", "never").stdout.decode()
    assert "không tồn tại" in out and "1 lỗi" in out
    out = cli(repo, "check", str(repo.root), "--fail-on", "never", "--lang", "en").stdout.decode()
    assert "does not exist" in out and "1 error" in out


@pytest.mark.skipif(sys.version_info < (3, 12), reason="reads the f-string tokens Python 3.12 added")
def test_sources_stay_readable_by_python_3_11():
    # The tool promises Python 3.11 and is written on a newer one. Before 3.12 an f-string could not reuse
    # its own quote, hold a backslash or (on one line) a line break inside `{...}`: a SyntaxError at import.
    import ast
    import tokenize
    top = HERE.parent
    bad = []
    for path in sorted([*top.glob("*.py"), *top.glob("mindmap/*.py"), *top.glob("mdhtml/*.py")]):
        ast.parse(path.read_text(encoding="utf-8"), feature_version=(3, 11))
        open_quotes = []                # quotes of the f-strings we are inside, outermost first
        with tokenize.open(path) as fh:
            for tok in tokenize.generate_tokens(fh.readline):
                where = f"{path.name}:{tok.start[0]}"
                if tok.type == tokenize.FSTRING_END:
                    open_quotes.pop()
                elif tok.type == tokenize.FSTRING_MIDDLE:
                    if len(open_quotes) > 1 and "\\" in tok.string:
                        bad.append(where + " backslash")
                elif open_quotes:       # inside `{...}`
                    quote = tok.string.lstrip("rRbBuUfF") if tok.type in (tokenize.STRING, tokenize.FSTRING_START) else ""
                    if quote.startswith(open_quotes[-1]):
                        bad.append(where + " same quote")
                    if "\\" in tok.string:
                        bad.append(where + " backslash")
                    if tok.type in (tokenize.NL, tokenize.COMMENT) and len(open_quotes[-1]) == 1:
                        bad.append(where + " line break")
                if tok.type == tokenize.FSTRING_START:
                    open_quotes.append(tok.string.lstrip("rRbBuUfF"))
    assert bad == []


def test_the_checked_folder_cannot_shadow_python_modules(repo):
    # Mind Map only reads the folder it checks: a `json.py` planted there must never run
    repo.write("json.py", 'raise SystemExit("TRAP")\n').commit()
    env = dict(os.environ, PYTHONPATH=str(HERE.parent))
    for cmd in ([sys.executable, "-X", "utf8", "-m", "mindmap", "check", "."],
                [sys.executable, "-I", "-X", "utf8", str(HERE.parent / "run_mindmap.py"), "check", "."]):
        out = subprocess.run(cmd, capture_output=True, cwd=repo.root, env=env, timeout=180)
        assert b"TRAP" not in out.stdout + out.stderr and out.returncode == 0, cmd


# -- a git that does not answer -------------------------------------------------------------

@pytest.fixture
def patient():
    """The git wrapper with a short wait after a stop, and a clean count before and after."""
    from mindmap import files
    grace = files.GIT_GRACE
    files.GIT_GRACE = 0.5
    files.git_trouble(reset=True)
    yield files
    files.GIT_GRACE = grace
    files.git_trouble(reset=True)


NAP = ["-c", "alias.nap=!sleep 20", "nap"]      # git starts a shell and the shell sleeps: processes below the one we started


def test_the_time_limit_of_a_git_call_is_a_real_one(repo, patient):
    # Python's own `run` kills the first process and then waits for the others: 20 seconds here, 22 minutes once
    t = time.perf_counter()
    assert patient.run_git(NAP, repo.root, timeout=1) is None
    assert time.perf_counter() - t < 12
    assert patient.git_trouble() == {"late": 1, "skipped": 0}


def test_a_git_that_keeps_hanging_is_not_asked_again(repo, patient):
    for _ in range(patient.GIT_PATIENCE):
        assert patient.run_git(NAP, repo.root, timeout=0.3) is None
    assert patient.run_git(["rev-parse", "HEAD"], repo.root) is None        # not asked: git is stuck, not slow
    assert patient.git_trouble() == {"late": patient.GIT_PATIENCE, "skipped": 1}
    patient.git_trouble(reset=True)                                         # the next run starts fresh
    assert patient.run_git(["rev-parse", "HEAD"], repo.root)


def test_a_report_made_while_git_hung_says_that_it_is_incomplete(repo, patient, monkeypatch, capsys):
    from mindmap import cli as mindmap_cli, engine, report
    from mindmap.mcp import Server

    class Stuck(subprocess.Popen):
        def communicate(self, input=None, timeout=None):
            if self.args[0] == "git" and timeout not in (None, patient.GIT_GRACE):
                raise subprocess.TimeoutExpired(self.args, timeout)
            return super().communicate(input, timeout)

    assert engine.run(repo.root).stats["git_unanswered"] == 0
    monkeypatch.setattr(subprocess, "Popen", Stuck)
    res = engine.run(repo.root)
    assert res.stats["git_unanswered"] >= 1 and not res.stats["git"]      # the first question already got no answer
    assert "git gave no answer in time" in report.text(res, res.findings, color=False)
    assert "git không trả lời kịp" in report.text(res, res.findings, "vi", color=False)
    assert mindmap_cli.main(["check", str(repo.root), "--format", "json", "--fail-on", "never"]) == 0
    assert "git gave no answer in time" in capsys.readouterr().err
    said = call(Server(repo.root), "tools/call", {"name": "check", "arguments": {}})["result"]
    assert "git gave no answer in time" in said["content"][0]["text"] and said["structuredContent"]["stats"]["git_unanswered"]
    monkeypatch.undo()
    assert engine.run(repo.root).stats["git_unanswered"] == 0               # one bad run does not mark the next


def test_git_never_reads_the_input_of_the_tool(repo, patient):
    # the MCP server speaks its protocol on stdin: a git that read there would eat a message, or wait for one
    empty = b"e69de29bb2d1d6434b8b29ae775ad8c2e48c5391"
    assert (patient.run_git(["hash-object", "--stdin"], repo.root, timeout=20) or b"").strip() == empty


def test_the_command_line_reports_guesses_as_notes_unless_all(repo, capsys):
    # `build_index()` gone from the code is a reading of the text (a guess); a link to a page that never was is a
    # fact. People and CI get the facts; --all, agents (MCP, hook) and the app get both
    from mindmap import cli as mindmap_cli
    from mindmap.mcp import Server
    repo.write("src/app.py", "def keep():\n    return 2\n")
    repo.write("AGENTS.md", "# Agents\n\nCall `build_index()` before `keep()`.\nSee [guide](docs/guide.md), [setup](docs/setup.md).\n")
    repo.commit("drop build_index")

    def found(*args):
        assert mindmap_cli.main(["check", str(repo.root), "--format", "json", "--severity", "info",
                                 "--fail-on", "never", *args]) == 0
        return {f["rule"]: f["severity"] for f in json.loads(capsys.readouterr().out)["findings"]}

    sure = found()
    assert sure["symbol-gone"] == "info" and sure["link-broken"] in ("error", "warning")
    assert found("--all")["symbol-gone"] == "warning"
    assert mindmap_cli.main(["check", str(repo.root), "--fail-on", "warning"]) == 1      # the link still fails CI
    assert "1 guess shown as info (--all)" in capsys.readouterr().out
    said = call(Server(repo.root), "tools/call", {"name": "check", "arguments": {}})["result"]["structuredContent"]
    assert {f["rule"]: f["severity"] for f in said["findings"]}["symbol-gone"] == "warning"
