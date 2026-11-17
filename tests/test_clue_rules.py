"""The dot rule functions, ported from gridfind's `pair_difference_test.py` and
`pair_ratio_test.py` (gridfind c01723c). Each case posts clues through the
`Poster` a rule function returns and asks CP-SAT for a completion of a 9x9
board, with only the houses a case names.

The line rules are ported from `thermo_test.py` and `line_test.py` (thermo,
slow thermo, whisper, renban, lockout). gridfind's doubler and Schrodinger
cases are not ported: those rule types need board-wide state, which spec #106
leaves out. Between lines have no rule function: no puzzle of the test set
uses one (spec #106, Out of Scope).
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
    # The first cell holds the smaller digit: a directed `a - b == k` would
    # refuse it; the absolute relation must not.
    grid = _solve([_difference([R1C1, R1C2], 4)], {R1C1: 1})
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


# line rules


def _line(rule, cells, values=(), clue_id="c"):
    return {
        "id": clue_id,
        "rule": rule,
        "cells": [list(c) for c in cells],
        "values": list(values),
    }


ROW = [(0, c) for c in range(9)]


@pytest.mark.parametrize("rule", ["thermo", "slow_thermo", "renban"])
def test_a_line_clue_posts_onto_its_path_in_order(rule):
    assert poster(_line(rule, ROW[:3])).cells == tuple(ROW[:3])


# thermo


def test_a_satisfiable_thermo_has_a_completion_that_rises_from_the_bulb():
    grid = _solve([_line("thermo", ROW[:3])], {R1C1: 3})
    assert grid is not None
    assert grid[R1C1] < grid[(0, 1)] < grid[(0, 2)]


def test_a_thermo_that_cannot_rise_has_no_completion():
    assert _solve([_line("thermo", ROW[:2])], {R1C1: 5, R1C2: 5}) is None
    assert _solve([_line("thermo", ROW[:2])], {R1C1: 6, R1C2: 5}) is None


def test_a_thermo_longer_than_the_digits_can_climb_has_no_completion():
    assert _solve([_line("thermo", [*ROW, (1, 8)])]) is None  # ten cells, nine digits
    assert _solve([_line("thermo", ROW[:9])]) is not None


def test_two_thermos_each_constrain_their_own_path():
    grid = _solve(
        [
            _line("thermo", ROW[:2], clue_id="a"),
            _line("thermo", [R3C3, R3C4], clue_id="b"),
        ],
        {R1C1: 8, R3C3: 1},
    )
    assert grid is not None
    assert grid[R1C2] == 9
    assert grid[R3C4] > 1


# slow thermo


def test_a_slow_thermo_allows_equal_neighbours():
    grid = _solve([_line("slow_thermo", ROW[:2])], {R1C1: 4, R1C2: 4})
    assert grid is not None


def test_a_slow_thermo_that_has_to_fall_has_no_completion():
    assert _solve([_line("slow_thermo", ROW[:2])], {R1C1: 6, R1C2: 5}) is None


def test_a_slow_thermo_longer_than_the_digits_still_has_a_completion():
    longer = [*ROW, (1, 8)]
    grid = _solve([_line("slow_thermo", longer)])
    assert grid is not None
    assert all(grid[a] <= grid[b] for a, b in zip(longer, longer[1:]))


# whisper


def test_a_satisfiable_whisper_has_a_completion_whose_steps_clear_the_minimum():
    grid = _solve([_line("whisper", ROW[:3], [5])], {R1C1: 1})
    assert grid is not None
    assert abs(grid[R1C1] - grid[R1C2]) >= 5
    assert abs(grid[R1C2] - grid[(0, 2)]) >= 5


def test_a_whisper_with_both_cells_equal_has_no_completion():
    assert _solve([_line("whisper", ROW[:2], [5])], {R1C1: 5, R1C2: 5}) is None


def test_a_whisper_reads_its_own_minimum():
    # 4 admits a step of exactly 4; 5 does not.
    pinned = {R1C1: 1, R1C2: 5}
    assert _solve([_line("whisper", ROW[:2], [4])], pinned) is not None
    assert _solve([_line("whisper", ROW[:2], [5])], pinned) is None


def test_a_whisper_is_absolute_either_cell_may_hold_the_larger_digit():
    assert _solve([_line("whisper", ROW[:2], [5])], {R1C1: 9, R1C2: 2}) is not None


def test_two_whispers_each_constrain_their_own_path_independently():
    grid = _solve(
        [
            _line("whisper", ROW[:3], [5], "a"),
            _line("whisper", [R3C3, R3C4], [4], "b"),
        ],
        {R1C1: 1, R3C3: 1},
    )
    assert grid is not None
    assert abs(grid[R3C3] - grid[R3C4]) >= 4


# renban


def test_a_satisfiable_renban_has_a_consecutive_completion():
    grid = _solve([_line("renban", ROW[:3])], {R1C1: 5})
    assert grid is not None
    digits = sorted(grid[c] for c in ROW[:3])
    assert digits[-1] - digits[0] == 2
    assert len(set(digits)) == 3


def test_a_renban_with_a_gap_has_no_completion():
    assert _solve([_line("renban", ROW[:2])], {R1C1: 1, R1C2: 4}) is None


def test_a_renban_repeat_has_no_completion_with_no_house_behind_it():
    assert _solve([_line("renban", ROW[:2])], {R1C1: 3, R1C2: 3}) is None


def test_a_renban_takes_its_digits_in_any_order():
    grid = _solve([_line("renban", ROW[:3])], {R1C1: 6, R1C2: 4, (0, 2): 5})
    assert grid is not None


def test_a_longer_renban_with_one_missing_digit_has_no_completion():
    pinned = {(0, 0): 1, (0, 1): 2, (0, 2): 3, (0, 3): 5}
    assert _solve([_line("renban", ROW[:4])], pinned) is None


# lockout


def test_a_satisfiable_lockout_has_a_completion_outside_the_ends():
    line = _line("lockout", ROW[:3], [4])
    grid = _solve([line], {R1C1: 2, (0, 2): 7})
    assert grid is not None
    assert grid[R1C2] < 2 or grid[R1C2] > 7


def test_a_lockout_interior_inside_the_end_range_has_no_completion():
    line = _line("lockout", ROW[:3], [4])
    assert _solve([line], {R1C1: 2, R1C2: 5, (0, 2): 7}) is None


def test_a_lockout_interior_equal_to_an_end_has_no_completion():
    line = _line("lockout", ROW[:3], [4])
    assert _solve([line], {R1C1: 2, R1C2: 7, (0, 2): 7}) is None
    assert _solve([line], {R1C1: 2, R1C2: 2, (0, 2): 7}) is None


def test_lockout_ends_closer_than_the_minimum_have_no_completion():
    line = _line("lockout", ROW[:3], [4])
    assert _solve([line], {R1C1: 4, (0, 2): 5}) is None


def test_a_lockout_reads_the_pair_as_min_and_max_either_end_larger():
    line = _line("lockout", ROW[:3], [4])
    grid = _solve([line], {R1C1: 7, (0, 2): 2})
    assert grid is not None
    assert grid[R1C2] < 2 or grid[R1C2] > 7


def test_a_two_cell_lockout_checks_only_the_gap():
    line = _line("lockout", ROW[:2], [4])
    assert _solve([line], {R1C1: 5, R1C2: 5}) is None
    assert _solve([line], {R1C1: 1, R1C2: 9}) is not None


@pytest.mark.parametrize(("size", "gap"), [(4, 2), (6, 3), (9, 4)])
def test_a_lockout_gap_is_the_clue_value_not_a_board_size(size, gap):
    line = _line("lockout", ROW[:2], [gap])
    assert _solve([line], {R1C1: 1, R1C2: gap}) is None
    assert _solve([line], {R1C1: 1, R1C2: gap + 1}) is not None


# malformed clues


@pytest.mark.parametrize(
    ("rule", "values"),
    [
        ("thermo", []),
        ("slow_thermo", []),
        ("renban", []),
        ("whisper", [4]),
        ("lockout", [4]),
    ],
)
def test_a_one_cell_line_clue_is_refused_naming_the_clue(rule, values):
    with pytest.raises(ValueError, match="line-9"):
        poster(_line(rule, [R1C1], values, "line-9"))


@pytest.mark.parametrize(
    ("rule", "values"),
    [("thermo", [1]), ("renban", [1]), ("whisper", []), ("lockout", [4, 4])],
)
def test_a_line_clue_with_the_wrong_value_count_is_refused(rule, values):
    with pytest.raises(ValueError, match="line-9"):
        poster(_line(rule, ROW[:3], values, "line-9"))


def test_there_is_no_between_rule():
    with pytest.raises(ValueError, match="between"):
        poster(_line("between", ROW[:3]))


@pytest.mark.parametrize("rule", ["difference", "ratio"])
@pytest.mark.parametrize("count", [1, 3], ids=["too few", "too many"])
def test_a_dot_clue_with_the_wrong_cell_count_is_refused_naming_the_clue(rule, count):
    clue = _clue(rule, [(0, c) for c in range(count)], 2, "dot-7")
    with pytest.raises(ValueError, match="dot-7"):
        poster(clue)


def test_a_clue_with_an_unknown_rule_is_refused_naming_the_rule():
    with pytest.raises(ValueError, match="sandwich"):
        poster(_clue("sandwich", [R1C1, R1C2], 2))
