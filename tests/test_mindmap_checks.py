"""Mind Map checks on tiny git repos: every rule fires on a real problem and stays quiet otherwise."""

import pytest

from mindmap_fixture import Repo, rules, run

pytest.importorskip("mindmap")      # a copy of this repo may carry the tests before the package


@pytest.fixture
def repo():
    r = Repo()
    yield r
    r.cleanup()


def only(res, rule):
    return [f for f in res.findings if f.rule == rule]


# -- paths ------------------------------------------------------------------------

def test_moved_path_is_an_error_with_the_new_place(repo):
    repo.write("src/old_name.py", "def f():\n    return 1\n")
    repo.write("README.md", "# App\n\nRun `src/old_name.py` to start.\n").commit("add")
    repo.mv("src/old_name.py", "src/new_name.py")
    repo.commit("rename")
    res = run(repo)
    [f] = only(res, "path-moved")
    assert (f.severity, f.path, f.line) == ("error", "README.md", 3)
    assert "src/new_name.py" in f.suggestion
    assert any(e.get("rev") for e in f.evidence)


def test_line_that_describes_the_move_is_only_info(repo):
    repo.write("src/old_name.py", "x = 1\n")
    repo.write("README.md", "# App\n\nMove `src/old_name.py` to `src/new_name.py`.\n").commit("add")
    repo.mv("src/old_name.py", "src/new_name.py")
    repo.commit("rename")
    [f] = only(run(repo), "path-moved")
    assert f.severity == "info"


def test_near_miss_path_is_a_typo_warning(repo):
    repo.write("src/helper.py", "x = 1\n")
    repo.write("README.md", "# App\n\nEdit `src/helpr.py` first.\n").commit()
    [f] = only(run(repo), "path-typo")
    assert f.severity == "warning" and "src/helper.py" in f.suggestion


def test_path_that_never_existed_without_near_match_is_quiet(repo):
    repo.write("src/helper.py", "x = 1\n")
    repo.write("README.md", "# App\n\nOutput goes to `out/report.csv`.\n").commit()
    assert rules(run(repo)) == []


def test_uncommitted_delete_is_reported(repo):
    repo.write("src/app.py", "x = 1\n")
    repo.write("README.md", "# App\n\nSee `src/app.py`.\n").commit()
    repo.remove("src/app.py")
    [f] = only(run(repo), "path-moved")
    assert f.severity == "error"


def test_ignored_and_generated_paths_are_skipped(repo):
    repo.write(".gitignore", "build/\n")
    repo.write("README.md", "# App\n\nArtifacts land in `build/app.bin` and `node_modules/x/y.js`.\n").commit()
    assert rules(run(repo)) == []


# -- links ------------------------------------------------------------------------

def test_links_and_anchors(repo):
    repo.write("docs/guide.md", "# Guide\n\n## Setup\n\nText.\n")
    repo.write("README.md", "# App\n\n[ok](docs/guide.md#setup) [bad anchor](docs/guide.md#nope) "
                            "[missing](docs/missing.md)\n").commit()
    got = sorted((f.rule, f.severity) for f in run(repo).findings)
    assert got == [("anchor-missing", "warning"), ("link-broken", "error")] or \
        got == [("anchor-missing", "error"), ("link-broken", "error")]


def test_many_never_existing_links_collapse_into_one_note(repo):
    links = " ".join(f"[{i}](../other/{i}.md)" for i in range(5))
    repo.write("docs/copied.md", f"# Copied\n\n{links}\n").commit()
    res = run(repo)
    assert [f.rule for f in res.findings] == ["foreign-links"]
    assert res.findings[0].severity == "info"


# -- code names -------------------------------------------------------------------

def _symbol_repo(repo, line):
    repo.write("src/app.py", "def build_index():\n    return 1\n")
    repo.write("README.md", f"# App\n\n{line}\n").commit("add")
    repo.write("src/app.py", "def make_index():\n    return 1\n").commit("rename function")


def test_removed_symbol_is_a_warning_with_evidence(repo):
    _symbol_repo(repo, "Call `build_index()` first.")
    [f] = only(run(repo), "symbol-gone")
    assert f.severity == "warning"
    assert any(e.get("path") == "src/app.py" for e in f.evidence)
    assert f.evidence[-1]["note"] == "removed by this commit: rename function"


