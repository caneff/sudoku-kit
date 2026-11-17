"""The dot rule functions, ported from gridfind's `pair_difference_test.py` and
`pair_ratio_test.py` (gridfind c01723c). Each case posts clues through the
`Poster` a rule function returns and asks CP-SAT for a completion of a 9x9
board, with only the houses a case names.

The line rules are ported from `thermo_test.py` and `line_test.py` (thermo,
slow thermo, whisper, renban, lockout). gridfind's doubler and Schrodinger
cases are not ported: those rule types need board-wide state, which spec #106
leaves out. Between lines have no rule function: no puzzle of the test set
uses one (spec #106, Out of Scope).

The sum and outside-clue rules (arrow, killer cage, little killer, skyscraper,
numbered rooms, anti-knight) are ported from `arrow_test.py`, `cage_test.py`,
`group_sum_test.py`, `numbered_rooms_test.py` and `offset_adjacency_test.py`;
gridfind has no skyscraper or little-killer layer, so those two are tested
from their stated rules. An outside clue's cell sits one step off the board
(row or column -1 or 9).
"""

import itertools

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
        for cell in p.cells:  # an outside clue cell, one step off the board
            if cell not in x:
                x[cell] = m.NewIntVar(1, 9, f"x{cell}")
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
    assert all(grid[a] <= grid[b] for a, b in itertools.pairwise(longer))


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


# arrow: cells are the bulb's, then the shaft's; the value is the bulb's length

ROW0 = [(0, c) for c in range(9)]


def _arrow(bulb, shaft, clue_id="arrow-1"):
    return _clue("arrow", [*bulb, *shaft], len(bulb), clue_id)


def test_a_satisfiable_arrow_has_a_completion():
    grid = _solve([_arrow([R1C1], [R1C2, (0, 2)])], {R1C1: 5, R1C2: 3})
    assert grid is not None
    assert grid[(0, 2)] == 2


def test_a_shaft_that_cannot_equal_its_bulb_has_no_completion():
    clue = _arrow([R1C1], [R1C2, (0, 2)])
    assert _solve([clue], {R1C1: 5, R1C2: 3, (0, 2): 3}) is None


def test_a_shaft_may_repeat_digits_the_arrow_itself_forbids_none():
    grid = _solve([_arrow([R1C1], [R1C2, (0, 2)])], {R1C1: 6, R1C2: 3, (0, 2): 3})
    assert grid is not None


def test_a_pill_reads_as_a_two_digit_number_first_cell_most_significant():
    pill = _arrow([R1C1, R1C2], [(0, 2), (0, 3), (0, 4)])
    grid = _solve([pill], {R1C1: 1, R1C2: 4, (0, 2): 9, (0, 3): 3})
    assert grid is not None
    assert grid[(0, 4)] == 2  # 14 = 9 + 3 + 2
    # Read the other way round the pill is 41, which three digits cannot reach.
    assert _solve([pill], {R1C1: 4, R1C2: 1}) is None


def test_an_arrow_is_posted_on_its_bulb_and_shaft_cells():
    assert poster(_arrow([R1C1], [R1C2, (0, 2)])).cells == (R1C1, R1C2, (0, 2))


@pytest.mark.parametrize(
    "clue",
    [
        _clue("arrow", [R1C1, R1C2], 0, "arrow-9"),
        _clue("arrow", [R1C1], 1, "arrow-9"),
        _clue("arrow", [R1C1, R1C2], 2, "arrow-9"),
        {"id": "arrow-9", "rule": "arrow", "cells": [R1C1, R1C2], "values": []},
    ],
    ids=["no bulb", "no shaft", "no shaft after the pill", "no bulb length"],
)
def test_an_arrow_without_a_bulb_and_a_shaft_is_refused_naming_the_clue(clue):
    with pytest.raises(ValueError, match="arrow-9"):
        poster(clue)


# killer cage: the cells' digits differ and sum to the value


