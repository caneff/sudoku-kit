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
from dataclasses import dataclass, replace
from itertools import pairwise
from typing import Literal, NamedTuple

from ortools.sat.python import cp_model

from sudoku_kit.cpsat import SOLVED, UNKNOWN, forbid, solver

Cell = tuple[int, int]
Status = Literal["proved", "refuted", "contradictory", "timeout"]


class ProofResult(NamedTuple):
    """`status` is "proved", "refuted", "contradictory" or "timeout". `witness` is set only on
    "refuted": a {(row, column): digit} grid over the cells that appear in a
    named constraint, the claim or a given chain. Other cells carry no meaning
    and are left out."""

    status: Status
    witness: dict[Cell, int] | None = None


class IrreducibleResult(NamedTuple):
    """`status` as `prove` gives it. `irreducible_set` is the irreducible set, in
    the order given: on "proved", named constraints that still prove the claim
    with none of them removable; on "contradictory", named constraints that
    conflict with each other, the candidates and the given chains; None on
    "refuted" and "timeout". `witness` is set only on "refuted", as `prove`
    sets it. `irreducible_checked` is False when a deletion trial timed out
    and kept its constraint, so `irreducible_set` still holds but may not be
    irreducible; it is False too when there is no set."""

    status: Status
    irreducible_set: tuple[str, ...] | None = None
    witness: dict[Cell, int] | None = None
    irreducible_checked: bool = False


class Elimination(NamedTuple):
    """`by` removed `digits` from `cell`. `by` is a constraint's name,
    "given chain <k>" for the k-th given chain counting from 1, or "negated
    claim". For a `Place` every run opens with a "negated claim" entry that
    fixes the cell to the run's digit; its `digits` are the cell's other
    candidates, and empty when the run's digit was the only one."""

    by: str
    cell: Cell
    digits: tuple[int, ...]


class PropagationResult(NamedTuple):
    """`proves` is whether propagation alone emptied a cell, in every run
    for a `Place`. `log` is every elimination in the order made."""

    proves: bool
    log: tuple[Elimination, ...]


@dataclass(frozen=True)
class Poster:
    """A constraint: the `cells` it ranges over and `post(model, x)`, which
    adds it to `model`, `x` mapping those `cells` to their variables."""

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

    def claim_cells(self):
        return list(self.cells)

    def fixes(self, candidates):
        """The (cell, digit) a run fixes, one per run; None when the claim
        fails in one solve, by `post_negation`."""
        return

    def post_negation(self, m, x):
        """Post "the chain does not rise" on `m`."""
        breaks = []
        for left, right in pairwise(self.cells):
            b = m.NewBoolVar(f"breaks_{left}_{right}")
            m.Add(x[left] >= x[right]).OnlyEnforceIf(b)
            m.Add(x[left] < x[right]).OnlyEnforceIf(b.Not())
            breaks.append(b)
        m.AddBoolOr(breaks)

    def probes(self, candidates):
        return [self.post_negation]


class Place(NamedTuple):
    """`cell` keeps only `digits` of its candidates."""

    cell: Cell
    digits: Collection[int]

    def claim_cells(self):
        return [self.cell]

    def removed(self, candidates):
        return sorted(set(candidates[self.cell]) - set(self.digits))

    def fixes(self, candidates):
        return [(self.cell, d) for d in self.removed(candidates)]

    def probes(self, candidates):
        return [
            lambda m, x, d=d: m.Add(x[self.cell] == d) for d in self.removed(candidates)
        ]


class Either(NamedTuple):
    """At least one pattern holds. A pattern is a {cell: digit} dict whose
    equalities hold together."""

    patterns: tuple[Mapping[Cell, int], ...]

    def claim_cells(self):
        return [cell for pattern in self.patterns for cell in pattern]

    def fixes(self, candidates):
        return None

    def post_negation(self, m, x):
        """Post "every pattern fails" on `m`."""
        for i, pattern in enumerate(self.patterns):
            forbid(m, x, pattern, tag=i)

    def probes(self, candidates):
        return [self.post_negation]


def _check_cells(cells, candidates, what):
    for cell in cells:
        if cell not in candidates:
            raise ValueError(f"{what} names cell {cell}, which is not on the board")


def _check(candidates, registry, names, claim, given):
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
    given = tuple(given)
    for chain in given:
        _check_cells(chain.cells, candidates, "a given chain")
    _check_cells(claim.claim_cells(), candidates, "the claim")
    return Step(candidates, tuple(posters), given, claim)


def _post(m, x, name, poster):
    # A poster sees only the cells it declares, so one that reaches for
    # another fails here instead of leaving it out of the witness.
    try:
        poster.post(m, {c: x[c] for c in poster.cells})
    except KeyError as e:
        raise ValueError(
            f"constraint {name!r} uses cell {e.args[0]}, which it does not declare"
        ) from None


