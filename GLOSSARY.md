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
One claim in a solve path, proved from the candidates and a stated set of
constraints. The guide groups steps into deductions.
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

### Solve guide

**Solve guide**:
A short document for a stuck solver showing the key ideas of one puzzle, the
break-in first, each drawn on its own grid, with the fill between them summed
up in one sentence per stretch. The `/solve-guide` skill writes its words as a
guide file; the library checks that file against the step record and draws
the page.
_Avoid_: Walkthrough, solution, write-up

**Guide file**:
The JSON file the `/solve-guide` skill writes and the library draws: an
ordered list of key ideas and fill stretches, each a run of steps with its
words, together covering every step of the step record once, in order. Its
format is `docs/guide-file.md`.
_Avoid_: Guide JSON, script, outline

**Deduction**:
A group of steps that name the same constraints, which the skill reads as
one candidate idea. Steps that are not adjacent join one deduction when no step between
them changed a cell it uses; it sits at its last step's position. Grouping is
computed from the step record, which keeps one entry per step.
_Avoid_: Move

**Key idea**:
A run of consecutive steps the skill chooses as one move a solver would name,
with its heading and paragraphs, drawn on its own numbered grid. The library
numbers key ideas 1..N with no gaps; the skill may flag one as the break-in.
_Avoid_: Key step, main step

**Supposition**:
A key idea's argument "suppose this cell were X", drawn as a second grid
beside the idea's own: the assumed digit, the digits it forces in order and
the cells where it clashes. The assumed digit is one the idea's steps
eliminate; the guide file names it, and the library refuses one that does not
fit the step record.
_Avoid_: Contradiction, bifurcation, what-if

**Early removal**:
A digit a key idea's words rule out of a cell before the step record does,
named in the guide file. The library refuses one that is not a candidate there
after the idea's steps, or that is the cell's solution digit; it strikes the
digit on the idea's grid and leaves it off every later grid.
_Avoid_: Extra elimination, manual elimination

**Fill**:
A run of steps between key ideas, shown as one sentence the skill writes,
with one plain line per step in a collapsed list: the claim, then its named
constraints in words, never a clue id. Fill carries no numbers.
_Avoid_: Singles, routine steps

**Rules file**:
The one JSON description of a puzzle every solve-guide stage reads: grid size,
regions, givens, an optional solution, and its clues. Importers write it.
_Avoid_: Puzzle file, puzzle JSON, spec

**Clue**:
One drawn rule of a puzzle in a rules file (a dot, a line, a cage), with a
stable id, a rule type, its cells and its values. Each clue is one named
constraint a step can use; rows, columns and regions are the others.
_Avoid_: Constraint (for one drawn mark), element, shape

**Outside cell**:
A cell one step off the grid, beside the end of a row or column, that a clue
names: a skyscraper's or numbered room's clue digit, or an arrow's bulb. A
variable with digits 1..n that no house holds. A rules file's
`solution_outside` stores its solved digit.
_Avoid_: Border cell, ring cell, clue cell

**Hole**:
A cell of a rules file's n x n grid that is not part of the puzzle, as on a
diamond-shaped board drawn on a square sheet. It is no variable, sits in no
house and carries no given or clue; a rules file's `holes` lists them.
_Avoid_: Blank cell, missing cell

**Step record**:
The saved list of steps a solve-path search has made so far, each with its
claim and named constraints, plus any proofs that timed out. A stopped search
resumes from it.
_Avoid_: Log, trace, path file

**Stuck point**:
Where a solve-path search stops because no claim it tried is proved, recorded
with the grid and candidates there. Never a guess.
_Avoid_: Dead end, failure

**Hard step**:
A step whose irreducible set holds more than 3 named constraints.
_Avoid_: Difficult step, advanced technique
