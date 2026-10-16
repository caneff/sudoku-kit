# sudoku-kit

## Agent skills

### Issue tracker

Issues live in this repo's GitHub Issues (`caneff/sudoku-kit`), via the `gh` CLI. See `docs/agents/issue-tracker.md`.

### Triage labels

Default six canonical triage roles, each label string equal to its name. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` and `docs/adr/` at the repo root. See `docs/agents/domain.md`.

## End-to-end seam

`bash tests/all.sh` runs the whole gate (ruff, format check, pytest); it is the
same as `just check`. `--changed <ref>` is accepted and ignored: the suite is
small enough to run whole every time.
