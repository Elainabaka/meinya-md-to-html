# Meinya Mind Map

**Your docs make claims about your code. Mind Map checks them, and shows the commit that broke each one.**

[Tiếng Việt](README.vi.md)

A README, an `AGENTS.md`, a `CLAUDE.md`, a guide: each names files, commands, options, functions and decisions. The code moves on and the doc keeps saying the old thing. A person loses an hour to it. A coding agent reads the stale line at the start of every session and acts on it.

Mind Map reads your Markdown, picks out every claim a machine can check, and checks it against the working tree and the git history. It uses no model and no network, and needs nothing but Python and git.

![The HTML report for a small demo repo](docs/mind-map-report.png)

## Try it

```bash
pip install git+https://github.com/Elainabaka/meinya-mind-map
cd your-repo
mindmap check .
```

Or without installing: clone this repo and run `python -I run_mindmap.py check /path/to/your-repo`.

This is what it prints for the demo repo in the picture:

<!-- mindmap: ignore-start -->
```text
README.md
  7:5  error  `scripts/setup.sh` no longer exists; it did when this line was written (2026-03-02)  [path-moved]
      ↳ 59c8e6d417 2026-03-02 · scripts/setup.sh · existed when the line was written
      ↳ b81c7e1cbb 2026-06-20 · tools/setup.sh · renamed
      → moved to `tools/setup.sh` in b81c7e1cbb (2026-06-20)
  11:1  warning  `--fast` was removed from `src/notes/cli.py` after this line was written (2026-03-02)  [flag-removed]
      ↳ 59c8e6d417 2026-03-02 · src/notes/cli.py
      ↳ c33a5ae744 2026-07-07 · src/notes/cli.py · removed by this commit: Drop --fast: the fast path is always on
  14:20  warning  no heading `#quick-start` in `docs/guide.md`  [anchor-missing]
      ↳ f740d7dfac 2026-08-15 · docs/guide.md · the heading `Quick start` was removed by this commit: Guide: rename the first section
  18:1  warning  `build_index()` is gone from the code; it existed when this line was written (2026-03-02)  [symbol-gone]
      ↳ 59c8e6d417 2026-03-02 · src/notes/cli.py:6 · `build_index` was here
      ↳ a3c7e3270a 2026-05-11 · src/notes/cli.py · removed by this commit: Rename build_index to rebuild_index
      → maybe renamed to `rebuild_index` (src/notes/cli.py)
  19:26  warning  decision D01 was replaced by D03; check this line still holds  [decision-superseded]
      ↳ DECISIONS.md:5

4 docs, 17 claims, 10 verified · 1 error, 6 warnings, 2 info · 0.8s
```
<!-- mindmap: ignore-end -->

For the page in the picture, add `--format html --out report.html`. It is one file and opens offline.

## How it decides

1. **Every finding carries its proof.** A file and line, or a commit id with its date and subject. You can check the checker.
2. **It reads history.** For each doc line it asks git when the line was written and what the repo held at that commit. "This file was here when you wrote the line, and commit `b81c7e1` moved it" is an error. "This name was never in the repo" is usually an example, another project or the reader's own file, so it stays quiet.
3. **No proof, no warning.** Plans, changelogs, decision logs and dated posts describe another time on purpose; they are read with looser rules. Findings come in three levels and the lowest one, notes, is hidden unless you ask.
4. **It only reads.** It never edits a doc or a file of code, never runs code from the repo it checks, and never opens files that usually hold secrets.

## What it checks

| A doc says | Checked against | Finding ids |
|---|---|---|
| a path, in backticks or as a link | the files in the tree, and every move and delete in history | `path-moved`, `path-gone`, `path-removed-now`, `path-typo`, `link-broken`, `link-case` |
| a link to a heading, `guide.md#install` | the headings and ids of that page, and the commit that removed one | `anchor-missing` |
| a command in a code block | script files, `package.json` scripts, Makefile targets | `command-missing`, `npm-script-missing`, `make-target-missing` |
| an option or subcommand of a script in the repo | the source of that script, then and now | `flag-removed`, `flag-missing`, `subcommand-missing` |
| a function, class or constant | an index of the names the code defines, and history | `symbol-gone`, `symbol-removed-now` |
| a decision id such as `D01` or `ADR-7` | the decision log or ADR folder: unknown, replaced, partly replaced | `decision-unknown`, `decision-superseded`, `decision-amended` |
| a version or a pinned dependency | the package files | `version-mismatch`, `dep-mismatch` |
| the same sentence in two docs, with different numbers | each other | `copies-diverged` |
| a rule, with a pattern beside it (see below) | the code | `rule-violation` |
| a table | its own shape | `table-shape`, `table-orphan` |

