"""The rules file: the one puzzle format the solve guide's checks, step search
and renderer read (spec #106).

A rules file is a JSON object:

- `size`: n for an n x n grid, digits 1..n; every row and column is a house.
- `regions`: the boxes, each a list of [row, column] cells counted from 0.
- `givens`: a list of `{"cell": [row, column], "digit": d}`.
- `solution`: optional, n rows of n digits.
- `clues`: a list of clues, each `{"id", "rule", "cells", "values"}`, `rule` a
  key of `clue_rules.RULES` and `id` stable and unique.
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


def _name(cell):
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def _cells(rules):
    n = rules["size"]
    return [(r, c) for r in range(n) for c in range(n)]


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


def validate(rules):
    """Raise ValueError naming the first thing wrong with `rules`."""
    missing = [key for key in REQUIRED if key not in rules]
    if missing:
        raise ValueError(f"the rules file has no {', '.join(missing)}")
    n = rules["size"]
    if not isinstance(n, int) or n < 1:
        raise ValueError(f"the rules file's size is {n!r}, not a positive integer")
    for k, region in enumerate(rules["regions"], 1):
        for cell in region:
            _on_board(rules, cell, f"region {k}")
    for given in rules["givens"]:
        _on_board(rules, given["cell"], f"given {given!r}")
        if given["digit"] not in range(1, n + 1):
            raise ValueError(f"given {given!r} is not a digit 1..{n}")
    solution = rules.get("solution")
    if solution is not None and (
        len(solution) != n
        or any(
            len(row) != n or not set(row) <= set(range(1, n + 1)) for row in solution
        )
    ):
        raise ValueError(f"the solution is not {n} rows of {n} digits 1..{n}")
    seen = set(house_names(rules))
    for clue in rules["clues"]:
        if clue.get("id") in seen:
            raise ValueError(f"clue id {clue.get('id')!r} is used twice")
        seen.add(clue["id"])
        for cell in clue["cells"]:
            _on_board(rules, cell, f"clue {clue['id']!r}")
        clue_rules.poster(clue)


def load(path):
    """The rules file at `path`, validated."""
    try:
        rules = json.loads(Path(path).read_text())
    except ValueError as e:
        raise ValueError(f"{path} is not JSON: {e}") from e
    if not isinstance(rules, dict):
        raise ValueError(f"{path} holds a {type(rules).__name__}, not a rules file")
    try:
        validate(rules)
    except (KeyError, TypeError) as e:
        raise ValueError(f"{path} is not a rules file: missing or bad {e}") from e
    return rules


def house_names(rules):
    """{name: cells} for every row, column and region."""
    n = rules["size"]
    houses = {f"row {r + 1}": [(r, c) for c in range(n)] for r in range(n)}
    houses |= {f"column {c + 1}": [(r, c) for r in range(n)] for c in range(n)}
    for k, region in enumerate(rules["regions"], 1):
        houses[f"region {k}"] = [tuple(cell) for cell in region]
    return houses


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
    x = {cell: m.NewIntVar(1, n, _name(cell)) for cell in _cells(rules)}
    for poster in named.values():
        poster.post(m, {cell: x[cell] for cell in poster.cells})
    return m, x


def _check_unique(rules, named, time_limit):
    m, x = _model(rules, named)
    for given in rules["givens"]:
        m.Add(x[tuple(given["cell"])] == given["digit"])
    result = check_uniqueness(m, x, time_limit=time_limit)
    return {"status": result.status, "passed": result.unique}


def _fits(poster, solution, time_limit):
    """True when the poster's constraint holds on its cells' solution digits."""
    m = cp_model.CpModel()
    x = {cell: m.NewConstant(solution[cell[0]][cell[1]]) for cell in poster.cells}
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
    failing = [
        f"given {_name(given['cell'])}"
        for given in rules["givens"]
        if solution[given["cell"][0]][given["cell"][1]] != given["digit"]
    ]
    failing += [
        name
        for name, poster in named.items()
        if not _fits(poster, solution, time_limit)
    ]
    return {"passed": not failing, "failing": failing}


def check(rules, time_limit=60.0):
    """The two checks on `rules`:

    - `unique`: `status` from `uniqueness.check_uniqueness` over every house,
      clue and given; `passed` only on "unique", never on a timeout.
    - `solution_fits`: `failing` names each given, house and clue the stored
      solution breaks; `passed` is None when there is no stored solution.
    """
    named = registry(rules)
    return {
        "unique": _check_unique(rules, named, time_limit),
        "solution_fits": _check_solution(rules, named, time_limit),
    }


def passed(checks):
    """True unless a check that ran failed."""
    return checks["unique"]["passed"] and checks["solution_fits"]["passed"] is not False
