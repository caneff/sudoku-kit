import pytest
from ortools.sat.python import cp_model

from sudoku_kit import cpsat
from sudoku_kit.cpsat import (
    boxes,
    forbid,
    has_second_solution,
    solve_unique,
    solver,
    sudoku_model,
)


def _model(total):
    m = cp_model.CpModel()
    x = {"x": m.NewIntVar(1, 3, "x"), "y": m.NewIntVar(1, 3, "y")}
    m.Add(x["x"] + x["y"] == total)
    return m, x


def _feasible(m):
    s = solver(30)
    status = s.Solve(m)
    assert status != cp_model.UNKNOWN, "the test model spent its 30s cap"
    return status in (cp_model.OPTIMAL, cp_model.FEASIBLE), s


def _solve(m, x):
    ok, s = _feasible(m)
    return {k: s.Value(v) for k, v in x.items()} if ok else None


def test_forbid_rules_out_exactly_the_named_assignment():
    # Two free variables over 1..3: nine assignments. Forbidding each one as
    # it is found must strike exactly that one, so the enumeration runs the
    # full nine. A clause that ruled out every cell it named independently --
    # "x is not 1 AND y is not 1" rather than "x is not 1 OR y is not 1" --
    # would strike five on the first round and stop at three.
    m = cp_model.CpModel()
    x = {"x": m.NewIntVar(1, 3, "x"), "y": m.NewIntVar(1, 3, "y")}
    seen = []
    while (found := _solve(m, x)) is not None:
        assert found not in seen, f"{found} came back twice: forbid struck nothing"
        seen.append(found)
        forbid(m, x, found, tag=len(seen))
    assert len(seen) == 9, sorted(map(sorted, (s.items() for s in seen)))


def test_has_second_solution_on_a_unique_and_an_ambiguous_model():
    m, x = _model(6)
    assert has_second_solution(m, x, _solve(m, x), 10) is False
    m, x = _model(4)
    assert has_second_solution(m, x, _solve(m, x), 10) is True


def test_has_second_solution_raises_rather_than_report_a_verdict():
    m, x = _model(4)
    first = _solve(m, x)
    with pytest.raises(TimeoutError):
        has_second_solution(m, x, first, 0.0)


def test_reproducible_pins_one_worker_and_seed_zero():
    s = solver(30)
    assert (s.parameters.num_workers, s.parameters.random_seed) == (1, 0)
    assert s.parameters.max_time_in_seconds == 30
    assert s.parameters.randomize_search is False


def test_a_seed_handed_to_the_reproducible_solver_is_a_loud_mistake():
    for kwargs in ({"seed": 1234}, {"randomize": True}):
        with pytest.raises(ValueError, match="reproducible"):
            solver(30, **kwargs)


def test_search_mode_leaves_the_portfolio_and_the_caller_s_seed_alone():
    s = solver(30, reproducible=False, seed=1234, randomize=True)
    assert s.parameters.num_workers > 1
    assert s.parameters.random_seed == 1234
    assert s.parameters.randomize_search is True


def test_workers_sets_the_thread_count_in_both_configurations():
    # The worker count is the one knob both configurations share: a caller that
    # wants more threads says so here instead of overwriting the parameter on
    # the returned solver.
    assert solver(30, workers=3).parameters.num_workers == 3
    assert solver(30, reproducible=False, workers=3).parameters.num_workers == 3


def test_solve_unique_on_unique_nonunique_and_infeasible_models():
    m, x = _model(6)
    assert solve_unique(m, x, 10) == ({"x": 3, "y": 3}, True)
    m, x = _model(4)
    first, unique = solve_unique(m, x, 10)
    assert unique is False and first["x"] + first["y"] == 4
    m, x = _model(9)
    assert solve_unique(m, x, 10) == (None, False)


def test_solve_unique_raises_on_a_spent_cap_in_the_first_solve():
    m, x = _model(4)
    with pytest.raises(TimeoutError):
        solve_unique(m, x, 0.0)


def test_solve_unique_raises_when_only_the_second_solve_times_out(monkeypatch):
    real, calls = cpsat.solver, []

    def stingy(limit, **kw):
        calls.append(limit)
        return real(limit if len(calls) == 1 else 0.0, **kw)

    monkeypatch.setattr(cpsat, "solver", stingy)
    m, x = _model(4)
    with pytest.raises(TimeoutError):
        solve_unique(m, x, 10)
    assert len(calls) == 2, calls


