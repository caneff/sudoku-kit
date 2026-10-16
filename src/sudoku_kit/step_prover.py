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
Status = Literal["proved", "refuted", "contradictory", "timeout"]


class ProofResult(NamedTuple):
    """`status` is "proved", "refuted", "contradictory" or "timeout". `witness` is set only on
    "refuted": a {(row, column): digit} grid over the cells that appear in a
    named constraint, the claim or a given chain. Other cells carry no meaning
    and are left out."""

    status: Status
    witness: dict[Cell, int] | None = None


class IrreducibleResult(NamedTuple):
    """`status` as `prove` gives it. `names` is the irreducible set, in the
    order given: on "proved", named constraints that still prove the claim
    with none of them removable; on "contradictory", named constraints that
    conflict with each other, the candidates and the given chains; None on
    "refuted" and "timeout". `witness` is set only on "refuted", as `prove`
    sets it. `irreducible_checked` is False when a deletion trial timed out
    and kept its constraint, so `names` still holds but may not be
    irreducible; it is False too when there is no set."""

    status: Status
    names: tuple[str, ...] | None = None
    witness: dict[Cell, int] | None = None
    irreducible_checked: bool = False


class Elimination(NamedTuple):
    """`by` removed `digits` from `cell`. `by` is a constraint's name,
    "given chain <k>" for the k-th given chain counting from 1, or "negated
    claim"; for a `Place` the negated claim fixes the cell to one removed
    digit, and its entry opens each run."""

    by: str
    cell: Cell
    digits: tuple[int, ...]


class PropagationResult(NamedTuple):
    """`refutes` is whether propagation alone emptied a cell, in every run
    for a `Place`. `log` is every elimination in the order made."""

    refutes: bool
    log: tuple[Elimination, ...]


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


def _prepare(candidates, registry, names, claim, given):
    """Check the input and return ([(name, poster)], [given chain], shown
    cells). Raises the ValueErrors `prove` lists."""
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
    return posters, given, shown


def _post(m, x, name, poster):
    # A poster sees only the cells it declares, so one that reaches for
    # another fails here instead of leaving it out of the witness.
    try:
        poster.post(m, {c: x[c] for c in poster.cells})
    except KeyError as e:
        raise ValueError(
            f"constraint {name!r} uses cell {e.args[0]}, which it does not declare"
        ) from None


def _variables(m, candidates):
    return {
        cell: m.NewIntVarFromDomain(
            cp_model.Domain.FromValues(sorted(set(digits))), f"x{cell}"
        )
        for cell, digits in candidates.items()
    }


def _solve(candidates, posters, given, probe, time_limit, workers):
    """One solve of the candidates, `posters` and `given` chains, with `probe`
    (or nothing, when None) posted. Returns (status, solver, x); raises
    ValueError on a model CP-SAT rejects."""
    m = cp_model.CpModel()
    x = _variables(m, candidates)
    for name, p in posters:
        _post(m, x, name, p)
    for chain in given:
        for left, right in pairwise(chain.cells):
            m.Add(x[left] < x[right])
    if probe is not None:
        probe(m, x)
    s = solver(time_limit)
    s.parameters.num_workers = workers
    status = s.Solve(m)
    if status not in (*SOLVED, UNKNOWN, cp_model.INFEASIBLE):
        names_posted = [name for name, _ in posters]
        raise ValueError(
            f"CP-SAT rejected the model for constraints {names_posted}: "
            f"{cp_model.CpSolver().StatusName(status)}"
        )
    return status, s, x


def _prove(candidates, posters, given, claim, shown, time_limit, workers):
    timed_out = False
    for probe in _probes(candidates, claim):
        status, s, x = _solve(candidates, posters, given, probe, time_limit, workers)
        if status in SOLVED:
            return ProofResult("refuted", {c: s.Value(x[c]) for c in sorted(shown)})
        timed_out = timed_out or status == UNKNOWN
    if timed_out:
        return ProofResult("timeout")
    # Every probe is infeasible. That proves the claim only if some grid is
    # left at all; none means the named constraints contradict themselves or
    # the candidates, and would "prove" any claim.
    status, _, _ = _solve(candidates, posters, given, None, time_limit, workers)
    if status == UNKNOWN:
        return ProofResult("timeout")
    return ProofResult("contradictory" if status == cp_model.INFEASIBLE else "proved")


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
    posters, given, shown = _prepare(candidates, registry, names, claim, given)
    return _prove(candidates, posters, given, claim, shown, time_limit, workers)


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
    posters, given, shown = _prepare(candidates, registry, names, claim, given)
    result = _prove(candidates, posters, given, claim, shown, time_limit, workers)
    if result.status in ("refuted", "timeout"):
        return IrreducibleResult(result.status, None, result.witness)
    probes = _probes(candidates, claim) if result.status == "proved" else [None]

    def verdict(kept):
        """ "infeasible" when every probe is, else "feasible" or "timeout"."""
        timed_out = False
        for probe in probes:
            status, _, _ = _solve(candidates, kept, given, probe, time_limit, workers)
            if status in SOLVED:
                return "feasible"
            timed_out = timed_out or status == UNKNOWN
        return "timeout" if timed_out else "infeasible"

    kept, checked = list(range(len(posters))), True
    for i in range(len(posters)):
        trial = [j for j in kept if j != i]
        outcome = verdict([posters[j] for j in trial])
        if outcome == "infeasible":
            kept = trial
        checked = checked and outcome != "timeout"
    return IrreducibleResult(
        result.status, tuple(posters[j][0] for j in kept), None, checked
    )


