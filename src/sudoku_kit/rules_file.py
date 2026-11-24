"""The rules file: the one puzzle format the solve guide's checks, step search
and renderer read (spec #106).

A rules file is a JSON object:

- `size`: n for an n x n grid, digits 1..n; every row and column is a house.
- `regions`: the boxes, each a list of [row, column] cells counted from 0.
- `givens`: a list of `{"cell": [row, column], "digit": d}`.
- `holes`: optional, the [row, column] cells of the n x n grid that are not
  part of the puzzle (a board that is not a full square, such as a diamond).
  A hole is no variable, sits in no house and carries no clue or given.
- `solution`: optional, n rows of n digits, null at each hole.
- `clues`: a list of clues, each `{"id", "rule", "cells", "values"}`, `rule` a
  key of `clue_rules.RULES` and `id` stable and unique. A clue's cells may
  include outside cells, one step off the grid ([row, -1] or [row, size], and
  the same for columns): a clue digit the solver writes beside the grid, a
  variable with digits 1..n that no row, column or region holds.
- `solution_outside`: optional, `{"cell": [row, column], "digit": d}` for each
  outside cell a clue uses, read when `solution` is. Stored apart from
  `solution`, which stays n rows of n digits.
- `title` and `rules_text`: optional, the source's title and rules text.

`validate` refuses a malformed one, naming what is wrong. `registry` gives
each house and clue its named constraint for the step prover. `check` runs the
two checks: exactly one solution, and the stored solution fits every named
constraint.
"""

import json
from pathlib import Path

from ortools.sat.python import cp_model

from sudoku_kit import clue_rules
from sudoku_kit.cpsat import SOLVED, UNKNOWN, check_valid, solver
from sudoku_kit.step_prover import house
from sudoku_kit.uniqueness import check_uniqueness

REQUIRED = ("size", "regions", "givens", "clues")


def cell_name(cell):
    """A cell as r<row>c<column>, counted from 1."""
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def _numbers(counts):
    """1-based numbers run together, comma-separated once one has two digits."""
    words = [str(n + 1) for n in sorted(counts)]
    return ",".join(words) if any(len(w) > 1 for w in words) else "".join(words)


def cell_list(cells):
    """Cells in words, in the standard notation: a block of rows by columns is
    one name (r12c34), a single cell stays r1c5. Rows holding the same columns
    form one block; the blocks come in reading order of their first cell."""
    columns = {}
    for r, c in sorted(set(map(tuple, cells))):
        columns.setdefault(r, set()).add(c)
    blocks = {}
    for r, cols in columns.items():
        blocks.setdefault(frozenset(cols), []).append(r)
    return ", ".join(
        f"r{_numbers(rows)}c{_numbers(cols)}"
        for cols, rows in sorted(blocks.items(), key=lambda b: (b[1][0], sorted(b[0])))
    )


def witness_words(witness):
    """{cell: digit} in words: the cells taking one digit share a block name
    (r12c34=3, one per block), the digits in order of their first cell."""
    by_digit = {}
    for cell, digit in witness.items():
        by_digit.setdefault(digit, []).append(cell)
    return " ".join(
        f"{block}={d}"
        for d, cells in by_digit.items()
        for block in cell_list(cells).split(", ")
    )


def holes(rules):
    """The grid cells that are not part of the puzzle, as tuples."""
    return {tuple(cell) for cell in rules.get("holes") or []}


def _outside_cells(rules):
    """The outside cells the clues name, in order of first use."""
    n = rules["size"]
    on_grid = {(r, c) for r in range(n) for c in range(n)}
    named = (tuple(cell) for clue in rules["clues"] for cell in clue["cells"])
    return list(dict.fromkeys(cell for cell in named if cell not in on_grid))


def cells(rules):
    """Every cell that is a solver variable: the grid's but its holes, row by
    row, then the outside cells."""
    n, off = rules["size"], holes(rules)
    on_grid = [(r, c) for r in range(n) for c in range(n) if (r, c) not in off]
    return on_grid + _outside_cells(rules)


