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

from sudoku_kit.cpsat import SOLVED, UNKNOWN, check_valid, forbid, solver

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


# A claim answers `claim_cells()`, the cells it names; `probes(candidates)`,
# one function per solve it needs, each posting that solve's negation; and
# `fixes(candidates)`, the (cell, digit) each propagation run fixes, or None
# when the claim fails in one solve, which `post_negation(m, x)` then posts.
# `fixes()` returns None exactly when the claim has `post_negation`, which
# `propagation` relies on.


class Chain(NamedTuple):
    """A rising chain: cells[0] < cells[1] < ..."""

    cells: tuple[Cell, ...]

    def claim_cells(self):
        return list(self.cells)

    def fixes(self, candidates):
        return None

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


def _step(candidates, registry, names, claim, given, *, time_limit, workers):
    if not isinstance(claim, Chain | Place | Either):
        raise ValueError(f"unknown claim {claim!r}: expected Chain, Place or Either")
    for cell, digits in candidates.items():
        if not digits:
            raise ValueError(f"cell {cell} has no candidates")
    named = []
    for name in names:
        if name not in registry:
            raise ValueError(f"constraint {name!r} is not in the registry")
        _check_cells(registry[name].cells, candidates, f"constraint {name!r}")
        named.append((name, registry[name]))
    chains = []
    for k, chain in enumerate(given, 1):
        _check_cells(chain.cells, candidates, "a given chain")
        chains.append((f"given chain {k}", _chain_poster(chain)))
    _check_cells(claim.claim_cells(), candidates, "the claim")
    return Step(candidates, tuple(named), tuple(chains), claim, time_limit, workers)


def _post(m, x, name, poster):
    # A poster sees only the cells it declares, so one that reaches for
    # another fails here instead of leaving it out of the witness. Only a
    # board cell the poster did not declare is relabelled; any other KeyError
    # is the poster's own bug.
    try:
        poster.post(m, {c: x[c] for c in poster.cells})
    except KeyError as e:
        cell = e.args[0] if e.args else None
        if not (isinstance(cell, tuple) and cell in x and cell not in poster.cells):
            raise
        raise ValueError(
            f"constraint {name!r} uses cell {cell}, which it does not declare"
        ) from e


def _post_chain(m, x, chain):
    for left, right in pairwise(chain.cells):
        m.Add(x[left] < x[right])


def _chain_poster(chain):
    return Poster(
        tuple(dict.fromkeys(chain.cells)), lambda m, x: _post_chain(m, x, chain)
    )


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
    (name, `Poster`) pairs, the given `chains` as the same kind of pair, the
    `claim`, and the limits every solve of it runs under."""

    candidates: Mapping[Cell, Collection[int]]
    named: tuple[tuple[str, Poster], ...]
    chains: tuple[tuple[str, Poster], ...]
    claim: Chain | Place | Either
    time_limit: float
    workers: int

    def _without(self, pair):
        """This step with the named constraint `pair` left out."""
        return replace(self, named=tuple(p for p in self.named if p is not pair))

    def shown(self):
        """The cells a witness carries: those of a named constraint, the claim
        or a given chain."""
        shown = {c for _, p in self.named for c in p.cells}
        shown.update(self.claim.claim_cells())
        shown.update(c for _, p in self.chains for c in p.cells)
        return shown

    def _run(self, m):
        s = solver(self.time_limit, workers=self.workers)
        status = s.Solve(m)
        check_valid(status, m)
        return status, s

    def _solve(self, probe):
        """Solve the step with `probe` posted; a None probe asks whether any grid is left."""
        m = cp_model.CpModel()
        x = _variables(m, self.candidates)
        for name, p in (*self.named, *self.chains):
            _post(m, x, name, p)
        if probe is not None:
            probe(m, x)
        return (*self._run(m), x)

    def _first_grid(self, probes):
        """The first probe's grid; one timed-out probe makes the answer UNKNOWN."""
        timed_out = False
        for probe in probes:
            status, s, x = self._solve(probe)
            if status in SOLVED:
                return status, s, x
            timed_out = timed_out or status == UNKNOWN
        return (UNKNOWN if timed_out else cp_model.INFEASIBLE), None, None

    def _backing(self, status):
        # The solves whose infeasibility backs `status`: the claim's probes on
        # "proved", the solve with no negation on "contradictory".
        return self.claim.probes(self.candidates) if status == "proved" else [None]

    def prove(self):
        status, s, x = self._first_grid(self._backing("proved"))
        if status in SOLVED:
            shown = sorted(self.shown())
            return ProofResult("refuted", {c: s.Value(x[c]) for c in shown})
        if status == UNKNOWN:
            return ProofResult("timeout")
        # Every probe is infeasible. That proves the claim only if some grid is
        # left at all; none means the named constraints contradict themselves or
        # the candidates, and would "prove" any claim.
        status, _, _ = self._first_grid(self._backing("contradictory"))
        if status == UNKNOWN:
            return ProofResult("timeout")
        return ProofResult(
            "contradictory" if status == cp_model.INFEASIBLE else "proved"
        )

    def irreducible(self):
        result = self.prove()
        if result.status in ("refuted", "timeout"):
            return IrreducibleResult(result.status, None, result.witness)
        probes = self._backing(result.status)

        kept, checked = self, True
        for pair in self.named:
            trial = kept._without(pair)
            status, _, _ = trial._first_grid(probes)
            if status == cp_model.INFEASIBLE:
                kept = trial
            checked = checked and status != UNKNOWN
        return IrreducibleResult(
            result.status, tuple(n for n, _ in kept.named), None, checked
        )

    def propagation(self):
        status, _, _ = self._solve(None)
        if status == UNKNOWN:
            raise TimeoutError(
                f"CP-SAT hit the {self.time_limit}s limit checking that the named "
                "constraints admit a grid; no verdict"
            )
        if status == cp_model.INFEASIBLE:
            raise ValueError(
                f"the named constraints {[name for name, _ in self.named]} admit "
                "no grid with these candidates and given chains: they are "
                "contradictory"
            )
        units = [*self.named, *self.chains]

        log = []
        fixes = self.claim.fixes(self.candidates)
        if fixes is not None:
            for cell, digit in fixes:
                remaining = {c: set(d) for c, d in self.candidates.items()}
                others = tuple(sorted(remaining[cell] - {digit}))
                remaining[cell] = {digit}
                log.append(Elimination("negated claim", cell, others))
                if not _propagate(self, remaining, units, log):
                    return PropagationResult(False, tuple(log))
            return PropagationResult(True, tuple(log))

        claim = self.claim
        units.append(
            (
                "negated claim",
                Poster(tuple(dict.fromkeys(claim.claim_cells())), claim.post_negation),
            )
        )
        remaining = {c: set(d) for c, d in self.candidates.items()}
        return PropagationResult(_propagate(self, remaining, units, log), tuple(log))