def test_removal_commit_is_found_when_the_new_name_contains_the_old_one(repo):
    repo.write("src/app.py", "def build_index():\n    return 1\n")
    repo.write("README.md", "# App\n\nCall `build_index()` first.\n").commit("add")
    repo.write("src/app.py", "def rebuild_index():\n    return 1\n").commit("rebuild")
    [f] = only(run(repo), "symbol-gone")
    assert f.evidence[-1]["note"] == "removed by this commit: rebuild"
    assert "rebuild_index" in f.suggestion


def test_removal_commit_is_left_out_when_the_file_moved_with_the_name(repo):
    repo.write("src/app.py", "def build_index():\n    return 1\n")
    repo.write("README.md", "# App\n\nCall `build_index()` first.\n").commit("add")
    repo.mv("src/app.py", "src/core.py").commit("move")
    repo.write("src/core.py", "def make_index():\n    return 1\n").commit("rename function")
    [f] = only(run(repo), "symbol-gone")
    assert not any("removed by" in e.get("note", "") for e in f.evidence)


def test_removed_symbol_in_a_past_sentence_is_info(repo):
    _symbol_repo(repo, "In v1.2–v1.6 `build_index()` did this work.")
    [f] = only(run(repo), "symbol-gone")
    assert f.severity == "info"


def test_removed_symbol_the_line_calls_removed_is_quiet(repo):
    _symbol_repo(repo, "`build_index()` was removed.")
    assert only(run(repo), "symbol-gone") == []


def test_existing_symbol_is_verified(repo):
    repo.write("src/app.py", "def build_index():\n    return 1\n")
    repo.write("README.md", "# App\n\nCall `build_index()` first.\n").commit()
    res = run(repo)
    assert res.findings == []
    assert any(c.status == "ok" and "build_index" in c.text for c in res.claims)


# -- commands ---------------------------------------------------------------------

def test_script_flags(repo):
    repo.write("tool.py", "import argparse\np = argparse.ArgumentParser()\np.add_argument('--quick')\n")
    repo.write("README.md", "# Tool\n\nRun `python tool.py --quick` or `python tool.py --fast`.\n").commit()
    got = [(f.rule, f.claim) for f in run(repo).findings]
    assert len(got) == 1 and got[0][0] == "flag-missing" and "--fast" in run(repo).findings[0].message


def test_removed_flag_names_the_commit(repo):
    repo.write("tool.py", "import argparse\np = argparse.ArgumentParser()\np.add_argument('--fast')\n")
    repo.write("README.md", "# Tool\n\nRun `python tool.py --fast`.\n").commit("add")
    repo.write("tool.py", "import argparse\np = argparse.ArgumentParser()\np.add_argument('--quick')\n").commit()
    [f] = run(repo).findings
    assert f.rule == "flag-removed" and f.evidence and f.evidence[0].get("rev")
    last = f.evidence[-1]
    assert last["note"] == "removed by this commit: change" and last["rev"] != f.evidence[0]["rev"]


def test_npm_scripts_and_make_targets(repo):
    repo.write("package.json", '{"name": "x", "scripts": {"build": "tsc"}}\n')
    repo.write("Makefile", "all:\n\techo all\nbuild:\n\techo build\n")
    repo.write("README.md", "# X\n\n`npm run build`, `npm run deploy`, `make build`, `make ship`.\n").commit()
    got = sorted((f.rule, f.severity) for f in run(repo).findings)
    assert got == [("make-target-missing", "error"), ("npm-script-missing", "error")]


# -- decisions --------------------------------------------------------------------

DECISIONS = """# Decisions

| ID | Decision | Status |
|---|---|---|
| MD01 | Use SQLite | superseded by MD02 |
| MD02 | Use Postgres | active |
"""


def test_decision_references(repo):
    repo.write("DECISIONS.md", DECISIONS)
    repo.write("README.md", "# App\n\nPer MD01 we store data. See MD02. MD09 says so.\n").commit()
    got = {(f.rule, f.claim) for f in run(repo).findings if f.path == "README.md"}
    assert ("decision-superseded", "MD01") in got
    assert ("decision-unknown", "MD09") in got
    assert not any(c == "MD02" for _, c in got)


def test_decision_rows_cut_off_from_the_table_still_count(repo):
    text = DECISIONS + "\nA note that breaks the table.\n| MD03 | Use Redis | active |\n| MD04 | Cache | active |\n"
    repo.write("DECISIONS.md", text)
    repo.write("README.md", "# App\n\nSee MD03 and MD04.\n").commit()
    res = run(repo)
    assert not [f for f in res.findings if f.rule == "decision-unknown"]
    assert [f.rule for f in res.findings if f.path == "DECISIONS.md"] == ["table-orphan"]


# -- tables -----------------------------------------------------------------------