def _on_board(rules, cell, what):
    n = rules["size"]
    if not (
        isinstance(cell, list | tuple)
        and len(cell) == 2
        and all(isinstance(i, int) and 0 <= i < n for i in cell)
    ):
        raise ValueError(
            f"{what} names cell {cell!r}, which is not on the {n}x{n} grid"
        )


def _is_outside(rules, cell):
    """True for a cell one step off the grid, beside a row's or a column's end."""
    n = rules["size"]
    if not (
        isinstance(cell, list | tuple)
        and len(cell) == 2
        and all(isinstance(i, int) for i in cell)
    ):
        return False
    row, column = cell
    return (row in (-1, n) and 0 <= column < n) or (column in (-1, n) and 0 <= row < n)


def _in_clue(rules, cell, what):
    if not _is_outside(rules, cell):
        _on_board(rules, cell, what)


def validate(rules):
    """Raise ValueError naming the first thing wrong with `rules`."""
    missing = [key for key in REQUIRED if key not in rules]
    if missing:
        raise ValueError(f"the rules file has no {', '.join(missing)}")
    n = rules["size"]
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"the rules file's size is {n!r}, not a positive integer")
    for cell in rules.get("holes") or []:
        _on_board(rules, cell, "holes")
    off = holes(rules)
    for k, region in enumerate(rules["regions"], 1):
        for cell in region:
            _on_board(rules, cell, f"region {k}")
            if tuple(cell) in off:
                raise ValueError(f"region {k} names cell {cell!r}, a hole")
    for given in rules["givens"]:
        _on_board(rules, given["cell"], f"given {given!r}")
        if tuple(given["cell"]) in off:
            raise ValueError(f"given {given!r} is on a hole")
        if given["digit"] not in range(1, n + 1):
            raise ValueError(f"given {given!r} is not a digit 1..{n}")
    solution = rules.get("solution")
    if solution is not None and not _solution_fits_grid(rules, solution):
        raise ValueError(
            f"the solution is not {n} rows of {n} digits 1..{n}, null at the holes"
        )
    seen = set(house_names(rules))
    for clue in rules["clues"]:
        if clue.get("id") in seen:
            raise ValueError(f"clue id {clue.get('id')!r} is used twice")
        seen.add(clue["id"])
        for cell in clue["cells"]:
            _in_clue(rules, cell, f"clue {clue['id']!r}")
            if tuple(cell) in off:
                raise ValueError(f"clue {clue['id']!r} names cell {cell!r}, a hole")
        clue_rules.poster(clue)
    _validate_outside_solution(rules)


def _solution_fits_grid(rules, solution):
    n, off = rules["size"], holes(rules)
    return len(solution) == n and all(
        len(row) == n
        and all(
            digit is None if (r, c) in off else digit in range(1, n + 1)
            for c, digit in enumerate(row)
        )
        for r, row in enumerate(solution)
    )


def _validate_outside_solution(rules):
    n = rules["size"]
    stored = rules.get("solution_outside") or []
    for entry in stored:
        if not _is_outside(rules, entry["cell"]):
            raise ValueError(
                f"solution_outside names cell {entry['cell']!r}, which is not "
                f"beside the {n}x{n} grid"
            )
        if entry["digit"] not in range(1, n + 1):
            raise ValueError(f"solution_outside {entry!r} is not a digit 1..{n}")
    if rules.get("solution") is not None:
        held = {tuple(entry["cell"]) for entry in stored}
        missing = [c for c in _outside_cells(rules) if c not in held]
        if missing:
            raise ValueError(
                f"the rules file has a solution but no solution_outside for "
                f"{[list(c) for c in missing]}"
            )


def read_json(path):
    """The JSON file at `path`, parsed; a file that cannot be read or is not
    JSON is a ValueError naming it."""
    try:
        return json.loads(Path(path).read_text())
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e.strerror}") from e
    except ValueError as e:
        raise ValueError(f"{path} is not JSON: {e}") from e