def _unsupported(by, cells, post, domains, time_limit, workers):
    """{cell: digits} of `cells` with no completion under `post` alone, from
    the current `domains`. A completion found supports every digit in it, so
    only the digits no completion has used yet are solved for."""
    supported = {c: set() for c in cells}
    for cell in cells:
        for digit in sorted(domains[cell] - supported[cell]):
            if digit in supported[cell]:
                continue
            m = cp_model.CpModel()
            x = _variables(m, {c: domains[c] for c in cells})
            post(m, x)
            m.Add(x[cell] == digit)
            s = solver(time_limit)
            s.parameters.num_workers = workers
            status = s.Solve(m)
            if status in SOLVED:
                for c in cells:
                    supported[c].add(s.Value(x[c]))
            elif status == UNKNOWN:
                raise TimeoutError(
                    f"CP-SAT hit the {time_limit}s limit testing {digit} in "
                    f"{cell} against {by!r}; no verdict"
                )
            elif status != cp_model.INFEASIBLE:
                raise ValueError(
                    f"CP-SAT rejected the model for {by!r}: "
                    f"{cp_model.CpSolver().StatusName(status)}"
                )
    return {
        c: tuple(sorted(domains[c] - supported[c]))
        for c in cells
        if domains[c] - supported[c]
    }


def _propagate(domains, units, log, time_limit, workers):
    """Run each unit alone until none removes a digit. True when one empties
    a cell. Changes `domains` and appends to `log`."""
    changed = True
    while changed:
        changed = False
        for by, cells, post in units:
            removed = _unsupported(by, cells, post, domains, time_limit, workers)
            for cell, digits in removed.items():
                domains[cell] -= set(digits)
                log.append(Elimination(by, cell, digits))
                changed = True
            if any(not domains[c] for c in cells):
                return True
    return False


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
    """Whether one-constraint propagation alone refutes the negated claim.
    Takes `prove`'s arguments and raises its ValueErrors.

    Each named constraint, given chain and the negated claim is taken alone:
    a digit leaves a cell when that one constraint has no completion using
    it, tested by a CP-SAT solve, and the loop repeats until nothing changes.
    The answer is yes when some cell runs out of candidates. A `Place` runs
    the loop once per digit it removes, with the cell fixed to that digit,
    and the answer is yes only when every run empties a cell; the first run
    that does not ends the search. Never changes `candidates`.

    Raises TimeoutError when one support solve spends `time_limit` seconds:
    a timeout is never a verdict.
    """
    posters, given, _ = _prepare(candidates, registry, names, claim, given)
    units = [
        (name, p.cells, lambda m, x, name=name, p=p: _post(m, x, name, p))
        for name, p in posters
    ]
    for k, chain in enumerate(given, 1):

        def rising(m, x, chain=chain):
            for left, right in pairwise(chain.cells):
                m.Add(x[left] < x[right])

        units.append((f"given chain {k}", tuple(dict.fromkeys(chain.cells)), rising))

    log = []
    if isinstance(claim, Place):
        for digit in sorted(set(candidates[claim.cell]) - set(claim.digits)):
            domains = {c: set(d) for c, d in candidates.items()}
            others = tuple(sorted(domains[claim.cell] - {digit}))
            domains[claim.cell] = {digit}
            if others:
                log.append(Elimination("negated claim", claim.cell, others))
            if not _propagate(domains, units, log, time_limit, workers):
                return PropagationResult(False, tuple(log))
        return PropagationResult(True, tuple(log))

    units.append(
        (
            "negated claim",
            tuple(dict.fromkeys(_claim_cells(claim))),
            lambda m, x: _post_negation(m, x, claim),
        )
    )
    domains = {c: set(d) for c, d in candidates.items()}
    return PropagationResult(
        _propagate(domains, units, log, time_limit, workers), tuple(log)
    )