Notes, shown with `--severity info`: `stale-risk` (the code a doc describes changed after the doc), `link-unverified` and `anchor-unverified` (an address only the built site can confirm), `foreign-links` (a doc copied in from another project).

### A rule in words that the machine enforces

Put a pattern under the sentence that states the rule. The doc stays readable, and the rule stops being a wish:

<!-- mindmap: ignore-start -->
```markdown
Never call `os.kill(pid, 0)`: on Windows it sends Ctrl+C to the whole console.
<!-- mindmap: forbid /os\.kill\([^,]+,\s*0\)/ in **/*.py -->
```

```text
src/app/watch.py
  5:1  error  breaks the rule in AGENTS.md:4: "Never call os.kill(pid, 0): on Windows it sends Ctrl+C to the whole console."  [rule-violation]
```
<!-- mindmap: ignore-end -->

## For coding agents

An agent trusts its instruction files. Mind Map gives it three ways to stop trusting stale ones.

**A hook for Claude Code.** Right after the agent edits code, the hook tells it which doc lines still mention what the edit removed. Add this to `.claude/settings.json` yourself; Mind Map never installs it.

```json
{
  "hooks": {
    "PostToolUse": [{"matcher": "Edit|Write|MultiEdit",
                     "hooks": [{"type": "command", "command": "mindmap hook", "timeout": 30}]}],
    "SessionStart": [{"hooks": [{"type": "command", "command": "mindmap hook", "timeout": 30}]}]
  }
}
```

What the agent then sees after it renames a function, and what it sees when a session starts:

<!-- mindmap: ignore-start -->
```text
Mind Map: your change to src/notes/cli.py removed things that docs still mention. Update these lines (or say why not):
- AGENTS.md:4 `load_config` (name) was removed from `src/notes/cli.py` and no code has it any more
- README.md:18 `load_config` (name) was removed from `src/notes/cli.py` and no code has it any more
```

```text
Mind Map: 3 line(s) in the instruction files you just read are out of date; trust the code over them:
- AGENTS.md:3 `build_index()` is gone from the code; it existed when this line was written (2026-03-02) (maybe renamed to `rebuild_index` (src/notes/cli.py))
- AGENTS.md:4 `load_config()` is gone from the code; it existed when this line was written (2026-03-02)
- AGENTS.md:6 decision D01 was replaced by D03; check this line still holds
```
<!-- mindmap: ignore-end -->

The hook never blocks an edit. On any problem it prints nothing and exits 0.

**An MCP server.** `mindmap mcp` speaks the Model Context Protocol on stdio, in both the 2024 to 2025 form (`initialize`) and the 2026-07-28 form (`server/discover`). It is read-only.

```bash
claude mcp add mind-map -- mindmap mcp
```

| Tool | What the agent gets |
|---|---|
| `check` | doc lines that disagree with the code or the history, with proof |
| `impact` | after a code change: doc lines that still mention what the change removed |
| `claims` | every checkable claim in one doc and whether it holds |
| `context` | the doc sections that matter for a task, inside a token budget, stale lines marked |
| `cost` | tokens of the instruction files loaded every session, and how many of their lines are stale |

Three prompts come with it: `fix-drift` (fix what `check` found), `prose-to-rules` (propose `forbid` lines for rules written in words), `critic` (a blunt review of whether the project should exist).

**The same from a terminal.**

<!-- mindmap: ignore-start -->
```text
$ mindmap impact
AGENTS.md:4  `load_config` (name) was removed from `src/notes/cli.py` and no code has it any more
README.md:18  `load_config` (name) was removed from `src/notes/cli.py` and no code has it any more

$ mindmap cost .
 tokens  stale  file  (loaded)
     76      3  AGENTS.md  (every session)
~76 tokens are read at the start of every session; 3 stale lines in total.

$ mindmap context "change how the index is stored" --budget 400
## README.md:16-20 · How it works
## How it works

`build_index()` scans the folder once and `load_config()` reads `notes.toml`.
  [stale] `build_index()` is gone from the code; it existed when this line was written (2026-03-02)
  [stale] `load_config()` is gone from the code; it existed when this line was written (2026-03-02)
The index format follows D01. Search is case-insensitive (D02).
  [stale] decision D01 was replaced by D03; check this line still holds
...
{"tokens": 270, "sections": 6}
```
<!-- mindmap: ignore-end -->