def load(path):
    """The rules file at `path`, validated."""
    rules = read_json(path)
    if not isinstance(rules, dict):
        raise ValueError(f"{path} holds a {type(rules).__name__}, not a rules file")
    try:
        validate(rules)
    except (KeyError, TypeError) as e:
        raise ValueError(f"{path} is not a rules file: missing or bad {e}") from e
    return rules


def house_names(rules):
    """{name: cells} for every row, column and region, holes left out."""
    n, off = rules["size"], holes(rules)
    houses = {
        f"row {r + 1}": [(r, c) for c in range(n) if (r, c) not in off]
        for r in range(n)
    }
    houses |= {
        f"column {c + 1}": [(r, c) for r in range(n) if (r, c) not in off]
        for c in range(n)
    }
    for k, region in enumerate(rules["regions"], 1):
        houses[f"region {k}"] = [tuple(cell) for cell in region]
    return {name: cells for name, cells in houses.items() if cells}


def registry(rules):
    """{name: Poster} for every house and clue, the step prover's registry.
    Givens are candidates, not named constraints, so they are not in it."""
    named = {name: house(cells) for name, cells in house_names(rules).items()}
    for clue in rules["clues"]:
        named[clue["id"]] = clue_rules.poster(clue)
    return named


def _model(rules, named):
    m = cp_model.CpModel()
    n = rules["size"]
    x = {cell: m.NewIntVar(1, n, cell_name(cell)) for cell in cells(rules)}
    for poster in named.values():
        poster.post(m, {cell: x[cell] for cell in poster.cells})
    return m, x


def _check_unique(rules, named, time_limit):
    m, x = _model(rules, named)
    for given in rules["givens"]:
        m.Add(x[tuple(given["cell"])] == given["digit"])
    result = check_uniqueness(m, x, time_limit=time_limit)
    if result.status == "invalid":
        raise ValueError("CP-SAT rejected the rules file's model as invalid")
    # A timeout is no verdict: passed is null, never false.
    passed = None if result.status == "timeout" else result.unique
    return {"status": result.status, "passed": passed}


def _fits(poster, digit_at, time_limit):
    """True when the poster's constraint holds on its cells' solution digits."""
    m = cp_model.CpModel()
    x = {cell: m.NewConstant(digit_at[cell]) for cell in poster.cells}
    poster.post(m, x)
    status = solver(time_limit).Solve(m)
    check_valid(status, m)
    if status == UNKNOWN:
        raise TimeoutError(f"checking a constraint on {list(x)} hit {time_limit}s")
    return status in SOLVED


def _check_solution(rules, named, time_limit):
    solution = rules.get("solution")
    if solution is None:
        return {"passed": None, "failing": []}
    digit_at = {
        (r, c): digit
        for r, row in enumerate(solution)
        for c, digit in enumerate(row)
        if digit is not None
    }
    digit_at |= {
        tuple(entry["cell"]): entry["digit"]
        for entry in rules.get("solution_outside") or []
    }
    failing = [
        f"given {cell_name(given['cell'])}"
        for given in rules["givens"]
        if solution[given["cell"][0]][given["cell"][1]] != given["digit"]
    ]
    failing += [
        name
        for name, poster in named.items()
        if not _fits(poster, digit_at, time_limit)
    ]
    return {"passed": not failing, "failing": failing}


def check(rules, time_limit=60.0):
    """The two checks on `rules`:

    - `unique`: `status` from `uniqueness.check_uniqueness` over every house,
      clue and given; `passed` true only on "unique" and null on "timeout",
      which is no verdict.
    - `solution_fits`: `failing` names each given, house and clue the stored
      solution breaks; `passed` is None when there is no stored solution.

    Raises ValueError when CP-SAT rejects the model, and TimeoutError when
    checking the stored solution against a constraint hits `time_limit`.
    """
    named = registry(rules)
    return {
        "unique": _check_unique(rules, named, time_limit),
        "solution_fits": _check_solution(rules, named, time_limit),
    }


def passed(checks):
    """True when the puzzle is unique and the stored solution, if any, fits."""
    return bool(checks["unique"]["passed"]) and (
        checks["solution_fits"]["passed"] is not False
    )
