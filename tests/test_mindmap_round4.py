"""Round 4 contracts: repository-independent paths and small AI-assisted repos."""
import pytest

from mindmap_fixture import Repo, run
from mindmap.gitinfo import defines
from mindmap.hook import post_tool, session_start
from mindmap.mdscan import scan


@pytest.fixture
def repo():
    repository = Repo(git=False)
    yield repository
    repository.cleanup()


def serious(repository):
    return [finding for finding in run(repository).findings if finding.severity in ("warning", "error")]


def reported(repository):
    """Serious findings plus every path-missing: it is a warning only in an agent's instruction file."""
    return [finding for finding in run(repository).findings
            if finding.severity in ("warning", "error") or finding.rule == "path-missing"]


@pytest.mark.parametrize("doc,severity", [("README.md", "info"), ("AGENTS.md", "warning"), ("sub/CLAUDE.md", "warning")])
@pytest.mark.parametrize("with_git", [False, True])
def test_missing_path_without_history(with_git, doc, severity):
    repository = Repo(git=with_git)
    try:
        repository.write("src/notes/cli.py", "value = 1\n")
        repository.write(doc, "# App\n\nSee `src/notes/old_cli.py`.\n")
        if with_git:
            repository.commit()
        findings = reported(repository)
        assert [(finding.rule, finding.severity) for finding in findings] == [("path-missing", severity)]
    finally:
        repository.cleanup()


@pytest.mark.parametrize("claim", ["config/app.yaml", "dist/app.js", "build/app.js", "out/app.js", "target/app.js", "node_modules/app/index.js", ".venv/lib/app.py", "venv/lib/app.py", "coverage/app.json", ".next/app.js", "__pycache__/app.py", "/src/notes/missing.py", "C:/src/notes/missing.py", "~/src/notes/missing.py", "src/notes/*.py", "src/notes/?.py", "src/notes/[a].py", "src/notes/<name>.py", "src/notes/{name}.py", "src/notes/$FILE.py", "src/notes/%FILE%.py", "src/notes/your-file.py", "src/notes/my-file.py", "src/notes/example.py", "src/notes/foo.py", "src/notes/xxx.py"])
def test_missing_path_safety_exclusions(repo, claim):
    repo.write("src/notes/cli.py", "value = 1\n")
    repo.write("dist/keep.txt", "build output\n")
    repo.write("README.md", f"# App\n\nSee `{claim}`.\n")
    assert not reported(repo)


@pytest.mark.parametrize("prefix", ["Create", "Add", "Generate", "Will create", "Should create", "Tạo", "Thêm", "Sinh ra", "Sẽ tạo"])
def test_creation_instruction_is_not_missing(repo, prefix):
    repo.write("src/notes/cli.py", "value = 1\n")
    repo.write("README.md", f"# App\n\n{prefix} `src/notes/new.py`.\n")
    assert not reported(repo)


def test_creation_after_existing_claim_remains_scoped(repo):
    repo.write("src/notes/cli.py", "value = 1\n")
    repo.write("README.md", "# App\n\nUse `src/notes/missing_entry.py`, then create `src/notes/new.py`.\n")
    assert [finding.claim for finding in reported(repo)] == ["src/notes/missing_entry.py"]


@pytest.mark.parametrize("literal", ['"out.json"', "'src/notes/out.json'"])
def test_generated_source_literal_is_not_missing(repo, literal):
    repo.write("src/notes/cli.py", f"output = {literal}\n")
    repo.write("README.md", "# App\n\nRead `src/notes/out.json`.\n")
    assert not reported(repo)


def test_no_git_ignore_and_negation(repo):
    repo.write("src/notes/cli.py", "value = 1\n")
    repo.write(".gitignore", "src/notes/*.json\n!src/notes/required.json\n")
    repo.write("README.md", "# App\n\nRead `src/notes/out.json` and `src/notes/required.json`.\n")
    assert [(finding.rule, finding.claim) for finding in reported(repo)] == [("path-missing", "src/notes/required.json")]


def test_missing_path_doc_relative_directory(repo):
    repo.write("docs/src/notes/cli.py", "value = 1\n")
    repo.write("docs/guide.md", "# App\n\nSee `src/notes/missing_entry.py`.\n")
    assert [finding.rule for finding in reported(repo)] == ["path-missing"]


