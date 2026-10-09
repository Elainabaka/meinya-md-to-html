import pytest

from mindmap import engine
from mindmap.gitinfo import Git
from mindmap.mdscan import github_slug, plain_heading, scan
from mindmap_fixture import Repo, run


@pytest.fixture
def repo():
    instance = Repo()
    yield instance
    instance.cleanup()


@pytest.mark.parametrize("heading, rendered", [
    (r"\*not bold\* and *bold*", "*not bold* and bold"),
    (r"\_not italic\_ and _italic_", "_not italic_ and italic"),
    (r"&lt;scope\> &amp; &#62; &#60;", "<scope> & > <"),
    (r"<span>label</span> &lt;tag&gt;", "label <tag>"),
    (r"`\*literal\* &amp; <tag>`", r"\*literal\* &amp; <tag>"),
    ("[`code`](url)", "code"),
    ("**`code`**", "code"),
])
def test_heading_preserves_literal_punctuation(heading, rendered):
    assert plain_heading(heading) == rendered


def test_encoded_punctuation_anchor():
    assert github_slug(r"--scope &lt;scope\> &#62;") == "--scope-scope-"


def test_partial_imports_recurse_and_stop_cycles(repo):
    repo.write("docs/page.mdx", '# Page\n\nimport Part from "./_part.mdx";\n')
    repo.write("docs/_part.mdx", "# Part\n\nimport Deep from './_deep.md'\n")
    repo.write("docs/_deep.md", '# Deep\n\nimport Page from "./page.mdx"\n')
    repo.write("README.md", "# Guide\n\n[deep](docs/page.mdx#deep)\n[absent](docs/page.mdx#absent)\n").commit()
    assert [(finding.rule, finding.line) for finding in run(repo).findings
            if finding.severity != "info"] == [("anchor-missing", 4)]


def test_fenced_import_does_not_contribute_anchors(repo):
    repo.write("docs/page.mdx", "# Page\n\n```js\nimport Part from './_part.mdx'\n```\n")
    repo.write("docs/_part.mdx", "# Hidden\n")
    repo.write("README.md", "# Guide\n\n[hidden](docs/page.mdx#hidden)\n").commit()
    assert [finding.rule for finding in run(repo).findings
            if finding.severity != "info"] == ["anchor-missing"]


@pytest.mark.parametrize("marker", ["sidebars.json", "docusaurus.config.ts"])
@pytest.mark.parametrize("docs_root", [
    "website/docs",
    "website/versioned_docs/version-2",
    "website/i18n/vi/docusaurus-plugin-content-docs/current",
])
def test_docusaurus_fallback_keeps_the_site_root_and_anchor(repo, marker, docs_root):
    repo.write("website/" + marker, "{}\n")
    repo.write("docs/x.md", "# Wrong site\n")
    repo.write(docs_root + "/x.md", "# Right site\n\n## Correct\n")
    repo.write(docs_root + "/guide/page.md", "# Guide\n\n[x](./x.md#correct)\n").commit()
    assert run(repo).findings == []


def test_docusaurus_fallback_does_not_escape_root(repo):
    repo.write("website/sidebars.json", "{}\n")
    repo.write("website/outside.md", "# Outside\n")
    repo.write("website/docs/deep/nested/page.md", "# Guide\n\n[x](../outside.md)\n").commit()
    assert [finding.rule for finding in run(repo).findings
            if finding.severity != "info"] == ["link-broken"]


@pytest.mark.parametrize("prompt", ["$ ", "❯ ", "➜ ", "% ", "PS> ", "PS C:\\repo> ", ">>> "])
def test_prompt_output_is_not_a_path_or_tree_claim(repo, prompt):
    repo.write("old.py", "value = 1\n")
    repo.write("README.md", "# Demo\n\n```console\n  " + prompt + "echo hello\nold.py\n└── old.py\n```\n").commit()
    repo.remove("old.py").commit("remove")
    assert [finding for finding in run(repo).findings if finding.severity != "info"] == []


@pytest.mark.parametrize("prompt", ["$ ", "❯ ", "➜ ", "% ", "PS> ", "PS C:\\repo> ", ">>> "])
def test_prompt_command_still_checked_after_previous_output(repo, prompt):
    repo.write("run.py", "print('hello')\n")
    repo.write("README.md", "# Demo\n\n```console\n" + prompt + "echo hello\noutput.py\n" +
               prompt + "py run.py\n```\n").commit()
    repo.remove("run.py").commit("remove")
    assert any(finding.rule == "command-missing" and finding.line == 6
               for finding in run(repo).findings)


def test_imports_are_not_scanned_from_fenced_examples():
    document = scan("page.mdx", '```mdx\nimport Part from "./_part.mdx";\n```\n')
    assert not document.imports


def test_focused_check_loads_imported_partial_on_demand(repo):
    repo.write("docs/page.mdx", '# Page\n\nimport Part from "./_part.mdx";\n')
    repo.write("docs/_part.mdx", "# Imported\n")
    repo.write("README.md", "# Guide\n\n[part](docs/page.mdx#imported)\n").commit()
    assert engine.run(repo.root, focus=["README.md"], light=True).findings == []


@pytest.mark.parametrize("method", ["grep_words", "alive_words"])
def test_git_grep_excludes_prohibited_names_before_reading(method):
    history = object.__new__(Git)
    history.sub = ""
    history._alive = {}
    commands = []
    history._git = lambda arguments, **options: commands.append(arguments) or b""
    if method == "grep_words":
        history.grep_words("HEAD", ["Example"])
    else:
        history.alive_words(["Example"])
    assert ":(glob,exclude,icase)**/*secret*" in commands[0]
    assert ":(glob,exclude,icase)**/*secret*/**" in commands[0]


@pytest.mark.parametrize("subdirectory", ["", "project", "proj[ect]", "build"])
def test_historical_grep_preserves_code_and_rejects_rendered_docs(repo, subdirectory):
    prefix = subdirectory + "/" if subdirectory else ""
    repo.write(prefix + "src/code.py", "class HistoricalName:\n    pass\n")
    repo.write(prefix + "GUIDE.MDX", "class OnlyInDocs:\n    pass\n")
    repo.write(prefix + "site/page.HTML", "class OnlyInDocs:\n    pass\n").commit()
    history = Git(repo.root, repo.root / subdirectory)
    found = history.grep_words("HEAD", ["HistoricalName", "OnlyInDocs"])
    assert found == {"HistoricalName": ("src/code.py", 1, True)}


def test_historical_grep_restricts_scan_root_as_a_literal_path():
    history = object.__new__(Git)
    history.sub = "project/"
    commands = []
    history._git = lambda arguments, **options: commands.append(arguments) or b""
    history.grep_words("HEAD", ["Example"])
    assert len(commands) == 1
    assert ":(literal)project/" in commands[0]
    assert ":(glob,exclude,icase)**/*secret*" in commands[0]


def test_historical_grep_preserves_nested_repo_mapping(repo):
    repo.write("src/code.py", "class FirstName:\n    pass\nclass SecondName:\n    pass\n").commit()
    history = Git(repo.root, repo.root.parent)
    assert history.grep_words("HEAD", ["FirstName"]) == {
        "FirstName": (repo.root.name + "/src/code.py", 1, True)}
