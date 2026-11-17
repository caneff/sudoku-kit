# sudoku-kit

A small library of sudoku tooling, written to be shared by
[sudokumaker-custom-constraints](https://github.com/caneff/sudokumaker-custom-constraints)
and grid-hunts. Neither imports the step prover.

- `sudoku_kit.cpsat`: the CP-SAT calls every generator and uniqueness proof
  makes. `solver`, `forbid`, `has_second_solution`, `boxes`, `sudoku_model`,
  `solve_unique` and `check_valid`.
- `sudoku_kit.link_codec`: the SudokuMaker link codec. `decode_puzzle`,
  `encode_link`, `read_puzzle`, `read_link` and `shorten_link`. `read_puzzle` returns the
  document a file, link, bare payload or short link holds in one call (`read_link` then
  `decode_puzzle`). `decode_puzzle` reads both payload formats
  the app writes (`D`, base64url of deflate-raw, and the older lz-string `N`);
  `encode_link` writes `N` and refuses a document whose link does not decode
  back to it. `read_link` also resolves a short link
  (`https://sudokumaker.app/p/<id>`) with one GET of the app's API. `shorten_link` mints one from a full link
  (or a file holding one) with one POST and checks it resolves back to the
  payload sent; `uv run --directory <repo> python -m sudoku_kit.link_codec
  shorten <link-or-file>...` prints one per source.
- `sudoku_kit.sudokupad_codec`: the SudokuPad link reader. `read_puzzle` returns the puzzle
  JSON (cells, regions, cages, lines, arrows, overlays, underlays, metadata including any
  stored solution) that a SudokuPad link, short id, bare `scl`/`ctc`/`fpuzzles`/`fpuz` string
  or a file holding one stands for; `decode` also returns the form the link carried. A short
  id is resolved with one GET of `sudokupad.app/api/puzzle/<id>`. A plain `scl` body decodes
  in Python; the other forms run SudokuPad's own loader in `node` over a recording of the app
  (`$SUDOKUPAD_HAR`, else `~/.cache/sudokupad-art/sudokupad.har`), so they need `node` and
  that recording.
- `sudoku_kit.step_prover`: `prove`, which reports whether a step's claim
  (`Chain`, `Place` or `Either`) is `proved` from its named constraints,
  `refuted` with a witness, `contradictory` or `timeout`. `irreducible`
  shrinks a proved step to an irreducible set of constraints, and
  `propagation` checks whether propagation alone proves it. `house` and
  `table` build the constraints; a caller registers its own with `Poster`.
- `sudoku_kit.rules_file`: the rules file, the one puzzle format the solve
  guide reads: grid size, regions, givens, an optional solution and clues.
  `load`, `validate`, `registry` (every house and clue as a named constraint
  for the step prover) and `check` (exactly one solution; the stored solution
  fits every named constraint).
- `sudoku_kit.clue_rules`: per-clue rule functions, each turning one clue into
  a step prover `Poster`: `difference` and `ratio` (Kropki dots), ported from
  gridfind.
- `sudoku_kit.sudokupad_import`: `rules_file`, a SudokuPad puzzle with Kropki
  dots (orthogonal or diagonal) as a rules file, the rules text picking each
  colour's reading. It refuses any shape it does not read.
- `sudoku_kit.solve_guide`: the command line, `uv run solve-guide <input>
  <output directory>`: imports a SudokuPad link or reads a rules `.json`,
  then writes `rules.json` and `checks.json`; exit 1 when a check fails.
- `sudoku_kit.uniqueness`: `check_uniqueness`, which reports `unique`,
  `not_unique`, `infeasible`, `timeout` or `invalid`.

A timeout is never read as a proof: `solve_unique` and `has_second_solution`
raise `TimeoutError`, and `check_uniqueness` reports `timeout`.

## Install

Use `main` as a uv git source, with no tag. This repo cuts no release tags.

```toml
[project]
dependencies = ["sudoku-kit"]

[tool.uv.sources]
sudoku-kit = { git = "https://github.com/caneff/sudoku-kit" }
```

`uv.lock` holds the exact commit. `uv lock --upgrade-package sudoku-kit` moves
it to the latest `main`.

## Develop

`just check` runs ruff, the uv lock check and the tests. It needs only `uv`, and runs on Python
3.11, the floor, which `.python-version` pins. CI runs it on 3.11 and 3.14.