def _invalid_model():
    """A model CP-SAT rejects outright: an integer variable with lower bound
    above its upper bound."""
    m = cp_model.CpModel()
    return m, {"x": m.NewIntVar(3, 1, "x")}


def test_solve_unique_raises_on_an_invalid_model_in_the_first_solve():
    # MODEL_INVALID is a broken model, not a puzzle with no solution.
    m, x = _invalid_model()
    with pytest.raises(ValueError, match="invalid"):
        solve_unique(m, x, 10)


def test_has_second_solution_raises_on_an_invalid_model():
    # The retry meets the invalid model; False would read as "unique".
    m, x = _invalid_model()
    with pytest.raises(ValueError, match="invalid"):
        has_second_solution(m, x, {"x": 1}, 10)


def test_solve_unique_raises_when_only_the_retry_is_invalid(monkeypatch):
    # The first solve is fine; the retry's model comes back MODEL_INVALID.
    real, calls = cpsat.solver, []

    class Invalid:
        def Solve(self, m):
            return cp_model.MODEL_INVALID

    def factory(limit, **kw):
        calls.append(limit)
        return real(limit, **kw) if len(calls) == 1 else Invalid()

    monkeypatch.setattr(cpsat, "solver", factory)
    m, x = _model(4)
    with pytest.raises(ValueError, match="invalid"):
        solve_unique(m, x, 10)
    assert len(calls) == 2, calls


def _solutions(m, x):
    found = []
    while (a := _solve(m, x)) is not None:
        found.append(a)
        forbid(m, x, a, tag=len(found))
    return found


def _lines(n):
    rows = [[(r, c) for c in range(n)] for r in range(n)]
    return rows + [[(r, c) for r in range(n)] for c in range(n)]


def _houses_ok(a, n, houses):
    return all(len({a[c] for c in h}) == n for h in houses)


def test_sudoku_model_on_a_square_board():
    m, x = sudoku_model(4, boxes(4, 2, 2))
    assert sorted(x) == [(r, c) for r in range(4) for c in range(4)]
    sols = _solutions(m, x)
    assert len(sols) == 288
    assert all(_houses_ok(a, 4, _lines(4) + boxes(4, 2, 2)) for a in sols)


def test_sudoku_model_on_a_rectangular_box_board():
    m, x = sudoku_model(6, boxes(6, 2, 3))
    found = _solve(m, x)
    assert found is not None
    assert _houses_ok(found, 6, _lines(6) + boxes(6, 2, 3))

    # The pair is (height, width): (0,0) and (1,2) share a 2x3 box but not a
    # 3x2 one, and (0,0) and (2,1) share a 3x2 box but not a 2x3 one.
    def pinned(height, width, cell):
        m, x = sudoku_model(6, boxes(6, height, width))
        m.Add(x[0, 0] == 1)
        m.Add(x[cell] == 1)
        return _feasible(m)[0]

    assert not pinned(2, 3, (1, 2)) and pinned(3, 2, (1, 2))
    assert not pinned(3, 2, (2, 1)) and pinned(2, 3, (2, 1))


def test_boxes_refuses_boxes_that_are_not_n_cells():
    for height, width in ((2, 2), (4, 2), (3, 1)):
        with pytest.raises(ValueError, match=f"{height}x{width} boxes do not hold 6"):
            boxes(6, height, width)


def test_sudoku_model_on_region_and_latin_boards():
    m, x = sudoku_model(3, ())
    latin = _solutions(m, x)
    assert len(latin) == 12
    region = [(0, 0), (0, 1), (1, 0)]
    m, x = sudoku_model(3, [region])
    sols = _solutions(m, x)
    expected = [a for a in latin if len({a[c] for c in region}) == 3]
    assert 0 < len(expected) < 12
    key = lambda a: sorted(a.items())
    assert sorted(sols, key=key) == sorted(expected, key=key)


def test_has_second_solution_takes_no_tag():
    m, x = _model(4)
    with pytest.raises(TypeError):
        has_second_solution(m, x, {"x": 1, "y": 3}, 10, tag=0)
