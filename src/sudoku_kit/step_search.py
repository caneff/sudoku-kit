"""The step search: a solve path of steps, each proved by the step prover from
the constraints it names, saved as a step record (spec #106).

From the current candidates the search tries claims -- placements and
eliminations, each a `Place` -- and takes one step at a time:

1. One named constraint alone. For each house and clue, each digit of each of
   its cells is tried as an elimination with `prove` from that constraint
   only; the digits it removes from one cell make one claim, a placement when
   one digit is left. A constraint whose cells' candidates have not changed
   since it was last tried is not tried again.
2. When no constraint alone removes a digit: rings around each unsolved cell.
   Ring 0 is the constraints on the cell; ring k + 1 adds those on any cell of
   ring k. Every placement and single-digit elimination of every unsolved cell
   is proved from its ring, and each proved one is reduced to its irreducible
   set, the outer rings' constraints offered for removal first. The first ring
   at which any claim proves gives the step: the smallest irreducible set
   found there, a placement before an elimination. The last ring holds every
   constraint, so there is no cap on a step's size; a step naming more than 3
   is hard. This tier runs only when no constraint alone removes a digit, so
   no step here names fewer than 2, and the first claim reduced to 2 is taken
   without trying the rest.

A proof's verdict depends only on the candidates of the cells its claim and
named constraints touch, so each verdict is kept and reused until one of
those cells' candidates changes.

Ties go to the earlier constraint in the registry and the earlier cell, so a
run and a resumed run take the same path. Each proof runs under the proof
limit; one that times out is recorded and the search goes on without it. When
no claim proves at the last ring, the search records a stuck point, the grid
and candidates there, and stops: it never guesses. A hint, a claim and the
constraints it names, is proved with `prove` and appended as a step when
proved; the search then goes on from it.

The step record is a JSON object:

- `steps`: each `{"claim", "named", "hard", "by"}`, `by` "search" or "hint".
  A claim is `{"cell": [row, column], "digits": [...]}` (the cell keeps only
  those digits), `{"chain": [cells]}` (a rising chain, assumed by every later
  step as a given chain) or `{"either": [[[cell, digit], ...], ...]}`.
- `timeouts`: each `{"step", "claim", "named"}`, `step` the index of the step
  being searched for when the proof timed out, each proof once per step.
- `stuck`: null, or `{"grid", "candidates", "outside", "timeouts"}`: n rows of
  digits, 0 where the cell is unsolved; n rows of each cell's candidate list;
  each outside cell as `{"cell", "candidates"}`; and how many proofs timed out
  while searching for the next step. Outside cells are searched like grid
  cells, and a path is finished only when they are solved too.

A stuck point with no timeouts is a real one: every claim tried failed to
prove. One with timeouts is no verdict (a timeout never is): the run ends
"timeout", and a higher proof limit may find the next step.

A run resumes from a record only after proving every step in it again from
its named constraints on the rules file it is given, so a record left by
another rules file, or by this one before a clue was changed, is refused
rather than replayed.
"""

import json
from pathlib import Path

from sudoku_kit import rules_file
from sudoku_kit.step_prover import Chain, Either, Place, irreducible, prove

HARD = 3


def claim_to_json(claim):
    if isinstance(claim, Place):
        return {"cell": list(claim.cell), "digits": sorted(claim.digits)}
    if isinstance(claim, Chain):
        return {"chain": [list(c) for c in claim.cells]}
    return {"either": [[[list(c), d] for c, d in p.items()] for p in claim.patterns]}


def claim_from_json(data):
    """The claim `data` describes, as `claim_to_json` writes it."""
    if not isinstance(data, dict):
        raise ValueError(f"claim {data!r} is not a JSON object")
    try:
        if "cell" in data:
            return Place(tuple(data["cell"]), tuple(data["digits"]))
        if "chain" in data:
            return Chain(tuple(tuple(c) for c in data["chain"]))
        if "either" in data:
            return Either(tuple({tuple(c): d for c, d in p} for p in data["either"]))
    except (KeyError, TypeError, ValueError) as e:
        raise ValueError(f"claim {data!r} is malformed: {e}") from e
    raise ValueError(f"claim {data!r} has none of cell, chain or either")


def new_record():
    return {"steps": [], "timeouts": [], "stuck": None}


def load_record(path):
    """The step record at `path`, or a new one when there is none."""
    path = Path(path)
    if not path.exists():
        return new_record()
    try:
        record = json.loads(path.read_text())
    except ValueError as e:
        raise ValueError(f"{path} is not JSON: {e}") from e
    if not isinstance(record, dict) or not isinstance(record.get("steps"), list):
        raise ValueError(f"{path} is not a step record: no steps list")
    return record