def _unsupported(step, by, poster, candidates):
    cells = poster.cells
    supported = {c: set() for c in cells}
    for cell in cells:
        for digit in sorted(candidates[cell] - supported[cell]):
            m = cp_model.CpModel()
            x = _variables(m, {c: candidates[c] for c in cells})
            poster.post(m, x)
            m.Add(x[cell] == digit)
            status, s = step._run(m)
            if status in SOLVED:
                for c in cells:
                    supported[c].add(s.Value(x[c]))
            elif status == UNKNOWN:
                raise TimeoutError(
                    f"CP-SAT hit the {step.time_limit}s limit testing "
                    f"{digit} in {cell} against {by!r}; no verdict"
                )
    return {
        c: tuple(sorted(candidates[c] - supported[c]))
        for c in cells
        if candidates[c] - supported[c]
    }


def _propagate(step, candidates, units, log):
    changed = True
    while changed:
        changed = False
        for by, poster in units:
            removed = _unsupported(step, by, poster, candidates)
            for cell, digits in removed.items():
                candidates[cell] -= set(digits)
                log.append(Elimination(by, cell, digits))
                changed = True
            if any(not candidates[c] for c in poster.cells):
                return True
    return False


def prove(
    candidates: Mapping[Cell, Collection[int]],
    registry: Mapping[str, Poster],
    names: Iterable[str],
    claim: Chain | Place | Either,
    *,
    given: Iterable[Chain] = (),
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
    that is not a `Chain`, `Place` or `Either`, or a model CP-SAT rejects.
    """
    return _step(
        candidates,
        registry,
        names,
        claim,
        given,
        time_limit=time_limit,
        workers=workers,
    ).prove()


def irreducible(
    candidates: Mapping[Cell, Collection[int]],
    registry: Mapping[str, Poster],
    names: Iterable[str],
    claim: Chain | Place | Either,
    *,
    given: Iterable[Chain] = (),
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
    return _step(
        candidates,
        registry,
        names,
        claim,
        given,
        time_limit=time_limit,
        workers=workers,
    ).irreducible()


def propagation(
    candidates: Mapping[Cell, Collection[int]],
    registry: Mapping[str, Poster],
    names: Iterable[str],
    claim: Chain | Place | Either,
    *,
    given: Iterable[Chain] = (),
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
    return _step(
        candidates,
        registry,
        names,
        claim,
        given,
        time_limit=time_limit,
        workers=workers,
    ).propagation()