def test_table_broken_by_a_blank_line(repo):
    repo.write("README.md", "# T\n\n| a | b |\n|---|---|\n| 1 | 2 |\n\n| 3 | 4 |\n| 5 | 6 |\n").commit()
    [f] = run(repo).findings
    assert (f.rule, f.severity, f.line) == ("table-orphan", "warning", 7)
    assert "blank line 6" in f.suggestion


def test_table_cut_by_a_line_break_in_a_cell(repo):
    repo.write("README.md", "# T\n\n| a | b |\n|---|---|\n| 1 | two\nlines |\n| 3 | 4 |\n| 5 | 6 |\n").commit()
    [f] = run(repo).findings
    assert f.rule == "table-orphan" and "join line 6 onto line 5" in f.suggestion


# -- doc types --------------------------------------------------------------------

def test_plan_docs_are_capped_at_info(repo):
    repo.write("PLAN.md", "# Plan\n\nNext: wire [the api](docs/api.md) into `src/server.py`.\n").commit()
    assert {f.severity for f in run(repo).findings} <= {"info"}


def test_history_docs_only_check_decisions(repo):
    repo.write("src/old.py", "x = 1\n")
    repo.write("CHANGELOG.md", "# Changelog\n\n- Added `src/old.py` and [notes](notes.md).\n").commit()
    repo.remove("src/old.py").commit("drop")
    assert run(repo).findings == []


def test_done_rows_are_capped_at_info(repo):
    repo.write("src/app.py", "x = 1\n")
    repo.write("ROADMAP.md", "# Roadmap\n\n| Task | Status |\n|---|---|\n| Write `src/app.py` | DONE |\n").commit()
    repo.remove("src/app.py").commit("drop")
    assert {f.severity for f in run(repo).findings} <= {"info"}


# -- directives, baseline, rules ---------------------------------------------------

def test_ignore_next_line(repo):
    repo.write("README.md", "# A\n\n<!-- mindmap: ignore-next-line -->\nSee [x](missing1.md).\n"
                            "See [y](missing2.md).\n").commit()
    assert [(f.rule, f.line) for f in run(repo).findings] == [("link-broken", 5)]


def test_a_directive_written_as_code_is_not_obeyed(repo):
    repo.write("README.md", "# A\n\nAdd `<!-- mindmap: ignore-file -->` to skip a file, "
                            "`<!-- mindmap: ignore -->` to skip a line.\n\nSee [x](missing.md).\n"
                            "See [y](gone.md). <!-- mindmap: ignore -->\n").commit()
    assert [(f.rule, f.line) for f in run(repo).findings] == [("link-broken", 5)]


def test_baseline_hides_known_findings(repo, tmp_path):
    from mindmap import engine
    repo.write("README.md", "# A\n\nSee [x](missing.md).\n").commit()
    res = run(repo)
    assert len(res.findings) == 1
    base = tmp_path / "baseline.json"
    engine.save_baseline(base, res.findings)
    again = run(repo, baseline=base)
    assert again.findings == [] and again.suppressed == 1


def test_forbid_rule_finds_violations_in_code(repo):
    repo.write("AGENTS.md", "# Rules\n\nNever call os.kill with signal 0 on Windows.\n"
                            "<!-- mindmap: forbid /os\\.kill\\(\\w+, 0\\)/ in **/*.py -->\n")
    repo.write("src/proc.py", "import os\n\ndef alive(pid):\n    os.kill(pid, 0)\n").commit()
    [f] = [f for f in run(repo).findings if f.rule == "rule-violation"]
    assert (f.path, f.line, f.severity) == ("src/proc.py", 4, "error")


def test_bad_forbid_rule_is_reported(repo):
    repo.write("AGENTS.md", "# Rules\n\n<!-- mindmap: forbid /([/ in *.py -->\n").commit()
    assert [f.rule for f in run(repo).findings] == ["rule-invalid"]


# -- environments -----------------------------------------------------------------

def test_works_without_git():
    r = Repo(git=False)
    try:
        r.write("README.md", "# A\n\nSee [x](missing.md) and `src/nothere.py`.\n")
        res = run(r)
        assert [f.rule for f in res.findings] == ["link-broken"]
        assert res.stats["git"] is False
    finally:
        r.cleanup()


def test_vietnamese_messages(repo):
    repo.write("README.md", "# A\n\nXem [x](missing.md).\n").commit()
    [f] = run(repo, lang="vi").findings
    assert "không tồn tại" in f.message or "không có" in f.message


