# sudoku-kit

Shared tools for building, checking and proving sudoku-variant puzzles: the
solver helpers, the SudokuMaker link codec, the uniqueness check and the step
prover.

## Language

### Solving

**Candidates**:
The digits still possible in a cell at a given point in a solve.
_Avoid_: Pencil marks, notes, options

**Step**:
One deduction in a solve path, made from the candidates and a stated set of
constraints.
_Avoid_: Move, technique

**Named constraints**:
The constraints a step says it uses, and the only ones its proof may rely on.
_Avoid_: Premises, rules used

**Claim**:
What a step concludes about the candidates: a rising chain, a cell keeping only
some digits, or at least one of several patterns holding.
_Avoid_: Conclusion, result

**Given chain**:
A rising chain of cells a step takes as already settled, passed beside the
named constraints and never removed from them.
_Avoid_: Assumed order, known chain

**Propagation**:
Removing a digit from a cell because one constraint, taken alone, has no
completion using it, repeated until nothing changes. Each removal is one
**elimination**.
_Avoid_: Constraint propagation, GAC, simple deduction

### Proof outcomes

**Proved**:
The claim holds in every grid allowed by the candidates and the named
constraints.
_Avoid_: Valid, true

**Refuted**:
Some grid allowed by the candidates and the named constraints breaks the claim.
_Avoid_: Invalid, false

**Witness**:
A grid that breaks a claim, shown as the refutation's evidence.
_Avoid_: Counterexample, solution

**Contradictory**:
The candidates, the named constraints and the given chains admit no grid at
all, so every claim would pass; reported instead of proved.
_Avoid_: Unsatisfiable premises, inconsistent

**Irreducible set**:
Named constraints that still give the verdict with none of them removable,
found by one greedy deletion pass. Another set may be shorter.
_Avoid_: Smallest set, minimum set, core