def test_missing_path_vietnamese(repo):
    repo.write("src/notes/cli.py", "value = 1\n")
    repo.write("README.md", "# App\n\nXem `src/notes/missing_entry.py`.\n")
    findings = run(repo, lang="vi").findings
    assert len(findings) == 1 and "không tồn tại" in findings[0].message


@pytest.mark.parametrize("status", ["Done", "Implemented", "Completed", "Shipped", "Superseded", "Obsolete", "Deprecated", "Archived", "Rejected", "Withdrawn", "Accepted"])
@pytest.mark.parametrize("form", ["Status: {status}", "**Status:** {status}", "Status — {status}", "---\nstatus: {status}\n---"])
def test_terminal_document_status(repo, status, form):
    repo.write("src/cli.py", "value = 1\n")
    repo.write("guide.md", form.format(status=status) + "\n\nSee `src/missing_entry.py`.\n")
    result = run(repo)
    assert result.doc_stats["guide.md"]["type"] == "history"
    assert not reported(repo)


@pytest.mark.parametrize("status", ["Draft", "Proposed", "Planned", "In progress", "WIP", "Approved", "Approved, not yet implemented"])
def test_planned_document_status(repo, status):
    repo.write("src/cli.py", "value = 1\n")
    repo.write("guide.md", f"# Guide\n\nStatus: {status}\n\nSee `src/missing_entry.py`.\n")
    assert run(repo).doc_stats["guide.md"]["type"] == "plan"
    assert not reported(repo)


@pytest.mark.parametrize("override", ["directive", "config"])
def test_status_does_not_override_explicit_live(repo, override):
    repo.write("src/cli.py", "value = 1\n")
    document = "Status: Done\n\nSee `src/missing_entry.py`.\n"
    if override == "directive":
        document = "<!-- mindmap: live -->\n" + document
    else:
        repo.write(".mindmap.toml", 'live = ["guide.md"]\n')
    repo.write("guide.md", document)
    assert run(repo).doc_stats["guide.md"]["type"] == "live"
    assert [finding.rule for finding in reported(repo)] == ["path-missing"]


def test_late_status_is_not_document_status(repo):
    repo.write("guide.md", "# Guide\n" + "\n" * 22 + "Status: Done\n")
    assert run(repo).doc_stats["guide.md"]["type"] == "live"


def test_dated_spec_not_blog(repo):
    repo.write("docs/specs/2026-06-26-design.md", "# Design\n")
    repo.write("blog/2026-06-26-entry.md", "# Release\n")
    result = run(repo)
    assert result.doc_stats["docs/specs/2026-06-26-design.md"]["type"] == "plan"
    assert result.doc_stats["blog/2026-06-26-entry.md"]["type"] == "live"


@pytest.mark.parametrize("directory", ["done", "completed", "complete", "implemented", "shipped", "superseded", "obsolete", "finished"])
def test_completed_directory_is_history(repo, directory):
    path = f"specs/{directory}/feature.md"
    repo.write(path, "# Feature\n")
    assert run(repo).doc_stats[path]["type"] == "history"


@pytest.mark.parametrize("suffix", ["", ' "Title"', " 'Title'", " (Title)"])
def test_reference_definition_valid_titles(suffix):
    document = scan("README.md", f"# Guide\n\n[label]: missing.md{suffix}\n\n[read][label]\n")
    assert [link.dest for link in document.links] == ["missing.md"]


@pytest.mark.parametrize("text", ["Paragraph\n[label]: missing.md\n\n[read][label]\n", '[label]: missing.md is prose\n\n[read][label]\n', '[measured on a fresh profile]: `gtm.js` is minified\n'])
def test_reference_definition_does_not_parse_prose(text):
    assert not scan("README.md", text).links


def test_consecutive_reference_definitions_are_valid():
    document = scan("README.md", '[one]: first.md\n[two]: second.md "Title"\n\n[one] [two]\n')
    assert {link.dest for link in document.links} == {"first.md", "second.md"}