def test_files_that_may_hold_secret_values_are_never_read():
    from mindmap.files import is_private
    for p in (".env", "conf/app-secret.json", "cookie/yt.json", "data/cookies/a.txt", "yt_cookies.txt",
              "keys/id_rsa", "tls/server.pem"):
        assert is_private(p), p
    for p in (".env.example", "src/cookie_store.py", "docs/cookies.md", "README.md"):
        assert not is_private(p), p


# -- lessons from repos never seen before -------------------------------------------

def test_a_tutorial_path_is_not_an_old_file_that_ends_the_same_way(repo):
    repo.write("tools/preview/app/main.py", "print(1)\n")
    repo.write("docs/testing.md", "# Testing\n\nLet's say you have an application `app/main.py` with:\n").commit("add")
    repo.remove("tools/preview/app/main.py").commit("drop the preview tool")
    assert run(repo).findings == []


def test_a_path_known_by_its_ending_counts_only_when_it_points_one_way(repo):
    repo.write("src/pkg/report_builder.py", "x = 1\n")
    repo.write("old/pkg/sheet_writer.py", "x = 1\n").write("new/pkg/sheet_writer.py", "x = 1\n")
    repo.write("docs/guide.md", "# Guide\n\nOpen `pkg/report_builder.py` and `pkg/sheet_writer.py`.\n").commit("add")
    repo.remove("src/pkg/report_builder.py").remove("old/pkg/sheet_writer.py").remove("new/pkg/sheet_writer.py")
    repo.commit("drop")
    [f] = run(repo).findings
    assert f.rule == "path-moved" and "report_builder" in f.message


def test_a_bare_script_name_far_from_the_doc_is_the_readers_own_script(repo):
    repo.write("pkg/main.py", "import argparse\np = argparse.ArgumentParser()\np.add_argument('--quick')\n")
    repo.write("pkg/skills/cli/GUIDE.md", "# Guide\n\n```bash\npython main.py --name Morty\n```\n").commit()
    assert run(repo).findings == []


def test_typer_options_come_from_parameter_names(repo):
    repo.write("main.py", "import typer\n\n\ndef main(name: str, dry_run: bool = False):\n    print(name)\n\n\n"
                          "typer.run(main)\n")
    repo.write("README.md", "# App\n\nRun `python main.py --name Morty --dry-run`, never `python main.py --shout`.\n")
    repo.commit()
    [f] = run(repo).findings
    assert f.rule == "flag-missing" and "--shout" in f.message


def test_a_name_still_used_by_a_script_without_an_extension_is_not_gone(repo):
    repo.write("ci/release.yml", "env:\n  RELEASE_CHANNEL: stable\n")
    repo.write("bin/publish", '#!/usr/bin/env bash\necho "$RELEASE_CHANNEL"\n')
    repo.write("CONTRIBUTING.md", "# Contributing\n\nRun `bin/publish` with `RELEASE_CHANNEL` set.\n").commit("add")
    repo.write("ci/release.yml", "env: {}\n").commit("simplify")
    assert run(repo).findings == []
    repo.remove("bin/publish").commit("drop the script")
    assert "symbol-gone" in [f.rule for f in run(repo).findings]


def test_broken_link_says_where_the_target_is(repo):
    repo.write("docs/tutorial/install.md", "# Install\n")
    repo.write("README.md", "# App\n\nSee the [guide](tutorial/install.md).\n").commit()
    [f] = run(repo).findings
    assert f.rule == "link-broken" and "docs/tutorial/install.md" in f.suggestion


def test_html_id_or_name_on_any_tag_is_an_anchor(repo):
    repo.write("FAQ.md", '# FAQ\n\n<h3 name="complete">\nShell completion?\n</h3>\n\n<div id=setup>x</div>\n')
    repo.write("README.md", "# App\n\n[a](FAQ.md#complete) [b](FAQ.md#setup) [c](FAQ.md#nope)\n").commit()
    got = [(f.rule, f.claim) for f in run(repo).findings]
    assert got == [("anchor-missing", "FAQ.md#nope")]


def test_a_library_name_the_code_stopped_using_is_a_note_not_a_warning(repo):
    repo.write("src/lib.rs", "use regex::bytes::{Regex, RegexSet};\n\npub struct GlobSet {\n}\n")
    repo.write("README.md", "# App\n\nPatterns are matched with a `RegexSet` inside `GlobSet`.\n").commit("add")
    repo.write("src/lib.rs", "use regex::bytes::Regex;\n\npub struct Globs {\n}\n").commit("rework")
    got = sorted((f.claim, f.severity) for f in only(run(repo), "symbol-gone"))
    assert got == [("GlobSet", "warning"), ("RegexSet", "info")]