## In CI

A GitHub Action that writes a summary on the run page and marks the lines in the pull request:

```yaml
jobs:
  docs:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0    # the whole history: Mind Map reads it
      - uses: Elainabaka/meinya-mind-map@v0.1.0
        with:
          fail-on: error
```

As a pre-commit hook:

```yaml
repos:
  - repo: https://github.com/Elainabaka/meinya-mind-map
    rev: v0.1.0
    hooks:
      - id: mindmap
```

For code scanning, `mindmap check . --format sarif --out mindmap.sarif`. Other formats: `json`, `github`, `md`.

## Fitting it to a repo

| Need | How |
|---|---|
| Start on an old repo without fixing everything first | `mindmap check . --update-baseline` records today's findings in `.mindmap-baseline.json`; from then on `--baseline .mindmap-baseline.json` shows only new ones |
| Show more, or fail earlier | `--severity info` shows notes; `--fail-on warning` makes warnings fail the run |
| Skip a folder | `--exclude "vendor/**"`, or `exclude = ["vendor/**"]` in `.mindmap.toml` |
| Silence one line, a block or a file | `<!-- mindmap: ignore -->` at the end of the line, `ignore-start` and `ignore-end` around a block, `ignore-file` anywhere in the doc |
| Tell it how to read a doc | `live`, `plans`, `history` lists of globs in `.mindmap.toml` (or under `[tool.mindmap]` in `pyproject.toml`), or `<!-- mindmap: history -->` (or `plan`, `live`) anywhere in the doc, which wins over both. A history doc (an old prompt, a pasted chat) keeps only its decision ids checked |
| Messages in Vietnamese | `--lang vi`, or `lang = "vi"` in the config |

## Measured, not promised

Twelve public repos, each at the commit named, each with its full history. Seconds are for the first run on a repo, the one that builds the code index: on Windows 11, then on Ubuntu under WSL on the same desktop PC. A later run reuses the index while no code file changes (vite: 4.1 s on Windows, 3.4 s on Linux).

| Repo at commit | Commits read | Docs | Claims | Errors | Warnings | Notes | Seconds |
|---|---|---|---|---|---|---|---|
| modelcontextprotocol/python-sdk `91941ed` | 1,093 | 771 | 31,926 | 0 | 0 | 442 | 11.6 / 5.6 |
| gohugoio/hugoDocs `1f72674` | 15,484 | 1,013 | 7,625 | 1 | 0 | 438 | 16.3 / 8.5 |
| withastro/starlight `531af7d` | 3,805 | 385 | 5,085 | 0 | 0 | 189 | 7.0 / 3.4 |
| anthropics/anthropic-sdk-python `50b78d1` | 1,516 | 16 | 2,497 | 0 | 0 | 5 | 5.0 / 2.2 |
| vitejs/vite `b6c20f6` | 9,760 | 84 | 1,713 | 0 | 18 | 53 | 8.8 / 4.7 |
| fastapi/typer `b15210b` | 1,781 | 80 | 610 | 2 | 0 | 5 | 2.8 / 0.9 |
| encode/starlette `0a15da3` | 1,764 | 33 | 555 | 0 | 0 | 20 | 1.3 / 0.4 |
| tj/commander.js `ba6d13d` | 1,517 | 15 | 340 | 0 | 0 | 4 | 1.5 / 0.4 |
| junegunn/fzf `33a3456` | 3,749 | 9 | 277 | 0 | 0 | 3 | 1.3 / 0.5 |
| encode/httpx `b5addb6` | 1,523 | 29 | 232 | 0 | 3 | 11 | 1.6 / 0.4 |
| BurntSushi/ripgrep `3fce3b5` | 2,287 | 23 | 167 | 0 | 0 | 12 | 1.2 / 0.5 |
| expressjs/express `9efc29e` | 6,177 | 4 | 47 | 0 | 0 | 1 | 1.0 / 0.3 |

That is 2,462 docs and 51,074 claims. 24 findings came out as errors or warnings, and each was read by hand: 23 are real, 1 is a false alarm.

- **vite, 18 real.** The posts that announced Vite 5 and Vite 6 link to sections of the migration guide. Later rewrites of the guide removed those sections. Each warning names the commit that did it.
- **httpx, 3 real.** Links to headings that have since been renamed.
- **typer, 2 real.** The README links to `tutorial/install.md`, which only resolves from inside `docs/`.
- **hugoDocs, 1 false alarm.** A page tells readers to put a `package.hugo.json` in their own module. The docs repo had a file by that name when the line was written, and deleted it later. Every piece of the proof is true; the line was simply about someone else's file.