def save_record(record, path):
    """Write `record` to `path` whole: a run killed mid-write leaves the last
    saved record, never half of one."""
    path = Path(path)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(record, indent=1) + "\n")
    tmp.replace(path)


class State:
    """The candidates and given chains after a list of steps."""

    def __init__(self, rules):
        n = rules["size"]
        self.size = n
        # Outside cells are variables too; leaving them out would let a proof
        # skip a clue's digit beside the grid.
        self.candidates = {
            cell: frozenset(range(1, n + 1)) for cell in rules_file.cells(rules)
        }
        for given in rules["givens"]:
            self.candidates[tuple(given["cell"])] = frozenset([given["digit"]])
        self.given = []

    def apply(self, claim):
        if isinstance(claim, Place):
            self.candidates[claim.cell] &= frozenset(claim.digits)
        elif isinstance(claim, Chain):
            self.given.append(claim)

    def solved(self):
        return all(len(d) == 1 for d in self.candidates.values())

    def snapshot(self):
        n = self.size
        rows = [[sorted(self.candidates[r, c]) for c in range(n)] for r in range(n)]
        on_grid = {(r, c) for r in range(n) for c in range(n)}
        return {
            "grid": [[d[0] if len(d) == 1 else 0 for d in row] for row in rows],
            "candidates": rows,
            "outside": [
                {"cell": list(cell), "candidates": sorted(digits)}
                for cell, digits in sorted(self.candidates.items())
                if cell not in on_grid
            ],
        }


def replay(rules, record, proof_limit):
    """The `State` after every step of `record`, each step proved again with
    `prove` from its named constraints first. Raises ValueError for a step
    these rules do not prove, and TimeoutError for one whose proof timed out."""
    state = State(rules)
    named = rules_file.registry(rules)
    for k, step in enumerate(record["steps"], 1):
        claim = claim_from_json(step["claim"])
        try:
            result = prove(
                state.candidates,
                named,
                step["named"],
                claim,
                given=state.given,
                time_limit=proof_limit,
            )
        except (KeyError, TypeError, ValueError) as e:
            raise ValueError(
                f"step {k} of the step record does not fit this rules file: {e}"
            ) from e
        if result.status == "timeout":
            raise TimeoutError(
                f"proving step {k} of the step record again hit the "
                f"{proof_limit}s proof limit; no verdict"
            )
        if result.status != "proved":
            raise ValueError(
                f"step {k} of the step record is {result.status} on this rules "
                f"file: the record was searched on another rules file, or "
                f"before a clue changed; remove it or use a new directory"
            )
        state.apply(claim)
    return state


