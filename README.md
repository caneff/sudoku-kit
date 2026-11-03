# sudoku-kit

A small library of sudoku tooling, written to be shared by
[sudokumaker-custom-constraints](https://github.com/caneff/sudokumaker-custom-constraints)
and grid-hunts. Neither imports the step prover.

- `sudoku_kit.cpsat`: the CP-SAT calls every generator and uniqueness proof
  makes. `solver`, `forbid`, `has_second_solution`, `boxes`, `sudoku_model`,
  `solve_unique` and `check_valid`.
- `sudoku_kit.link_codec`: the SudokuMaker link codec. `decode_puzzle`,
  `encode_link`, `read_link` and `shorten_link`. `decode_puzzle` reads both payload formats
  the app writes (`D`, base64url of deflate-raw, and the older lz-string `N`);
  `encode_link` writes `N` and refuses a document whose link does not decode
  back to it. `read_link` also resolves a short link
  (`https://sudokumaker.app/p/<id>`) with one GET of the app's API. `shorten_link` mints one from a full link
  (or a file holding one) with one POST and checks it resolves back to the
  payload sent; `uv run --directory <repo> python -m sudoku_kit.link_codec
  shorten <link-or-file>...` prints one per source.
- `sudoku_kit.step_prover`: `prove`, which reports whether a step's claim
  (`Chain`, `Place` or `Either`) is `proved` from its named constraints,
  `refuted` with a witness, `contradictory` or `timeout`. `irreducible`
  shrinks a proved step to an irreducible set of constraints, and
  `propagation` checks whether propagation alone proves it. `house` and
  `table` build the constraints; a caller registers its own with `Poster`.
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
