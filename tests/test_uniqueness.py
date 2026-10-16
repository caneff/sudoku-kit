"""`check_uniqueness` on tiny CpModels, each of its five statuses reached
through a real CP-SAT solve.

The second solve running out of time is the branch where a wrong answer reads
as "unique". No model makes a first solve fast and a second slow on every
machine, so that test spends the cap between the two solves. A second solve
coming back invalid cannot be forced at all either, so that test swaps the
solve for one that reports it.
"""

import random

from ortools.sat.python import cp_model

from sudoku_kit import uniqueness
from sudoku_kit.uniqueness import check_uniqueness


def _pair(*, pin):
    """a == b over 0..1, with a pinned to 1 when `pin`: one solution or two."""
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
    # A subset-sum instance under a cap of no time at all: the search has
    # spent its limit before it starts, whatever the machine.
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
    # The model has one solution, so a second solve that finished would say
    # "unique". It is handed a cap of no time instead, and must say so.
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
    # The exclusion clause goes on a copy, so a second call on the same model
    # reports the same verdict rather than "unique".
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