class Search:
    """One run of the step search over `rules`, extending `record` in place
    and saving it to `path` after every step."""

    def __init__(self, rules, record, path, proof_limit):
        self.registry = rules_file.registry(rules)
        self.order = list(self.registry)
        self.record = record
        self.path = path
        self.limit = proof_limit
        self.state = replay(rules, record, proof_limit)
        self.cache = {}
        self.verdicts = {}
        self.step_timeouts = set()

    def _key(self, kind, claim, named):
        cells = set(claim.claim_cells())
        for name in named:
            cells.update(self.registry[name].cells)
        cells.update(c for chain in self.state.given for c in chain.cells)
        held = tuple((c, self.state.candidates[c]) for c in sorted(cells))
        return kind.__name__, claim, tuple(named), tuple(self.state.given), held

    def _verdict(self, kind, claim, named):
        """`prove` or `irreducible` (`kind`) on the current candidates, run
        once per key; a timeout is recorded each time it is met."""
        key = self._key(kind, claim, named)
        if key not in self.verdicts:
            self.verdicts[key] = kind(
                self.state.candidates,
                self.registry,
                named,
                claim,
                given=self.state.given,
                time_limit=self.limit,
            )
        result = self.verdicts[key]
        if result.status == "timeout":
            self._timed_out(claim, named)
        return result

    def _prove(self, claim, named):
        return self._verdict(prove, claim, named).status == "proved"

    def _timed_out(self, claim, named):
        if (claim, tuple(named)) in self.step_timeouts:
            return
        self.step_timeouts.add((claim, tuple(named)))
        self.record["timeouts"].append(
            {
                "step": len(self.record["steps"]),
                "claim": claim_to_json(claim),
                "named": list(named),
            }
        )

    def _removed_by(self, name):
        """{cell: digits} that constraint `name` alone removes, each digit
        proved gone by `prove` from `name` only."""
        cells = self.registry[name].cells
        key = (
            name,
            tuple(self.state.candidates[c] for c in cells),
            len(self.state.given),
        )
        if key not in self.cache:
            removed = {}
            for cell in cells:
                digits = self.state.candidates[cell]
                if len(digits) == 1:
                    continue
                gone = [
                    d
                    for d in sorted(digits)
                    if self._prove(Place(cell, digits - {d}), [name])
                ]
                if gone:
                    removed[cell] = digits - set(gone)
            self.cache[key] = removed
        return self.cache[key]

    def _single(self):
        """The best step one constraint alone gives, or None."""
        found = []
        for rank, name in enumerate(self.order):
            for cell, keep in self._removed_by(name).items():
                found.append((len(keep) != 1, rank, cell, Place(cell, keep), name))
        if not found:
            return None
        *_, claim, name = min(found, key=lambda f: f[:3])
        # The claim combines one-digit eliminations; prove it whole.
        if not self._prove(claim, [name]):
            return None
        return claim, (name,)

    def _rings(self, cell):
        """Each ring's constraints around `cell`, outer rings' names first."""
        rings, seen, reached = [], [], {cell}
        while True:
            ring = [
                n
                for n in self.order
                if n not in seen and reached & set(self.registry[n].cells)
            ]
            if not ring:
                return rings
            seen = ring + seen
            rings.append(list(seen))
            for n in ring:
                reached.update(self.registry[n].cells)

    def _claims(self, cell):
        """Each placement in `cell`, then each single-digit elimination."""
        digits = self.state.candidates[cell]
        for d in sorted(digits):
            yield Place(cell, (d,))
        if len(digits) > 2:
            for d in sorted(digits):
                yield Place(cell, tuple(sorted(digits - {d})))

    def _ringed(self):
        """The best step from the rings around each unsolved cell, or None."""
        unsolved = [c for c, d in self.state.candidates.items() if len(d) > 1]
        rings = {cell: self._rings(cell) for cell in unsolved}
        for radius in range(max(len(r) for r in rings.values())):
            found = []
            for cell in unsolved:
                if radius >= len(rings[cell]):
                    continue
                named = rings[cell][radius]
                for claim in self._claims(cell):
                    if not self._prove(claim, named):
                        continue
                    result = self._verdict(irreducible, claim, named)
                    if result.status != "proved":
                        continue
                    if len(result.irreducible_set) == 2:
                        return claim, result.irreducible_set
                    found.append(
                        (
                            len(result.irreducible_set),
                            len(claim.digits) != 1,
                            cell,
                            claim,
                            result.irreducible_set,
                        )
                    )
            if found:
                *_, claim, named = min(found, key=lambda f: f[:3])
                return claim, named
        return None

    def take(self, claim, named, by):
        """Append a proved step and save the record."""
        self.state.apply(claim)
        self.record["steps"].append(
            {
                "claim": claim_to_json(claim),
                "named": list(named),
                "hard": len(named) > HARD,
                "by": by,
            }
        )
        self.record["stuck"] = None
        self.step_timeouts = set()
        save_record(self.record, self.path)

    def check_hint(self, claim, named):
        """Raise ValueError when the hint `claim` from `named` cannot be tried:
        no named constraint, a name that is not a house or clue, or a cell
        not on the board."""
        if not named:
            raise ValueError("a hint names at least one constraint it uses")
        unknown = [name for name in named if name not in self.registry]
        if unknown:
            raise ValueError(f"the hint names {unknown}, not a house or clue")
        off = [c for c in claim.claim_cells() if c not in self.state.candidates]
        if off:
            raise ValueError(f"the hint names cells {off}, not on the board")

    def hint(self, claim, named):
        """Prove `claim` from the constraints `named`; when proved, append it
        as a step by "hint". Returns `prove`'s result. Raises `check_hint`'s
        ValueErrors."""
        self.check_hint(claim, named)
        result = prove(
            self.state.candidates,
            self.registry,
            named,
            claim,
            given=self.state.given,
            time_limit=self.limit,
        )
        if result.status == "proved":
            self.take(claim, named, by="hint")
        return result

    def run(self, max_steps=None):
        """Search until solved, stuck, or `max_steps` steps taken this run.
        Returns "solved", "stopped", "stuck" (a stuck point, no proof timed
        out) or "timeout" (a stuck point where some proof timed out)."""
        taken = 0
        while not self.state.solved():
            if max_steps is not None and taken >= max_steps:
                save_record(self.record, self.path)
                return "stopped"
            step = self._single() or self._ringed()
            if step is None:
                timeouts = len(self.step_timeouts)
                self.record["stuck"] = self.state.snapshot() | {"timeouts": timeouts}
                save_record(self.record, self.path)
                return "timeout" if timeouts else "stuck"
            self.take(*step, by="search")
            taken += 1
        save_record(self.record, self.path)
        return "solved"