def _post_chain(m, x, chain):
    for left, right in pairwise(chain.cells):
        m.Add(x[left] < x[right])


def _variables(m, candidates):
    return {
        cell: m.NewIntVarFromDomain(
            cp_model.Domain.FromValues(sorted(set(digits))), f"x{cell}"
        )
        for cell, digits in candidates.items()
    }


@dataclass(frozen=True)
class Step:
    """One prepared step: the `candidates`, the named constraints as
    (name, `Poster`) pairs, the `given` chains, the `claim`, and the limits
    every solve of it runs under."""

    candidates: Mapping[Cell, Collection[int]]
    posters: tuple[tuple[str, Poster], ...]
    given: tuple[Order, ...]
    claim: Order | Place | Either
    time_limit: float = 10.0
    workers: int = 1

    def without(self, pair):
        """This step with the named constraint `pair` left out."""
        return replace(self, posters=tuple(p for p in self.posters if p is not pair))

    def shown(self):
        """The cells a witness carries: those of a named constraint, the claim
        or a given chain."""
        shown = {c for _, p in self.posters for c in p.cells}
        shown.update(self.claim.claim_cells())
        shown.update(c for chain in self.given for c in chain.cells)
        return shown

    def run(self, m, what):
        s = solver(self.time_limit, workers=self.workers)
        status = s.Solve(m)
        if status not in (*SOLVED, UNKNOWN, cp_model.INFEASIBLE):
            raise ValueError(
                f"CP-SAT rejected the model for {what}: "
                f"{cp_model.CpSolver().StatusName(status)}"
            )
        return status, s

    def solve(self, probe):
        m = cp_model.CpModel()
        x = _variables(m, self.candidates)
        for name, p in self.posters:
            _post(m, x, name, p)
        for chain in self.given:
            _post_chain(m, x, chain)
        if probe is not None:
            probe(m, x)
        what = f"constraints {[name for name, _ in self.posters]}"
        return (*self.run(m, what), x)

    def first_grid(self, probes):
        timed_out = False
        for probe in probes:
            status, s, x = self.solve(probe)
            if status in SOLVED:
                return status, s, x
            timed_out = timed_out or status == UNKNOWN
        return (UNKNOWN if timed_out else cp_model.INFEASIBLE), None, None

    def prove(self):
        probes = self.claim.probes(self.candidates)
        status, s, x = self.first_grid(probes)
        if status in SOLVED:
            shown = sorted(self.shown())
            return ProofResult("refuted", {c: s.Value(x[c]) for c in shown})
        if status == UNKNOWN:
            return ProofResult("timeout")
        # Every probe is infeasible. That proves the claim only if some grid is
        # left at all; none means the named constraints contradict themselves or
        # the candidates, and would "prove" any claim.
        status, _, _ = self.solve(None)
        if status == UNKNOWN:
            return ProofResult("timeout")
        return ProofResult(
            "contradictory" if status == cp_model.INFEASIBLE else "proved"
        )

    def unsupported(self, by, cells, post, candidates):
        supported = {c: set() for c in cells}
        for cell in cells:
            for digit in sorted(candidates[cell] - supported[cell]):
                m = cp_model.CpModel()
                x = _variables(m, {c: candidates[c] for c in cells})
                post(m, x)
                m.Add(x[cell] == digit)
                status, s = self.run(m, repr(by))
                if status in SOLVED:
                    for c in cells:
                        supported[c].add(s.Value(x[c]))
                elif status == UNKNOWN:
                    raise TimeoutError(
                        f"CP-SAT hit the {self.time_limit}s limit testing "
                        f"{digit} in {cell} against {by!r}; no verdict"
                    )
        return {
            c: tuple(sorted(candidates[c] - supported[c]))
            for c in cells
            if candidates[c] - supported[c]
        }

    def propagate(self, candidates, units, log):
        changed = True
        while changed:
            changed = False
            for by, cells, post in units:
                removed = self.unsupported(by, cells, post, candidates)
                for cell, digits in removed.items():
                    candidates[cell] -= set(digits)
                    log.append(Elimination(by, cell, digits))
                    changed = True
                if any(not candidates[c] for c in cells):
                    return True
        return False


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
    every solve the claim needs is infeasible and the named constraints, given
    chains and candidates still admit some grid; "contradictory" when they
    admit none, since then every claim would pass; "refuted" with the first
    witness found; and "timeout" when no solve found a grid but one ran out of
    `time_limit` seconds -- a timeout is never a proof. Never changes
    `candidates`.

    Raises ValueError naming a cell with no candidates, a name missing from
    `registry`, or a cell of a constraint, claim or given chain that is not in
    `candidates`, a constraint that touches a cell it does not declare, a claim
    that is not an `Order`, `Place` or `Either`, or a model CP-SAT rejects.
    """
    step = _check(candidates, registry, names, claim, given)
    return replace(step, time_limit=time_limit, workers=workers).prove()


def irreducible(
    candidates: Mapping[Cell, Collection[int]],
    registry: Mapping[str, Poster],
    names: Iterable[str],
    claim: Order | Place | Either,
    *,
    given: Iterable[Order] = (),
    time_limit: float = 10.0,
    workers: int = 1,
) -> IrreducibleResult:
    """An irreducible set of the named constraints behind `prove`'s verdict.
    Takes `prove`'s arguments and raises its ValueErrors.

    One greedy pass over `names` in the order given drops each constraint
    whose removal leaves every solve infeasible: each probe solve on
    "proved", the solve with no negation on "contradictory". One pass is
    enough, since removing a constraint never makes a feasible model
    infeasible. Earlier names are tried first, so a caller lists a constraint
    last to keep it when there is a choice. The given chains always stay. The
    set is irreducible, not the smallest: another set may be shorter. Never
    changes `candidates`.
    """
    step = replace(
        _check(candidates, registry, names, claim, given),
        time_limit=time_limit,
        workers=workers,
    )
    result = step.prove()
    if result.status in ("refuted", "timeout"):
        return IrreducibleResult(result.status, None, result.witness)
    probes = claim.probes(candidates) if result.status == "proved" else [None]

    kept, checked = step, True
    for pair in step.posters:
        trial = kept.without(pair)
        status, _, _ = trial.first_grid(probes)
        if status == cp_model.INFEASIBLE:
            kept = trial
        checked = checked and status != UNKNOWN
    return IrreducibleResult(
        result.status, tuple(n for n, _ in kept.posters), None, checked
    )


def propagation(
    candidates: Mapping[Cell, Collection[int]],
    registry: Mapping[str, Poster],
    names: Iterable[str],
    claim: Order | Place | Either,
    *,
    given: Iterable[Order] = (),
    time_limit: float = 10.0,
    workers: int = 1,
) -> PropagationResult:
    """Whether one-constraint propagation alone proves the claim, by emptying a
    cell under its negation.
    Takes `prove`'s arguments and raises its ValueErrors.

    Each named constraint, given chain and the negated claim is taken alone:
    a digit leaves a cell when that one constraint has no completion using
    it, tested by a CP-SAT solve, and the loop repeats until nothing changes.
    The answer is yes when some cell runs out of candidates. A `Place` runs
    the loop once per digit it removes, with the cell fixed to that digit,
    and the answer is yes only when every run empties a cell; the first run
    that does not ends the search. Never changes `candidates`.

    Raises ValueError, too, when the named constraints, given chains and
    candidates admit no grid -- the input `prove` calls "contradictory", on
    which propagation would empty a cell for any claim -- and TimeoutError
    when one solve spends `time_limit` seconds: a timeout is never a verdict.
    """
    step = replace(
        _check(candidates, registry, names, claim, given),
        time_limit=time_limit,
        workers=workers,
    )
    status, _, _ = step.solve(None)
    if status == UNKNOWN:
        raise TimeoutError(
            f"CP-SAT hit the {time_limit}s limit checking that the named "
            "constraints admit a grid; no verdict"
        )
    if status == cp_model.INFEASIBLE:
        raise ValueError(
            f"the named constraints {[name for name, _ in step.posters]} admit no "
            "grid with these candidates and given chains: they are contradictory"
        )
    units = [
        (name, p.cells, lambda m, x, name=name, p=p: _post(m, x, name, p))
        for name, p in step.posters
    ]
    units += [
        (
            f"given chain {k}",
            tuple(dict.fromkeys(chain.cells)),
            lambda m, x, chain=chain: _post_chain(m, x, chain),
        )
        for k, chain in enumerate(step.given, 1)
    ]

    log = []
    fixes = claim.fixes(candidates)
    if fixes is not None:
        for cell, digit in fixes:
            remaining = {c: set(d) for c, d in candidates.items()}
            others = tuple(sorted(remaining[cell] - {digit}))
            remaining[cell] = {digit}
            log.append(Elimination("negated claim", cell, others))
            if not step.propagate(remaining, units, log):
                return PropagationResult(False, tuple(log))
        return PropagationResult(True, tuple(log))

    units.append(
        (
            "negated claim",
            tuple(dict.fromkeys(claim.claim_cells())),
            claim.post_negation,
        )
    )
    remaining = {c: set(d) for c, d in candidates.items()}
    return PropagationResult(step.propagate(remaining, units, log), tuple(log))
