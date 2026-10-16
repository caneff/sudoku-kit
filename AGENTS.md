# sudoku-kit

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (`caneff/sudoku-kit`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default six canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## End-to-end seam

`bash tests/all.sh` is the seam: ruff, the format check, `uv lock --check` and
pytest, one suite per command, stopping at the first failure. `just check`
calls it, so CI runs it too. `--list` prints the suites; `--changed <base>` is
accepted and runs the whole seam, since the full run takes seconds. There is no
live layer.
