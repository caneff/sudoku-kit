# sudoku-kit

A small library of sudoku tooling, written to be shared by
[sudokumaker-custom-constraints](https://github.com/caneff/sudokumaker-custom-constraints)
and grid-hunts. At v0.1.0 neither installs it yet.

- `sudoku_kit.cpsat`: the CP-SAT calls every generator and uniqueness proof
  makes. `solver`, `forbid`, `has_second_solution`, `sudoku_model` and
  `solve_unique`.
- `sudoku_kit.link_codec`: the SudokuMaker link codec. `decode_puzzle`,
  `encode_link` and `read_link`. `encode_link` refuses a document whose link
  does not decode back to it.
- `sudoku_kit.uniqueness`: `check_uniqueness`, which reports `unique`,
  `not_unique`, `infeasible`, `timeout` or `invalid`.

A timeout is never read as a proof: `solve_unique` and `has_second_solution`
raise `TimeoutError`, and `check_uniqueness` reports `timeout`.

## Install

Pin a tag as a uv git source:

```toml
[project]
dependencies = ["sudoku-kit"]

[tool.uv.sources]
sudoku-kit = { git = "https://github.com/caneff/sudoku-kit", tag = "v0.1.0" }
```

## Develop

`just check` runs ruff and the tests. It needs only `uv`, and runs on Python
3.11, the floor, which `.python-version` pins. CI runs it on 3.11 and 3.14.