def _cage(cells, total, clue_id="cage-1"):
    return _clue("killer_cage", cells, total, clue_id)


def test_a_killer_cage_sums_to_its_total():
    grid = _solve([_cage([R1C1, R1C2, (0, 2)], 7)], {R1C1: 1, R1C2: 2})
    assert grid is not None
    assert grid[(0, 2)] == 4


def test_a_killer_cage_forbids_a_repeated_digit_even_when_the_sum_allows_it():
    # 4 + 4 = 8 meets the total, but the cage is a no-repeat set.
    assert _solve([_cage([R1C1, R1C2], 8)], {R1C1: 4, R1C2: 4}) is None
    assert _solve([_cage([R1C1, R1C2], 8)], {R1C1: 3}) is not None


def test_a_killer_cage_with_the_wrong_total_has_no_completion():
    assert _solve([_cage([R1C1, R1C2], 8)], {R1C1: 1, R1C2: 2}) is None


def test_a_killer_cage_with_one_cell_is_refused_and_so_is_one_with_no_total():
    with pytest.raises(ValueError, match="cage-9"):
        poster(_cage([R1C1], 6, "cage-9"))
    with pytest.raises(ValueError, match="cage-9"):
        poster(_cage([R1C1, R1C2], 6, "cage-9") | {"values": []})


# little killer: the diagonal's digits sum to the value, repeats allowed


DIAGONAL = [(0, 0), (1, 1), (2, 2), (3, 3)]


def _little_killer(cells, total, clue_id="little-1"):
    return _clue("little_killer", cells, total, clue_id)


def test_a_little_killer_sums_its_diagonal():
    grid = _solve([_little_killer(DIAGONAL, 12)], {(0, 0): 1, (1, 1): 2, (2, 2): 3})
    assert grid is not None
    assert grid[(3, 3)] == 6


def test_a_little_killer_may_repeat_a_digit_along_its_diagonal():
    grid = _solve([_little_killer(DIAGONAL, 20)], {(0, 0): 5, (1, 1): 5, (2, 2): 5})
    assert grid is not None
    assert grid[(3, 3)] == 5


def test_a_little_killer_with_the_wrong_sum_has_no_completion():
    clue = _little_killer(DIAGONAL, 20)
    assert _solve([clue], {(0, 0): 1, (1, 1): 2, (2, 2): 3}) is None


# skyscraper: cells are the outside cell, then the line from the clue inward


def _skyscraper(outside, line, clue_id="sky-1"):
    return {
        "id": clue_id,
        "rule": "skyscraper",
        "cells": [list(outside), *map(list, line)],
        "values": [],
    }


LEFT = (0, -1)
RIGHT = (0, 9)
ASCENDING = {(0, c): c + 1 for c in range(9)}


def test_a_skyscraper_counts_the_digits_seen_from_the_clue():
    left = _skyscraper(LEFT, ROW0, "left")
    right = _skyscraper(RIGHT, ROW0[::-1], "right")
    grid = _solve([left, right], ASCENDING, rows_distinct=True)
    assert grid is not None
    assert grid[LEFT] == 9  # 1 2 3 .. 9: every digit is taller than those before
    assert grid[RIGHT] == 1  # from the other end only the 9 shows


def test_a_skyscraper_clue_that_miscounts_has_no_completion():
    assert _solve([_skyscraper(LEFT, ROW0)], ASCENDING | {LEFT: 8}) is None


def test_a_taller_digit_hides_the_ones_behind_it():
    # 9 first: nothing after it shows, so the clue reads 1.
    row = dict(zip(ROW0, [9, 1, 2, 3, 4, 5, 6, 7, 8], strict=True))
    grid = _solve([_skyscraper(LEFT, ROW0)], row, rows_distinct=True)
    assert grid is not None
    assert grid[LEFT] == 1


