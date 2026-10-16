# sudoku-kit

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (`caneff/sudoku-kit`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default six canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## Coding standards

`CODING_STANDARDS.md` holds the conventions no gate checks; read it before writing code.

## End-to-end seam

`bash tests/all.sh` is the seam: one suite per command, stopping at the first
failure; `--list` prints the suites. `just check` calls it, so CI runs it too.
`--changed <base>` is accepted and runs the whole seam, since the full run takes seconds. There is no
live layer.