def test_a_link_that_differs_by_letter_case_is_reported_on_every_system(repo):
    # Windows and macOS open `Docs/Guide.md` when the file is `docs/guide.md`; GitHub and Linux do not
    repo.write("docs/guide.md", "# Guide\n\n## Setup\n\ntext\n")
    repo.write("docs/shot.png", "png")
    repo.write("README.md", "# App\n\nSee the [guide](Docs/Guide.md#setup) and ![shot](./docs/Shot.PNG).\n"
                            "Right: [guide](docs/guide.md#setup), ![shot](docs/shot.png). Gone: [x](docs/nope.md).\n")
    repo.write("docs/more.md", "# More\n\nBack to the [readme](../readme.md).\n").commit()
    got = sorted((f.rule, f.severity, f.path, f.claim, f.suggestion) for f in run(repo).findings)
    assert got == [
        ("link-broken", "error", "README.md", "docs/nope.md", ""),
        ("link-case", "warning", "README.md", "./docs/Shot.PNG", "write `./docs/shot.png`"),
        ("link-case", "warning", "README.md", "Docs/Guide.md#setup", "write `docs/guide.md#setup`"),
        ("link-case", "warning", "docs/more.md", "../readme.md", "write `../README.md`"),
    ]


def test_a_link_written_for_the_built_site_finds_its_source_page(repo):
    # MkDocs, Docusaurus, Hugo serve `page.md` at `page/`: such a link names no file, yet its page and heading can be checked
    repo.write("docs/advanced/transports.md", "# Transports\n\n## ASGI Transport\n\ntext\n")
    repo.write("docs/guide/index.md", "# Guide\n")
    repo.write("docs/about.html", "<h1>About</h1>\n")
    repo.write("docs/async.md", "# Async\n\nSee [a](../advanced/transports#asgi-transport), [b](../advanced/transports/#old-name),\n"
                                "[c](advanced/transports.html), [d](guide/), [e](../guide), [f](/advanced/transports/), [g](about).\n"
                                "A page the site makes itself: [h](/api/Client/), [i](../reference). A file: [j](../advanced/nothing.md).\n")
    repo.write("README.md", "# App\n\nNo site address works from here: [k](LICENSE).\n").commit()
    got = sorted((f.path, f.rule, f.severity, f.claim) for f in run(repo).findings)
    assert got == [("README.md", "link-broken", "error", "LICENSE"),
                   ("docs/async.md", "anchor-unverified", "info", "../advanced/transports/#old-name"),
                   ("docs/async.md", "link-broken", "error", "../advanced/nothing.md"),
                   ("docs/async.md", "link-unverified", "info", "2 links")]


def test_a_site_address_that_fits_two_pages_gets_no_heading_check(repo):
    # `quickstart` from docs/guide.md is docs/quickstart.md on one site and docs/guide/quickstart.md on another
    repo.write("docs/quickstart.md", "# Quickstart\n\n## Install\n")
    repo.write("docs/guide/quickstart.md", "# Quickstart of the guide\n\n## Setup\n")
    repo.write("docs/guide.md", "# Guide\n\n[one](quickstart#setup), [two](quickstart#install), [three](quickstart#nope)\n").commit()
    assert run(repo).findings == []


def test_a_link_to_a_template_variable_is_not_a_link(repo):
    repo.write("notices.md", "# Notice\n\nRead the [English page](ENGLISH_PAGE) or [the others](TRANSLATIONS_PAGE).\n"
                             "See the [license](LICENSE).\n").commit()
    assert [(f.rule, f.claim) for f in run(repo).findings] == [("link-broken", "LICENSE")]


def test_a_root_relative_site_address_stays_inside_the_site_of_its_doc(repo):
    # translations repeat every ending: `/guides/setup/` from an English page is the English page
    repo.write("site/docs/guides/setup.md", "# Setup\n\n## Install\n")
    repo.write("site/docs/de/guides/setup.md", "# Einrichtung\n\n## Installieren\n")
    repo.write("site/docs/guides/intro.md", "# Intro\n\n[ok](/guides/setup/#install), [bad](/guides/setup/#installieren)\n")
    repo.write("site/docs/de/guides/intro.md", "# Intro\n\n[ok](/de/guides/setup/#installieren), "
                                               "[either](/guides/setup/#nope)\n").commit()
    got = [(f.path, f.rule, f.claim) for f in run(repo).findings]
    assert got == [("site/docs/guides/intro.md", "anchor-unverified", "/guides/setup/#installieren")]


