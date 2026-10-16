"""Prove one solve step from the constraints it names, and nothing else.

A step says "from these candidates and these named constraints, this claim
follows". `prove` builds a model of exactly that -- one variable per cell,
domain the cell's candidates, only the named constraints posted -- and asks
CP-SAT for a grid that breaks the claim. None exists: proved. One exists: it is
the witness. The search ran out of time: no verdict. A step that passes follows
from what it names, not from the solution, and a step that quietly used an
unnamed constraint fails with a witness that obeys only the named ones.

It builds its own model rather than using `cpsat.sudoku_model`, which posts every
row, column and region and gives every cell the full domain.
"""

from collections.abc import Callable, Collection, Iterable, Mapping
from dataclasses import dataclass
from itertools import pairwise
from typing import Literal, NamedTuple

from ortools.sat.python import cp_model

from sudoku_kit.cpsat import SOLVED, UNKNOWN, solver

Cell = tuple[int, int]
Status = Literal["proved", "refuted", "timeout"]


class ProofResult(NamedTuple):
    """`status` is "proved", "refuted" or "timeout". `witness` is set only on
    "refuted": a {(row, column): digit} grid over the cells that appear in a
    named constraint, the claim or a given chain. Other cells carry no meaning
    and are left out."""

    status: Status
    witness: dict[Cell, int] | None = None


@dataclass(frozen=True)
class Poster:
    """A constraint: the `cells` it ranges over and `post(model, x)`, which
    adds it to `model`, `x` mapping every cell to its variable."""

    cells: tuple[Cell, ...]
    post: Callable[[cp_model.CpModel, Mapping[Cell, cp_model.IntVar]], None]

    def __post_init__(self):
        object.__setattr__(self, "cells", tuple(self.cells))


def house(cells: Iterable[Cell]) -> Poster:
    """All the cells take different digits."""
    cells = tuple(cells)
    return Poster(cells, lambda m, x: m.AddAllDifferent([x[c] for c in cells]))


def table(cells: Iterable[Cell], tuples: Iterable[Iterable[int]]) -> Poster:
    """The cells, in order, take one of the allowed digit `tuples`."""
    cells = tuple(cells)
    allowed = [tuple(t) for t in tuples]
    return Poster(
        cells, lambda m, x: m.AddAllowedAssignments([x[c] for c in cells], allowed)
    )


class Order(NamedTuple):
    """A rising chain: cells[0] < cells[1] < ..."""

    cells: tuple[Cell, ...]


class Place(NamedTuple):
    """`cell` keeps only `digits` of its candidates."""

    cell: Cell
    digits: Collection[int]


class Either(NamedTuple):
    """At least one pattern holds. A pattern is a {cell: digit} dict whose
    equalities hold together."""

    patterns: tuple[Mapping[Cell, int], ...]


def _claim_cells(claim):
    if isinstance(claim, Order):
        return list(claim.cells)
    if isinstance(claim, Place):
        return [claim.cell]
    return [cell for pattern in claim.patterns for cell in pattern]


def _post_negation(m, x, claim):
    """Post "the claim fails" on `m`, for the claims that fail in one solve."""
    if isinstance(claim, Order):
        breaks = []
        for left, right in pairwise(claim.cells):
            b = m.NewBoolVar(f"breaks_{left}_{right}")
            m.Add(x[left] >= x[right]).OnlyEnforceIf(b)
            m.Add(x[left] < x[right]).OnlyEnforceIf(b.Not())
            breaks.append(b)
        m.AddBoolOr(breaks)
        return
    for i, pattern in enumerate(claim.patterns):
        # This pattern fails: some one of its equalities does.
        misses = []
        for cell, digit in pattern.items():
            b = m.NewBoolVar(f"miss{i}_{cell}")
            m.Add(x[cell] != digit).OnlyEnforceIf(b)
            m.Add(x[cell] == digit).OnlyEnforceIf(b.Not())
            misses.append(b)
        m.AddBoolOr(misses)


