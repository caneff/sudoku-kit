"""Per-clue rule functions: each takes one clue of a rules file and returns the
`step_prover.Poster` that posts it, the shape the step prover's registry takes.

A clue is a dict with an `id`, a `rule` (a key of `RULES`), its `cells` as
[row, column] pairs counted from 0, and its `values`. `poster(clue)` picks the
rule function by `rule`.

The logic is copied from the archived gridfind's rule layers (c01723c):
`pair_difference.differs_by` and `pair_ratio.ratio_of`, without gridfind's
engine, doubler or Schrodinger value reads. Rule types are added as the solve
guide's test set needs them.
"""

from sudoku_kit.step_prover import Poster


def _pair(clue):
    """The clue's two cells and its one value, refusing any other shape."""
    cells = [tuple(cell) for cell in clue["cells"]]
    if len(cells) != 2 or len(clue["values"]) != 1:
        raise ValueError(
            f"clue {clue['id']!r} ({clue['rule']}) needs two cells and one value, "
            f"got cells {clue['cells']} and values {clue['values']}"
        )
    return cells[0], cells[1], clue["values"][0]


def difference(clue):
    """The two cells' digits differ by exactly the clue's value, either cell
    the larger: a white Kropki dot reads as difference 1."""
    a, b, k = _pair(clue)

    def post(m, x):
        d = m.NewIntVar(0, k, f"{clue['id']}.diff")
        m.AddAbsEquality(d, x[a] - x[b])
        m.Add(d == k)

    return Poster((a, b), post)


def ratio(clue):
    """One cell's digit is the clue's value times the other's, either cell the
    larger: a black Kropki dot reads as ratio 2."""
    a, b, k = _pair(clue)

    def post(m, x):
        s = m.NewBoolVar(f"{clue['id']}.ratio")
        m.Add(x[a] == k * x[b]).OnlyEnforceIf(s)
        m.Add(x[b] == k * x[a]).OnlyEnforceIf(s.Not())

    return Poster((a, b), post)


RULES = {"difference": difference, "ratio": ratio}


def poster(clue):
    """The `Poster` for `clue`, from the rule function its `rule` names."""
    if clue["rule"] not in RULES:
        raise ValueError(
            f"clue {clue['id']!r} has rule {clue['rule']!r}, not one of {sorted(RULES)}"
        )
    return RULES[clue["rule"]](clue)