def test_a_heading_is_found_however_the_site_names_it(repo):
    # GitHub drops the dot of `build.target`, a VitePress site turns it into a hyphen, repeats get a number
    repo.write("docs/options.md", "# Options\n\n## build.target\n\n## `index.html` and Project Root\n\n"
                                  "## `<Badge>` Props\n\n## [@scope/pkg](https://example.com/pkg)\n\n"
                                  "## Notes\n\nA term {#term-id}\n\n## Notes\n")
    repo.write("README.md", "# App\n\n[a](docs/options.md#build-target) [b](docs/options.md#buildtarget) "
                            "[c](docs/options.md#index-html-and-project-root) [d](docs/options.md#badge-props)\n"
                            "[e](docs/options.md#scope-pkg) [f](docs/options.md#notes-1) [g](docs/options.md#term-id) "
                            "[h](docs/options.md#build-outdir) [i](docs/options.md#pkg.Client.get)\n").commit()
    got = sorted((f.rule, f.severity, f.claim) for f in run(repo).findings)
    assert got == [("anchor-missing", "warning", "docs/options.md#build-outdir"),
                   ("anchor-unverified", "info", "docs/options.md#pkg.Client.get")]


def test_a_link_from_the_site_root_finds_the_file_under_some_folder(repo):
    # VitePress, Docusaurus, Hugo: `/logo.png` is docs/public/logo.png, `/config/options.md` is docs/config/options.md
    repo.write("docs/public/logo.png", "png")
    repo.write("docs/config/options.md", "# Options\n\n## base\n")
    repo.write("docs/blog/post.md", "# Post\n\n![logo](/logo.png) [base](/config/options.md#base) "
                                    "[gone](/config/options.md#nope)\n[theme](/theme/extra.css)\n").commit()
    got = sorted((f.rule, f.severity, f.claim) for f in run(repo).findings)
    assert got == [("anchor-unverified", "info", "/config/options.md#nope"),
                   ("link-unverified", "info", "/theme/extra.css")]


def test_a_package_script_is_looked_for_in_the_whole_workspace(repo):
    repo.write("package.json", '{"name": "root", "scripts": {"lint": "eslint ."}}')
    repo.write("packages/app/package.json", '{"name": "app", "scripts": {"dev": "vite", "test": "vitest"}}')
    repo.write("README.md", "# Mono\n\n```sh\npnpm test\nnpm run dev\npnpm vite build\nyarn patch left-pad\n"
                            "npm run nothing\n```\n")
    repo.write("docs/guide.md", "# Guide\n\nDeploy your own site with `npm run deploy`.\n").commit()
    got = sorted((f.path, f.rule, f.severity, f.claim) for f in run(repo).findings)
    assert got == [("README.md", "npm-script-missing", "error", "npm run nothing"),
                   ("docs/guide.md", "npm-script-missing", "info", "npm run deploy")]


def test_a_renamed_heading_is_proven_by_the_history_of_the_page(repo):
    repo.write("docs/guide.md", "# Guide\n\n## Quick start\n\ntext\n\n```sh\n# made by a plugin\n```\n")
    repo.write("docs/index.md", "# Home\n\nSee [start](guide#quick-start) and [made](guide#made-by-a-plugin).\n").commit("docs")
    repo.write("docs/guide.md", "# Guide\n\n## Getting started\n\ntext\n").commit("Rename the first section")
    got = [(f.rule, f.severity, f.claim, [e.get("note") for e in f.evidence]) for f in run(repo).findings]
    assert got == [("anchor-missing", "warning", "guide#quick-start",
                    ["the heading `Quick start` was removed by this commit: Rename the first section"]),
                   ("anchor-unverified", "info", "guide#made-by-a-plugin", [])]


def test_a_path_the_repo_once_had_needs_a_doc_that_named_it_then(repo):
    # a guide about the reader's project says `config/_default`; this repo had such a folder before the guide
    repo.write("config/_default/site.toml", "x = 1\n")
    repo.write("docs/old.md", "# Old\n\nSettings live in `config/_default/site.toml`.\n").commit("start")
    repo.remove("config/_default/site.toml").commit("drop the config folder")
    repo.write("docs/new.md", "# New\n\nPut your settings in `config/_default/site.toml`.\n")
    repo.write("docs/old.md", "# Old\n\nAll settings live in `config/_default/site.toml`.\n").commit("write the guide")
    assert [(f.path, f.rule, f.severity) for f in run(repo).findings] == [("docs/old.md", "path-gone", "warning")]


