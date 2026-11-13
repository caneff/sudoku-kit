"""`check_uniqueness` on tiny CpModels, each of its five statuses reached
through a real CP-SAT solve.

The second solve running out of time is the branch where a wrong answer reads
as "unique". No model makes a first solve fast and a second slow on every
machine, so that test spends the cap between the two solves. A second solve
coming back invalid cannot be forced at all either, so that test swaps the
solve for one that reports it.
"""

import random

import pytest
from ortools.sat.python import cp_model

from sudoku_kit import uniqueness
from sudoku_kit.uniqueness import check_uniqueness


def _pair(*, pin):
    m = cp_model.CpModel()
    a = m.NewIntVar(0, 1, "a")
    b = m.NewIntVar(0, 1, "b")
    m.Add(a == b)
    if pin:
        m.Add(a == 1)
    return m, [a, b]


def test_a_one_solution_model_is_unique():
    m, variables = _pair(pin=True)
    result = check_uniqueness(m, variables)
    assert result.status == "unique"
    assert result.unique
    assert result.first == (1, 1)
    assert result.second is None


def test_a_two_solution_model_is_not_unique_with_both_solutions():
    m, variables = _pair(pin=False)
    result = check_uniqueness(m, variables)
    assert result.status == "not_unique"
    assert not result.unique
    assert {result.first, result.second} == {(0, 0), (1, 1)}


def test_a_model_with_no_solution_is_infeasible():
    m = cp_model.CpModel()
    a = m.NewIntVar(0, 1, "a")
    m.Add(a == 0)
    m.Add(a == 1)
    result = check_uniqueness(m, [a])
    assert result.status == "infeasible"
    assert not result.unique
    assert result.first is None
    assert result.second is None


def test_an_invalid_model_is_invalid():
    # An IntVar built with lb > ub is invalid at solve time, with no
    # exception at construction.
    m = cp_model.CpModel()
    bad = m.NewIntVar(5, 2, "bad")
    result = check_uniqueness(m, [bad])
    assert result.status == "invalid"
    assert not result.unique
    assert result.first is None
    assert result.second is None


def test_a_solve_that_runs_out_of_time_is_timeout():
    m = cp_model.CpModel()
    rng = random.Random(1)
    xs = [m.NewBoolVar(f"x{i}") for i in range(60)]
    weights = [rng.randint(1, 1000) for _ in xs]
    m.Add(sum(w * x for w, x in zip(weights, xs, strict=True)) == sum(weights) // 2)
    result = check_uniqueness(m, xs, time_limit=0.0, workers=1)
    assert result.status == "timeout"
    assert not result.unique
    assert result.first is None
    assert result.second is None


def test_a_second_solve_that_runs_out_of_time_is_timeout_not_unique(monkeypatch):
    real, limits = uniqueness._solve, []

    def stingy(model, time_limit, workers):
        limits.append(time_limit)
        return real(model, time_limit if len(limits) == 1 else 0.0, workers)

    monkeypatch.setattr(uniqueness, "_solve", stingy)
    m, variables = _pair(pin=True)
    result = check_uniqueness(m, variables)
    assert len(limits) == 2
    assert result.status == "timeout"
    assert not result.unique
    assert result.first == (1, 1)
    assert result.second is None


def test_a_second_solve_that_is_invalid_is_invalid_not_unique(monkeypatch):
    real, calls = uniqueness._solve, []

    def broken(model, time_limit, workers):
        calls.append(time_limit)
        if len(calls) == 1:
            return real(model, time_limit, workers)
        return cp_model.MODEL_INVALID, None

    monkeypatch.setattr(uniqueness, "_solve", broken)
    m, variables = _pair(pin=True)
    result = check_uniqueness(m, variables)
    assert result.status == "invalid"
    assert not result.unique
    assert result.first == (1, 1)
    assert result.second is None


def test_the_caller_s_model_is_left_untouched():
    m, variables = _pair(pin=False)
    before = len(m.Proto().constraints)
    assert check_uniqueness(m, variables).status == "not_unique"
    assert check_uniqueness(m, variables).status == "not_unique"
    assert len(m.Proto().constraints) == before


def test_a_negated_literal_among_the_variables_reads_as_its_own_value():
    # `a != b` has the solutions (0, 1) and (1, 0) over (a, b); read through
    # `[a, b.Not()]` they are (0, 0) and (1, 1).
    m = cp_model.CpModel()
    a = m.NewBoolVar("a")
    b = m.NewBoolVar("b")
    m.Add(a != b)
    result = check_uniqueness(m, [a, b.Not()])
    assert result.status == "not_unique"
    assert {result.first, result.second} == {(0, 0), (1, 1)}


@pytest.mark.parametrize("negate", [False, True])
def test_variables_given_by_name_come_back_by_name(negate):
    # x is fixed at 2, y is free, z's literal is fixed at 1: the two solutions
    # differ only in y, and no two names share a value, so a value filed under
    # the wrong name fails. Under negation z reads its literal flipped.
    m = cp_model.CpModel()
    x = m.NewIntVar(2, 2, "x")
    y = m.NewBoolVar("y")
    z = m.NewBoolVar("z")
    m.Add(z == 1)
    result = check_uniqueness(m, {"x": x, "y": y, "z": z.Not() if negate else z})
    assert result.status == "not_unique"
    z_value = 0 if negate else 1
    expected = [{"x": 2, "y": 0, "z": z_value}, {"x": 2, "y": 1, "z": z_value}]
    assert sorted([result.first, result.second], key=lambda s: s["y"]) == expected


def test_a_negated_literal_variable_is_judged_correctly():
    # `a.Not()` reads 1 - a, so a == b pins (1, 0)-style pairs: with a == 1
    # the pair (a.Not(), b) is forced to (0, 1) -- unique; unpinned, two.
    m, (a, b) = _pair(pin=True)
    assert check_uniqueness(m, [a.Not(), b]).first == (0, 1)
    assert check_uniqueness(m, [a.Not(), b]).status == "unique"
    m, (a, b) = _pair(pin=False)
    result = check_uniqueness(m, [a.Not(), b])
    assert result.status == "not_unique"
    assert {result.first, result.second} == {(1, 0), (0, 1)}


def test_a_model_with_no_variables_is_unique():
    m = cp_model.CpModel()
    assert check_uniqueness(m, []).status == "unique"
