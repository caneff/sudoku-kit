"""Uniqueness check on a raw CpModel: solve, exclude the solution found,
re-solve, and expect infeasible. Works on any `CpModel` and list of decision
variables, with no board structure assumed.

`sudoku_kit.cpsat.solve_unique` runs the same proof with a different
contract: it raises on a timeout where this reports one, and it spends the
model where this leaves it alone. Why both exist:
docs/adr/0001-two-uniqueness-proofs.md.
"""

from collections.abc import Mapping
from typing import Literal, NamedTuple

from ortools.sat.python import cp_model

from sudoku_kit.cpsat import forbid

Status = Literal["unique", "not_unique", "infeasible", "timeout", "invalid"]


class UniquenessResult(NamedTuple):
    """`first`/`second` are solutions -- tuples of values aligned with the
    `variables` passed to `check_uniqueness`, or dicts with the same keys when
    `variables` was a Mapping -- with `second` set only when `status` is
    "not_unique"."""

    status: Status
    first: tuple | dict | None = None
    second: tuple | dict | None = None

    @property
    def unique(self):
        return self.status == "unique"


_UNSOLVED = {cp_model.MODEL_INVALID: "invalid", cp_model.UNKNOWN: "timeout"}


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


def _read(solver, variables):
    return tuple(solver.Value(v) for v in variables)


def _keyed(values, keys):
    """`values` as a tuple, or a dict under `keys` when the caller gave names."""
    if keys is None:
        return values
    return dict(zip(keys, values, strict=True))


def check_uniqueness(model, variables, *, time_limit=10.0, workers=1):
    """True (via `.unique`) iff `model` has exactly one solution over
    `variables`, a sequence or a Mapping (solutions then come back keyed the
    same way). A timeout or an invalid model is reported as such and
    never as unique -- a caller stripping clues that trusted either would
    drop a clue the puzzle needs.

    Never mutates `model`: the exclusion constraint that rules the first
    solution out is added to an internal copy, so the caller's model is
    safe to reuse across repeated calls.
    """
    keys = list(variables) if isinstance(variables, Mapping) else None
    variables = list(variables.values() if keys is not None else variables)
    status, solver = _solve(model, time_limit, workers)
    if status in _UNSOLVED:
        return UniquenessResult(_UNSOLVED[status])
    if status == cp_model.INFEASIBLE:
        return UniquenessResult("infeasible")
    first = _read(solver, variables)

    retry_model = model.clone()
    retry_variables = [_remap(retry_model, v) for v in variables]

    forbid(retry_model, dict(enumerate(retry_variables)), dict(enumerate(first)))

    status, solver = _solve(retry_model, time_limit, workers)
    if status in _UNSOLVED:
        return UniquenessResult(_UNSOLVED[status], _keyed(first, keys))
    if status == cp_model.INFEASIBLE:
        return UniquenessResult("unique", _keyed(first, keys))
    second = _read(solver, retry_variables)
    return UniquenessResult("not_unique", _keyed(first, keys), _keyed(second, keys))