def test_a_template_keeps_its_dotfile_under_another_name(repo):
    repo.write("template/_gitignore", "node_modules\n")
    repo.write("template/README.md", "# Template\n\nEdit `.gitignore` to taste.\n").commit()
    assert run(repo).findings == []


def test_a_dated_post_keeps_the_figures_of_its_day(repo):
    line = "We invite you to help us improve the project, joining the more than {} contributors who sent a patch.\n"
    repo.write("docs/blog/release-7.md", "# Release 7\n\n" + line.format("1.1K")).commit()
    repo.write("docs/blog/release-8.md", "# Release 8\n\n" + line.format("1.2K")).commit()
    assert run(repo).findings == []
    repo.write("docs/about.md", "# About\n\n" + line.format("1.1K")).commit()
    repo.write("README.md", "# App\n\n" + line.format("1.2K")).commit()
    assert [(f.rule, f.path) for f in run(repo).findings] == [("copies-diverged", "docs/about.md")]


def test_a_symlinked_doc_is_read_once_at_its_real_path(repo):
    # git stores a link as a tiny blob; Windows checks it out as a one-line text file, Linux as a real link
    repo.git("config", "core.symlinks", "false")
    repo.write("packages/app/README.md", "# App\n\nCopyright (c) 2023-present the contributors of this project, all of them.\n")
    repo.write("packages/kit/README.md", "# Kit\n\nCopyright (c) 2024-present the contributors of this project, all of them.\n"
                                         "Back to the [front page](../../README.md).\n")
    repo.write("README.md", "packages/app/README.md").git("add", "-A")
    blob = repo.git("hash-object", "-w", "README.md").strip()
    repo.git("update-index", "--cacheinfo", f"120000,{blob},README.md")
    repo.commit()
    res = run(repo)
    assert sorted(res.docs) == ["packages/app/README.md", "packages/kit/README.md"]
    assert res.findings == []


def test_files_changed_by_one_commit_are_listed_in_the_same_order_every_run(repo):
    names = [f"src/part_{i:02d}.py" for i in range(12)]
    for n in names:
        repo.write(n, "x = 1\n")
    repo.write("README.md", "# App\n\n" + "".join(f"- `{n}`\n" for n in names)).commit("start")
    repo.write("notes.txt", "a day passes\n").commit("filler")
    for n in names:
        repo.write(n, "x = 2\n")
    repo.commit("one commit touches them all")
    [f] = only(run(repo), "stale-risk")
    assert [e["path"] for e in f.evidence] == names[:5]


def test_a_side_history_merged_in_does_not_lend_its_files_to_the_other_side(repo):
    # a docs repo that also carries the history of the project itself: two lines of commits, side by side
    repo.write("guide.md", "# Guide\n\nKeep your settings in `config/site.toml`.\n").commit("docs: the guide")
    docs = repo.git("rev-parse", "--abbrev-ref", "HEAD").strip()
    repo.git("checkout", "-q", "--orphan", "project")
    repo.git("rm", "-rfq", ".")
    repo.write("config/site.toml", "x = 1\n").write("main.go", "package main\n").commit("project: first commit")
    repo.git("merge", "-q", "--allow-unrelated-histories", "-m", "bring the docs in", docs)
    repo.remove("config/site.toml").commit("project: the settings move elsewhere")
    assert run(repo).findings == []     # the commit that wrote the line never had that file


def test_a_bare_file_name_far_from_the_file_is_every_projects_file(repo):
    repo.write("yarn.lock", "# lock\n")
    repo.write("docs/guide/cache.md", "# Cache\n\nThe cache follows the lock file, such as `yarn.lock`.\n")
    repo.write("README.md", "# App\n\nInstall, then commit `yarn.lock`.\n").commit("start")
    repo.remove("yarn.lock").commit("another package manager")
    repo.write("docs/guide/cache.md", "# Cache\n\nThe cache follows the lock file of your project, such as `yarn.lock`.\n")
    repo.write("README.md", "# App\n\nInstall first, then commit `yarn.lock`.\n").commit("reword both")
    assert [(f.path, f.rule, f.severity) for f in run(repo).findings] == [("README.md", "path-gone", "warning")]


def test_a_term_of_a_definition_list_can_be_linked_to(repo):
    repo.write("docs/fields.md", "# Fields\n\n## aliases\n\ntext\n\n## draft\n\ntext\n")
    repo.write("docs/index.md", "# Home\n\nSee [aliases](fields.md#aliases) and [draft](fields.md#draft).\n").commit("docs")
    repo.write("docs/fields.md", "# Fields\n\naliases\n: (`string array`) Other addresses of the page.\n\n"
                                 "`draft`\n\n: (`bool`) Not published yet.\n").commit("Turn the headings into a list of terms")
    assert run(repo).findings == []     # a site can give every term an id; the term is still on the page