def _probes(candidates, claim):
    """One function per solve the claim needs, each posting that solve's
    negation: a `Place` is one solve per candidate it removes, the others one."""
    if isinstance(claim, Place):
        removed = sorted(set(candidates[claim.cell]) - set(claim.digits))
        return [lambda m, x, d=d: m.Add(x[claim.cell] == d) for d in removed]
    return [lambda m, x: _post_negation(m, x, claim)]


def _check_cells(cells, candidates, what):
    for cell in cells:
        if cell not in candidates:
            raise ValueError(f"{what} names cell {cell}, which is not on the board")


def prove(
    candidates: Mapping[Cell, Collection[int]],
    registry: Mapping[str, Poster],
    names: Iterable[str],
    claim: Order | Place | Either,
    *,
    given: Iterable[Order] = (),
    time_limit: float = 10.0,
    workers: int = 1,
) -> ProofResult:
    """Whether `claim` follows from `candidates` and the constraints in
    `registry` that `names` picks, with the `given` chains assumed.

    `candidates` maps every cell (0-based (row, column)) to the digits it may
    hold, and the board is whatever cells it holds. Returns "proved" only when
    every solve the claim needs is infeasible, "refuted" with the first
    witness found, and "timeout" when no solve found a grid but one ran out of
    `time_limit` seconds -- a timeout is never a proof. Never changes
    `candidates`.

    Raises ValueError naming a cell with no candidates, a name missing from
    `registry`, or a cell of a constraint, claim or given chain that is not in
    `candidates`, a constraint that touches a cell it does not declare, a claim
    that is not an `Order`, `Place` or `Either`, or a model CP-SAT rejects.
    """
    if not isinstance(claim, Order | Place | Either):
        raise ValueError(f"unknown claim {claim!r}: expected Order, Place or Either")
    for cell, digits in candidates.items():
        if not digits:
            raise ValueError(f"cell {cell} has no candidates")
    posters = []
    for name in names:
        if name not in registry:
            raise ValueError(f"constraint {name!r} is not in the registry")
        _check_cells(registry[name].cells, candidates, f"constraint {name!r}")
        posters.append((name, registry[name]))
    given = list(given)
    for chain in given:
        _check_cells(chain.cells, candidates, "a given chain")
    _check_cells(_claim_cells(claim), candidates, "the claim")

    shown = {c for _, p in posters for c in p.cells}
    shown.update(_claim_cells(claim))
    shown.update(c for chain in given for c in chain.cells)

    timed_out = False
    for probe in _probes(candidates, claim):
        m = cp_model.CpModel()
        x = {
            cell: m.NewIntVarFromDomain(
                cp_model.Domain.FromValues(sorted(set(digits))), f"x{cell}"
            )
            for cell, digits in candidates.items()
        }
        for name, p in posters:
            # A poster sees only the cells it declares, so one that reaches
            # for another fails here instead of leaving it out of the witness.
            try:
                p.post(m, {c: x[c] for c in p.cells})
            except KeyError as e:
                raise ValueError(
                    f"constraint {name!r} uses cell {e.args[0]}, which it does not declare"
                ) from None
        for chain in given:
            for left, right in pairwise(chain.cells):
                m.Add(x[left] < x[right])
        probe(m, x)
        s = solver(time_limit)
        s.parameters.num_workers = workers
        status = s.Solve(m)
        if status in SOLVED:
            return ProofResult("refuted", {c: s.Value(x[c]) for c in sorted(shown)})
        if status == UNKNOWN:
            timed_out = True
        elif status != cp_model.INFEASIBLE:
            names_posted = [name for name, _ in posters]
            raise ValueError(
                f"CP-SAT rejected the model for constraints {names_posted}: "
                f"{cp_model.CpSolver().StatusName(status)}"
            )
    return ProofResult("timeout" if timed_out else "proved")
