"""Uniqueness check on a raw CpModel: solve, exclude the solution found,
re-solve, and expect infeasible. Works on any `CpModel` and list of decision
variables, with no board structure assumed.

`sudoku_kit.cpsat.solve_unique` runs the same proof with a different
contract: it raises on a timeout where this reports one, and it spends the
model where this leaves it alone. Why both exist:
docs/adr/0001-two-uniqueness-proofs.md.
"""

from typing import Literal, NamedTuple

from ortools.sat.python import cp_model

from sudoku_kit.cpsat import forbid

Status = Literal["unique", "not_unique", "infeasible", "timeout", "invalid"]


class UniquenessResult(NamedTuple):
    """`first`/`second` are solutions -- tuples of values aligned with the
    `variables` passed to `check_uniqueness` -- with `second` set only when
    `status` is "not_unique"."""

    status: Status
    first: tuple | None = None
    second: tuple | None = None

    @property
    def unique(self):
        return self.status == "unique"


def _solve(model, time_limit, workers):
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = time_limit
    solver.parameters.num_workers = workers
    return solver.Solve(model), solver


def _remap(retry_model, v):
    """The `retry_model` literal for `v` -- a plain variable's proto index
    is non-negative, but a negated literal (`.Not()`) carries a negative
    one, so it resolves through the positive base variable and gets
    negated back rather than being looked up directly."""
    index = v.Index()
    if index >= 0:
        return retry_model.GetIntVarFromProtoIndex(index)
    return retry_model.GetIntVarFromProtoIndex(-index - 1).Not()


def check_uniqueness(model, variables, *, time_limit=10.0, workers=1):
    """True (via `.unique`) iff `model` has exactly one solution over
    `variables`. A timeout or an invalid model is reported as such and
    never as unique -- a caller stripping clues that trusted either would
    drop a clue the puzzle needs.

    Never mutates `model`: the exclusion constraint that rules the first
    solution out is added to an internal copy, so the caller's model is
    safe to reuse across repeated calls.
    """
    variables = list(variables)
    status, solver = _solve(model, time_limit, workers)
    if status == cp_model.MODEL_INVALID:
        return UniquenessResult("invalid")
    if status == cp_model.UNKNOWN:
        return UniquenessResult("timeout")
    if status == cp_model.INFEASIBLE:
        return UniquenessResult("infeasible")
    first = tuple(solver.Value(v) for v in variables)

    retry_model = model.clone()
    retry_variables = [_remap(retry_model, v) for v in variables]

    forbid(retry_model, dict(enumerate(retry_variables)), dict(enumerate(first)))

    status, solver = _solve(retry_model, time_limit, workers)
    if status == cp_model.MODEL_INVALID:
        return UniquenessResult("invalid", first)
    if status == cp_model.UNKNOWN:
        return UniquenessResult("timeout", first)
    if status == cp_model.INFEASIBLE:
        return UniquenessResult("unique", first)
    second = tuple(solver.Value(v) for v in retry_variables)
    return UniquenessResult("not_unique", first, second)
