"""The dot rule functions, ported from gridfind's `pair_difference_test.py` and
`pair_ratio_test.py` (gridfind c01723c). Each case posts clues through the
`Poster` a rule function returns and asks CP-SAT for a completion of a 9x9
board, with only the houses a case names.

gridfind's doubler and Schrodinger cases are not ported: those rule types need
board-wide state, which spec #106 leaves out.
"""

import pytest
from ortools.sat.python import cp_model

from sudoku_kit.clue_rules import poster


def _clue(rule, cells, k, clue_id="c"):
    return {
        "id": clue_id,
        "rule": rule,
        "cells": [list(c) for c in cells],
        "values": [k],
    }


def _difference(cells, k, clue_id="c"):
    return _clue("difference", cells, k, clue_id)


def _ratio(cells, k, clue_id="c"):
    return _clue("ratio", cells, k, clue_id)


def _solve(clues, givens=(), rows_distinct=False):
    """A completion of a 9x9 board under `clues` and `givens` ({cell: digit}),
    or None when there is none."""
    m = cp_model.CpModel()
    x = {(r, c): m.NewIntVar(1, 9, f"x{r}{c}") for r in range(9) for c in range(9)}
    if rows_distinct:
        for r in range(9):
            m.AddAllDifferent([x[r, c] for c in range(9)])
    for clue in clues:
        p = poster(clue)
        p.post(m, {cell: x[cell] for cell in p.cells})
    for cell, digit in dict(givens).items():
        m.Add(x[cell] == digit)
    s = cp_model.CpSolver()
    s.parameters.num_workers = 1
    status = s.Solve(m)
    assert status != cp_model.UNKNOWN
    if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        return None
    return {cell: s.Value(v) for cell, v in x.items()}


R1C1, R1C2, R3C3, R3C4 = (0, 0), (0, 1), (2, 2), (2, 3)


@pytest.mark.parametrize("rule", ["difference", "ratio"])
def test_a_clue_posts_onto_its_own_two_cells(rule):
    assert poster(_clue(rule, [R3C3, R3C4], 2)).cells == (R3C3, R3C4)


# pair-difference


def test_a_satisfiable_difference_pair_has_a_completion():
    grid = _solve([_difference([R1C1, R1C2], 3)], {R1C1: 5})
    assert grid is not None
    assert abs(grid[R1C1] - grid[R1C2]) == 3


def test_a_pair_that_cannot_meet_its_difference_has_no_completion():
    assert _solve([_difference([R1C1, R1C2], 3)], {R1C1: 1, R1C2: 1}) is None


def test_two_difference_clues_each_constrain_their_own_pair():
    grid = _solve(
        [_difference([R1C1, R1C2], 3, "a"), _difference([R3C3, R3C4], 5, "b")],
        {R1C1: 2, R3C3: 1},
    )
    assert grid is not None
    assert abs(grid[R1C1] - grid[R1C2]) == 3
    assert abs(grid[R3C3] - grid[R3C4]) == 5


def test_a_broken_second_difference_clue_breaks_the_whole_board():
    clues = [_difference([R1C1, R1C2], 3, "a"), _difference([R3C3, R3C4], 5, "b")]
    assert _solve(clues, {R3C3: 1, R3C4: 1}) is None


def test_the_difference_is_absolute_either_cell_may_hold_the_larger_digit():
    # The first cell holds the larger digit: a directed `a - b == k` would
    # refuse it; the absolute relation must not.
    grid = _solve([_difference([R1C1, R1C2], 4)], {R1C1: 9})
    assert grid is not None
    assert grid[R1C2] == 5


# pair-ratio


def test_a_satisfiable_ratio_pair_has_a_completion():
    grid = _solve([_ratio([R1C1, R1C2], 2)], {R1C1: 2})
    assert grid is not None
    assert grid[R1C2] in (1, 4)


def test_a_pair_that_cannot_meet_its_ratio_has_no_completion():
    assert _solve([_ratio([R1C1, R1C2], 2)], {R1C1: 5, R1C2: 5}) is None


def test_a_ratio_other_than_two_is_honored_at_its_value():
    grid = _solve([_ratio([R1C1, R1C2], 3)], {R1C1: 9})
    assert grid is not None
    assert grid[R1C2] == 3


def test_two_ratio_clues_each_constrain_their_own_pair():
    grid = _solve(
        [_ratio([R1C1, R1C2], 2, "a"), _ratio([R3C3, R3C4], 3, "b")],
        {R1C1: 1, R3C3: 1},
    )
    assert grid is not None
    assert grid[R1C2] == 2
    assert grid[R3C4] == 3


def test_the_ratio_is_undirected_either_cell_may_hold_the_larger_digit():
    # The first cell holds the smaller digit: a directed `a == k*b` would
    # refuse it; the undirected relation must not.
    grid = _solve([_ratio([R1C1, R1C2], 4)], {R1C1: 2})
    assert grid is not None
    assert grid[R1C2] == 8


def test_a_ratio_of_one_forces_equality_and_breaks_under_a_house():
    assert _solve([_ratio([R1C1, R1C2], 1)], rows_distinct=True) is None


def test_a_board_mixing_ratio_and_difference_clues_meets_both():
    grid = _solve(
        [_difference([R1C1, R1C2], 5, "a"), _ratio([R3C3, R3C4], 2, "b")],
        {R1C1: 1, R3C3: 3},
    )
    assert grid is not None
    assert grid[R1C2] == 6
    assert grid[R3C4] == 6


# malformed clues


@pytest.mark.parametrize("rule", ["difference", "ratio"])
@pytest.mark.parametrize("count", [1, 3], ids=["too few", "too many"])
def test_a_dot_clue_with_the_wrong_cell_count_is_refused_naming_the_clue(rule, count):
    clue = _clue(rule, [(0, c) for c in range(count)], 2, "dot-7")
    with pytest.raises(ValueError, match="dot-7"):
        poster(clue)


def test_a_clue_with_an_unknown_rule_is_refused_naming_the_rule():
    with pytest.raises(ValueError, match="sandwich"):
        poster(_clue("sandwich", [R1C1, R1C2], 2))