def test_a_digit_equal_to_the_tallest_so_far_is_not_seen_again():
    # Without rows_distinct a repeat is possible: 3 3 9 shows 3 then 9 only.
    row = {(0, 0): 3, (0, 1): 3, (0, 2): 9}
    grid = _solve([_skyscraper(LEFT, ROW0[:3])], row)
    assert grid is not None
    assert grid[LEFT] == 2


def test_a_skyscraper_reads_the_line_in_the_order_it_is_given():
    descending = {(0, c): 9 - c for c in range(9)}
    grid = _solve([_skyscraper(LEFT, ROW0)], descending, rows_distinct=True)
    assert grid is not None
    assert grid[LEFT] == 1
    grid = _solve([_skyscraper(RIGHT, ROW0[::-1])], descending, rows_distinct=True)
    assert grid is not None
    assert grid[RIGHT] == 9


def test_a_skyscraper_with_no_line_or_a_value_is_refused():
    with pytest.raises(ValueError, match="sky-9"):
        poster(_skyscraper(LEFT, [], "sky-9"))
    with pytest.raises(ValueError, match="sky-9"):
        poster(_skyscraper(LEFT, ROW0, "sky-9") | {"values": [3]})


# numbered rooms: cells are the outside cell, then the line from the clue inward


def _room(outside, line, clue_id="room-1"):
    return _skyscraper(outside, line, clue_id) | {"rule": "numbered_rooms"}


def test_the_outside_cell_holds_the_digit_at_the_position_the_near_cell_names():
    # The near cell holds 3, so the digit at the 3rd position is the clue.
    row = {(0, 0): 3, (0, 1): 1, (0, 2): 7}
    grid = _solve([_room(LEFT, ROW0)], row, rows_distinct=True)
    assert grid is not None
    assert grid[LEFT] == 7


def test_a_numbered_room_whose_outside_cell_misses_the_named_position_fails():
    row = {(0, 0): 3, (0, 1): 1, (0, 2): 7}
    assert _solve([_room(LEFT, ROW0)], row | {LEFT: 1}, rows_distinct=True) is None


def test_a_near_cell_of_one_names_itself():
    grid = _solve([_room(LEFT, ROW0)], {(0, 0): 1}, rows_distinct=True)
    assert grid is not None
    assert grid[LEFT] == 1


def test_a_numbered_room_reads_from_the_clues_own_end():
    # From the right the near cell is column 9, holding 2: position 2 from the
    # right is column 8, so the clue is that cell's digit.
    row = {(0, 8): 2, (0, 7): 6}
    grid = _solve([_room(RIGHT, ROW0[::-1])], row, rows_distinct=True)
    assert grid is not None
    assert grid[RIGHT] == 6


def test_a_numbered_room_names_a_position_on_a_short_line_only():
    line = ROW0[:3]
    assert _solve([_room(LEFT, line)], {(0, 0): 4}) is None
    assert _solve([_room(LEFT, line)], {(0, 0): 3}) is not None


# anti-knight: one clue per knight-move pair, the two cells differ


def _knight(a, b, clue_id="knight-1"):
    return {
        "id": clue_id,
        "rule": "anti_knight",
        "cells": [list(a), list(b)],
        "values": [],
    }


def test_two_cells_a_knight_move_apart_may_not_share_a_digit():
    assert _solve([_knight(R1C1, (1, 2))], {R1C1: 4, (1, 2): 4}) is None
    assert _solve([_knight(R1C1, (1, 2))], {R1C1: 4, (1, 2): 5}) is not None


def test_an_anti_knight_pair_posts_on_its_two_cells():
    assert poster(_knight(R1C1, (1, 2))).cells == (R1C1, (1, 2))


def test_an_anti_knight_clue_with_one_cell_or_a_value_is_refused():
    with pytest.raises(ValueError, match="knight-9"):
        poster(_knight(R1C1, (1, 2), "knight-9") | {"cells": [[0, 0]]})
    with pytest.raises(ValueError, match="knight-9"):
        poster(_knight(R1C1, (1, 2), "knight-9") | {"values": [3]})
