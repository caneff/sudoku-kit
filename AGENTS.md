# sudoku-kit

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (`caneff/sudoku-kit`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default six canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Solution paths (always on)

- **Never publish a solution path.** This repo is public, so a solve path for
  a puzzle never goes into a commit, PR, issue, gist or artifact, here or
  anywhere else. Work it in a session scratch file outside this repo and open
  it for Chris. (Chris, 2026-10-13: "Never ever publish solution paths"; the
  ruling covers every repo, agent-skills#1627.)

## Coding standards

`CODING_STANDARDS.md` holds the conventions no gate checks; read it before writing code.

## End-to-end seam

`bash tests/all.sh` is the seam: one suite per command, stopping at the first
failure; `--list` prints the suites. `just check` calls it, so CI runs it too.
`--changed <base>` is accepted and runs the whole seam, since the full run takes seconds. There is no
live layer.

- **Seam**: `bash tests/all.sh`: ruff check, ruff format, the uv lock check
  and pytest over `tests/`. The print test needs Chromium: run
  `uv run playwright install chromium` once per Playwright version (CI caches it)
- **Blind to**: the consumers. grid-hunts and sudokumaker-custom-constraints
  both track main and each lock a commit in `uv.lock`, so a change here never
  runs against their code until one of them runs
  `uv lock --upgrade-package sudoku-kit`. This repo cuts no more release tags
  (Chris, 2026-11-03).
