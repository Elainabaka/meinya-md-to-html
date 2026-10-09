# Changelog

## 1.0.0 (2026-10-09)

**Facts by default, guesses on request.** On the command line, in the GitHub Action and in pre-commit, findings
that rest on a reading of the text (`symbol-gone`, `symbol-removed-now`, `path-missing`, `path-typo`,
`make-target-missing`, `subcommand-missing`, `decision-unknown`, `copies-diverged`, `version-mismatch`,
`dep-mismatch`) are now notes. `--all` (or `args: --all` in the Action) reports them as before. The summary line
says how many were turned into notes. MCP, the Claude Code hook and the desktop app still get every finding, with
the note asking the agent to read each one in context.

New since 0.1.0:

- `path-missing`: a path that is not in the tree and never was (agents make these up), checked without git too.
  A guess, so on the command line it needs `--all`.
- The hook also reads Codex `apply_patch` edits. A Mind Map tab in the desktop app (English and Vietnamese).
- Install with `uv tool install`; setup notes for Codex, Cursor and VS Code.

Fewer false alarms on repos built with coding agents, found on four sets of repos never seen before (numbers in
the README, including the first runs that missed the bar):

- Release notes waiting for a release (`.changeset/`, `.changes/`, `changelog.d/`, `newsfragments/`) are history.
- Dated records (`**Date**: 2026-07-11` under the title), numbered feature specs (`specs/001-login/`, spec-kit) and
  a status given in a table row (`| Status | Proposed |`) are read as records and plans.
- A folder of work items that git drops whenever no work is in progress (`openspec/changes/<id>/`) is not "gone".
- A file tree drawn from the folder that holds the clone (`mytool/` on top) is read from the repo root.
- Build folders a `.gitignore` names, folder-only ignore patterns, file names the code writes as strings, a
  library's package path in an import, `bun run` patterns.
- Names built by format strings (`f"time_{n}_{field}"`), names from a package that moved to its own repo and is
  now a dependency, version requirements (`v1.2.0+`, `3.11 or later`).
- Commands of another project: a skill that has the reader `git clone` another repo and `cd` into it.
- One finding per line when a table names a thing in two cells.

Fixes:

- A long string in the code (base64, a minified bundle) could make a run on a big repo run out of memory: strings
  over 400 characters are no longer read as paths.
- `git check-ignore` is no longer asked about a folder with a trailing slash: with a `.gitignore` saved with CRLF,
  the `\r` of a blank line matched every such path and hid real findings.
- A broken link now suggests the path as the link must be written from the doc (`../LICENSE.md`).

## 0.1.0 (2026-10-09)

First public release: `mindmap check` with git history as proof, MCP server, Claude Code hook, `impact`, `cost`,
`context`, GitHub Action, pre-commit hook, SARIF, HTML report, English and Vietnamese messages.