@pytest.mark.parametrize("command", ["git clone https://github.com/org/widgets.git\ncd widgets", "git clone https://github.com/org/upstream.git widgets\ncd widgets", "$ git clone https://github.com/org/widgets.git\n$ cd widgets"])
def test_clone_created_directory_is_not_repo_path(repo, command):
    repo.write("widget/keep.py", "value = 1\n")
    repo.write("README.md", f"# Install\n\n```sh\n{command}\n```\n")
    assert not serious(repo)
    document = scan("README.md", repo.root.joinpath("README.md").read_text(encoding="utf-8"))
    assert not any(text.lstrip().startswith("cd ") for fence in document.fences for _, text in fence.lines)


def test_clone_state_does_not_leak_to_another_fence(repo):
    repo.write("widget/keep.py", "value = 1\n")
    repo.write("README.md", "# Install\n\n```sh\ngit clone https://github.com/org/widgets.git\n```\n\n```sh\ncd widgets\n```\n")
    document = scan("README.md", repo.root.joinpath("README.md").read_text(encoding="utf-8"))
    assert document.fences[-1].lines == [(8, "cd widgets")]


@pytest.mark.parametrize("route", ["issues", "pulls", "pull", "wiki", "discussions", "releases", "actions", "security", "compare", "tags", "milestones", "projects", "commits", "blob", "tree"])
def test_github_relative_root_escape_is_web(repo, route):
    repo.write("FOR_AGENTS.md", f"# Agents\n\n[route](../../{route}/42)\n")
    assert not serious(repo)


def test_non_github_root_escape_keeps_existing_boundary_policy(repo):
    repo.write("README.md", "# Agents\n\n[missing](../../unknown/file.md)\n")
    assert not serious(repo)


def test_in_repo_issues_directory_is_not_web_route(repo):
    repo.write("docs/guide.md", "# Guide\n\n[missing](../issues/missing.md)\n")
    assert [finding.rule for finding in serious(repo)] == ["link-broken"]


@pytest.mark.parametrize("directory", ["template", "templates", "scaffold", "boilerplate"])
def test_templates_do_not_check_decision_placeholders(repo, directory):
    repo.write("DECISIONS.md", "# Decisions\n\n| ID | Decision | Status |\n|---|---|---|\n| MD01 | Keep design | active |\n")
    repo.write(f"{directory}/audit.md", "# Audit\n\nFollow MD09.\n")
    assert not any(finding.rule == "decision-unknown" for finding in run(repo).findings)


@pytest.mark.parametrize("text,extension,expected", [("        let window_id = {", "app.rs", False), ("let window_id = 1;", "app.rs", False), ("    let window_id = 1;", "app.js", False), ("    var window_id = 1;", "app.js", False), ("    val window_id = 1", "app.kt", False), ("let window_id = 1;", "app.js", True), ("const window_id = 1;", "app.js", True), ("fn window_id() {", "app.rs", True)])
def test_local_variables_are_not_definitions(text, extension, expected):
    assert defines(text, "window_id", extension) is expected


@pytest.mark.parametrize("introduction", ["Suppose you have the following source code structure:", "Create your project with the following scaffold:", "Your project directory structure:"])
def test_reader_project_tree_not_checkout(introduction):
    repository = Repo()
    try:
        repository.write("index.md", "# Old\n")
        repository.write("README.md", f"# Guide\n\n{introduction}\n\n```text\n.\n├── index.md\n└── README.md\n```\n").commit()
        repository.mv("index.md", "docs/index.md")
        repository.commit("move")
        assert not serious(repository)
    finally:
        repository.cleanup()


def test_actual_checkout_tree_still_checked():
    repository = Repo()
    try:
        repository.write("index.md", "# Old\n")
        repository.write("README.md", "# Repository\n\nRepository structure:\n\n```text\n.\n├── index.md\n└── README.md\n```\n").commit()
        repository.mv("index.md", "docs/index.md")
        repository.commit("move")
        assert [finding.rule for finding in serious(repository)] == ["path-moved"]
    finally:
        repository.cleanup()