A second experiment: rename one class in starlette (`CORSMiddleware` to `CorsMiddleware`) and run again. Two warnings appear, on the two doc lines that still use the old name, each with the commit and the new name as a suggestion.

**The first runs were not this clean.** The Python SDK of MCP gave 435 false alarms the first time. Three documentation sites gave 294 findings, about 20 of them real. Five repos it had never seen gave 9 findings: 2 real, 6 false, 1 arguable. Reading the full history of hugoDocs and vite, where the first clones were shallow, added 20 findings, every one of them false. Every false alarm was traced to a general gap (24 so far: addresses written for a built site, the many ways sites name a heading, a history with two lines of commits side by side, and so on) and closed with a test. No repo has a rule of its own. Expect a few false alarms on a repo shaped unlike these twelve; the baseline and the ignore comments are there for that.

**Same input, same report.** The JSON report for all twelve repos is identical on Windows (a machine set to UTC+7) and on Linux (UTC), down to each message and each date, and does not change with Python's hash seed.

## Limits

- It reads Markdown (`.md`, `.markdown`, `.mdx`), not reStructuredText or AsciiDoc.
- It checks what a machine can prove. Whether a paragraph still describes the behaviour well is a judgement it leaves to you; `stale-risk` only points at where to look.
- Docs of a product that talk about the reader's project can name a file the repo itself once had. That is the false alarm above.
- A site generator makes pages and ids that are not in the repo. Mind Map follows the common conventions and turns the rest into notes, not warnings.
- Names in code are found with a text index and patterns for definitions in more than thirty languages, not with a parser for each. A definition written in an unusual way is missed, and then Mind Map stays quiet.
- A shallow clone has less history, so it gives fewer findings (never more). In CI, fetch the full history.
- If git does not answer in time (each call has a hard time limit, and after three timeouts in one run it stops asking), the report says how many questions went unanswered: a `!` line, `stats.git_unanswered` in JSON, a line on stderr. Such a report may miss findings: run it again. The exit code still follows the findings only.
- Status: 0.1.0, alpha. It needs Python 3.11 or newer and git. Tested on Windows (Python 3.11, 3.12, 3.13) and Linux (Python 3.14): 146 tests, 89 of them for Mind Map (on Linux the 24 tests of the desktop app were skipped: no pywebview there). Not tested yet: macOS.

## Safety

- It writes only what you ask for (`--out`, `--update-baseline`) and one cache file of the code index in your user cache folder. `MINDMAP_CACHE_DIR` moves the cache.
- No network, no model, no telemetry.
- It never runs or imports code from the repo it checks. It reads text and asks git.
- It skips files that usually hold secrets: `.env` files, `.npmrc`, `.pypirc`, `.netrc`, SSH keys, `*.pem`, `*.key`, cookie files, and any path with `secret` in it.
- On a repo you do not trust, use the installed `mindmap` command or `python -I run_mindmap.py`. Do not run `python -m mindmap` from inside that repo: Python would put the repo's folder first on its import path.

## Also in this repo: Meinya MD to HTML

Mind Map grew out of a small tool that turns Markdown into a single HTML page you can open offline, and that tool still lives here.

![The desktop app: sources, preview, options](docs/01-giao-dien.png)

- **Command line**, standard library only: `python md_to_html.py NOTES.md` writes `NOTES.html` next to it; give it a folder to convert every file in it. Table of contents, light and dark mode, copy buttons on code, GitHub-style tables and callouts.
- **Desktop app for Windows 10 and 11**: double-click `run.bat`. The first run creates `.venv` and installs the pinned `pywebview` 6.2.1 (about 3 MB, needs the Edge WebView2 runtime). Drop a `.md` file on the window.
- Not supported: footnotes, Mermaid, KaTeX, syntax colouring by language. It escapes Markdown content, but it is not a filter for content you do not trust.

Details, the full option list and the licences of the libraries `run.bat` installs are in the [Vietnamese README](README.vi.md).

## Tests

```bash
python -m pip install pytest
python -m pytest tests -q
```

The two test files of the desktop window are skipped when `pywebview` is not installed. Everything else runs anywhere.

## Licence

The code is under the MIT licence; see the `LICENSE` file. The name Meinya, the character art and the name Elainabaka are not part of that licence.

Made by [Elainabaka](https://elainabaka.com).
