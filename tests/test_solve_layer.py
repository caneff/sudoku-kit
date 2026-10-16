"""Spec #11 end to end: an invalid model is never a verdict, one factory sets
the thread count, and a board is described by its houses.

Blind to: outside callers. sudokumaker-custom-constraints (pinned at v0.1.0,
12 sudoku_model call sites in 10 files) and grid-hunts run none of their code
here, so the changed sudoku_model signature and the new ValueError on
MODEL_INVALID reach them only when they bump their tag.
"""

import pytest
from ortools.sat.python import cp_model

from sudoku_kit.cpsat import (
    boxes,
    has_second_solution,
    solve_unique,
    solver,
    sudoku_model,
)
from sudoku_kit.uniqueness import check_uniqueness


def test_the_solve_layer_end_to_end():
    broken = cp_model.CpModel()
    x = {"x": broken.NewIntVar(5, 1, "x")}
    with pytest.raises(ValueError, match='name: "x"'):
        solve_unique(broken, x, 10)
    with pytest.raises(ValueError, match='name: "x"'):
        has_second_solution(broken, x, {"x": 1}, 10)
    assert check_uniqueness(broken, x.values()).status == "invalid"

    for reproducible in (True, False):
        assert (
            solver(10, reproducible=reproducible, workers=3).parameters.num_workers == 3
        )

    with pytest.raises(ValueError, match="2x2 boxes do not hold 6"):
        boxes(6, 2, 2)
    m, x = sudoku_model(4, boxes(4, 2, 2))
    for cell, digit in {(0, 0): 1, (0, 1): 2, (1, 2): 1, (2, 1): 1}.items():
        m.Add(x[cell] == digit)
    first, unique = solve_unique(m, x, 10)
    assert first is not None and not unique

    m, x = sudoku_model(3, ())
    result = check_uniqueness(m, x.values())
    assert result.status == "not_unique" and result.first != result.second