def test_a_file_name_with_a_place_in_it_is_a_path_not_a_name(repo):
    repo.write("docs/setup.py", "def install():\n    return 1\n")
    repo.write("docs/guide.md", "# Guide\n\n## Install\n\ntext\n")
    repo.write("docs/index.md", "# Home\n\nStart at `guide.md#install`, then read `src/app.py#L10`.\n").commit("start")
    repo.write("docs/setup.py", "def setup():\n    return 1\n").commit("rename the function")
    res = run(repo)
    assert res.findings == []       # `install` left the code, but the line never spoke of a function
    assert [(c.kind, c.target, c.status) for c in res.claims] == [("path", "guide.md", "ok"),
                                                                   ("path", "src/app.py", "unverified")]


def test_a_commit_day_reads_the_same_in_every_time_zone():
    import calendar

    from mindmap.gitinfo import day
    assert day(calendar.timegm((2026, 1, 5, 0, 30, 0))) == "2026-01-05"       # west of Greenwich the clock says the 4th
    assert day(calendar.timegm((2026, 1, 5, 23, 30, 0))) == "2026-01-05"      # east of it, the 6th
    assert day(str(calendar.timegm((2026, 1, 5, 12, 0, 0)))) == "2026-01-05"  # as git prints it
    assert day(None) == day("") == day("soon") == ""


DEFINED = [
    ("def build_index():", "build_index"), ("class CORSMiddleware:", "CORSMiddleware"), ("MAX_RETRIES = 3", "MAX_RETRIES"),
    ("    max_retries: int = 3", "max_retries"), ("export const buildIndex = () => {", "buildIndex"),
    ("module.exports.buildIndex = function () {", "buildIndex"), ("  buildIndex(a, b) {", "buildIndex"),
    ("func (s *Server) ListenAll(addr string) error {", "ListenAll"), ("type GlobSet struct {", "GlobSet"),
    ("pub(crate) fn build_index(", "build_index"), ("impl<T> GlobSet<T> {", "GlobSet"),
    ("public void buildIndex(String a) {", "buildIndex"), ("static const int MAX_DEPTH = 8;", "MAX_DEPTH"),
    ("    private final Map<String, Index> buildIndex;", "buildIndex"), ("#define MAX_DEPTH 8", "MAX_DEPTH"),
    ("def get(url, timeout=5):", "timeout"), ("  PYPI_TOKEN: ${{ secrets.X }}", "PYPI_TOKEN"),
    ("export RELEASE_CHANNEL=stable", "RELEASE_CHANNEL"), ('  "build": "tsc",', "build"), ("[tool.mindmap]", "mindmap"),
    ("CREATE TABLE IF NOT EXISTS job_runs (", "job_runs"), (":build_all", "build_all"),
]
ONLY_USED = [
    ("use regex::bytes::{Regex, RegexBuilder, RegexSet};", "RegexSet"), ("    RegexSet::new(pats).map_err(|err| {", "RegexSet"),
    ("fn new_regex_set<I, S>(pats: I) -> Result<RegexSet, Error>", "RegexSet"), ("from app.core import build_index", "build_index"),
    ("const { buildIndex } = require('./core');", "buildIndex"), ("const RegexSet = require('regex-set');", "RegexSet"),
    ("    result = build_index(folder)", "build_index"), ("    return build_index(a)", "build_index"), ("    main()", "main"),
    ("public static RegexSet build(List<String> pats) {", "RegexSet"), ("    let x: RegexSet = make();", "RegexSet"),
    ("class Foo extends RegexSet {", "RegexSet"), ("def f(a: RegexSet, b) -> RegexSet:", "RegexSet"),
    ("    buildIndex(folder, (err) => {", "buildIndex"), ("    with RegexSet(pats) as s:", "RegexSet"),
    ("impl fmt::Display for GlobSet {", "Display"), ("    static RegexSet set;", "RegexSet"),
]


def test_a_line_defines_a_name_or_only_uses_it():
    from mindmap.gitinfo import defines
    assert [x for x in DEFINED if not defines(*x)] == []
    assert [x for x in ONLY_USED if defines(*x)] == []
    assert defines("build_index()", "build_index", "bin/run") and not defines("build_index()", "build_index", "app.py")
    assert not defines("var RegexSet=1;" + "function a(b){return c(b,d)};" * 5000, "RegexSet")      # a minified bundle