@pytest.mark.parametrize("tool_name", ["apply_patch", "ApplyPatch", "APPLY_PATCH"])
@pytest.mark.parametrize("shape", ["input", "patch", "commands", "nested"])
def test_codex_patch_doc_edits(repo, tool_name, shape):
    repo.write("docs/guide.md", "# Guide\n\n[missing](missing.md)\n")
    patch = "*** Begin Patch\n*** Update File: guide.md\n*** End Patch\n"
    payload = {"input": patch} if shape == "input" else {"patch": patch} if shape == "patch" else {"command": ["apply_patch", patch]} if shape == "commands" else {"nested": [{"arbitrary": patch}]}
    output = post_tool(repo.root, {"tool_name": tool_name, "cwd": str(repo.root / "docs"), "tool_input": payload})
    assert "docs/guide.md:3" in output


@pytest.mark.parametrize("header", ["Add File", "Delete File", "Move to"])
def test_codex_patch_file_header_variants(repo, header):
    repo.write("guide.md", "# Guide\n\n[missing](missing.md)\n")
    output = post_tool(repo.root, {"tool_name": "apply_patch", "tool_input": {"patch": f"*** {header}: guide.md\n"}})
    assert "guide.md:3" in output


def test_codex_patch_multiple_files(repo):
    repo.write("one.md", "# One\n\n[missing](missing.md)\n")
    repo.write("two.md", "# Two\n\n[missing](missing.md)\n")
    output = post_tool(repo.root, {"tool_name": "apply_patch", "tool_input": "*** Update File: one.md\n*** Add File: two.md\n"})
    assert "one.md:3" in output and "two.md:3" in output


@pytest.mark.parametrize("payload", [None, [], {}, {"tool_name": "apply_patch", "tool_input": 17}, {"tool_name": "apply_patch", "tool_input": {"input": "not a patch"}}, {"tool_name": "ApplyPatch", "tool_input": {"input": "*** Update File: ../outside.md\n"}}])
def test_codex_malformed_or_outside_patch_is_quiet(repo, payload):
    assert post_tool(repo.root, payload) == ""


def test_agents_override_session_and_cost(repo):
    from mindmap.cost import measure

    repo.write("AGENTS.override.md", "# Agents\n\n[missing](missing.md)\n")
    repo.write("src/AGENTS.override.md", "# Local agents\n")
    assert "AGENTS.override.md:3" in session_start(repo.root)
    rows = {row["file"]: row for row in measure(repo.root)}
    assert rows["AGENTS.override.md"]["loaded"] == "every session"
    assert rows["src/AGENTS.override.md"]["loaded"] == "when working in src/"


def test_inline_compound_cd_uses_only_directory(repo):
    repo.write("examples/demo/main.py", "value = 1\n")
    repo.write("README.md", "# Examples\n\nRun \x60cd examples/demo && npm install && npm run build\x60.\n")
    result = run(repo)
    assert not serious(repo)
    assert any(claim.target == "examples/demo" for claim in result.claims)
    assert not any("&&" in claim.target for claim in result.claims)


def test_unknown_tree_root_does_not_borrow_document_directory(repo):
    repo.write("docs/guide.md", "# Structure\n\n```text\nunrelated-root/\n├── src/\n│   └── missing.py\n└── config/\n```\n")
    repo.write("src/main.py", "value = 1\n")
    assert not serious(repo)


def test_real_tree_first_directory_still_checks_missing_path(repo):
    repo.write("src/notes/cli.py", "value = 1\n")
    repo.write("docs/guide.md", "# Repository\n\nRepository structure:\n\n```text\nsrc/\n└── notes/\n    ├── cli.py\n    └── missing_entry.py\n```\n")
    assert [(finding.rule, finding.claim) for finding in reported(repo)] == [("path-missing", "missing_entry.py")]


def test_flow_diagram_is_not_a_file_tree(repo):
    repo.write("docs/guide.md", "# Flow\n\n```text\nsrc/app\n├── User enters\n│   v\n│   updateSession\n└── Yes\n```\n")
    repo.write("src/app/main.py", "value = 1\n")
    assert not serious(repo)


def test_live_unknown_decision_still_warns(repo):
    repo.write("DECISIONS.md", "# Decisions\n\n| ID | Decision | Status |\n|---|---|---|\n| MD01 | Keep design | active |\n| MD02 | Keep tests | active |\n")
    repo.write("README.md", "# App\n\nPer MD02 we test. Follow MD09.\n")
    assert [finding.rule for finding in serious(repo)] == ["decision-unknown"]
