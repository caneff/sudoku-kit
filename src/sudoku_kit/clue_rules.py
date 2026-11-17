"""Per-clue rule functions: each takes one clue of a rules file and returns the
`step_prover.Poster` that posts it, the shape the step prover's registry takes.

A clue is a dict with an `id`, a `rule` (a key of `RULES`), its `cells` as
[row, column] pairs counted from 0, and its `values`. `poster(clue)` picks the
rule function by `rule`.

The logic is copied from the archived gridfind's rule layers (c01723c):
`pair_difference.differs_by`, `pair_ratio.ratio_of`, `thermo`, and `line`'s
`_whisper`, `_renban` and `_lockout`, without gridfind's engine,
doubler or Schrodinger value reads. A line rule's `cells` are in path order
(a thermo's bulb first; a lockout line's two ends first and last).
Rule types are added as the solve guide's test set needs them.

The line rules post only comparisons between the cells' variables, so they
need no board size: a lockout's smallest end gap is the clue's value (gridfind
derived it from the board, size // 2), and a whisper's smallest step is its
value.
"""

import itertools

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


def _line(clue, values):
    """The clue's path of two or more cells, refusing any other shape and any
    count of values but `values`."""
    cells = [tuple(cell) for cell in clue["cells"]]
    if len(cells) < 2 or len(clue["values"]) != values:
        raise ValueError(
            f"clue {clue['id']!r} ({clue['rule']}) needs two or more cells and "
            f"{values} value(s), got cells {clue['cells']} and values "
            f"{clue['values']}"
        )
    return cells


def _climb(clue, strict):
    cells = _line(clue, 0)

    def post(m, x):
        for a, b in itertools.pairwise(cells):
            m.Add(x[a] < x[b] if strict else x[a] <= x[b])

    return Poster(tuple(cells), post)


def thermo(clue):
    """Digits strictly rise from the bulb, the first cell, along the path."""
    return _climb(clue, strict=True)


def slow_thermo(clue):
    """Digits never fall from the bulb, the first cell, along the path."""
    return _climb(clue, strict=False)


def renban(clue):
    """The path's digits are all different and, sorted, consecutive. Posted as
    all-different plus every pair within n - 1 of each other: n distinct
    digits spanning at most n - 1 are consecutive."""
    cells = _line(clue, 0)

    def post(m, x):
        m.AddAllDifferent([x[c] for c in cells])
        for i, a in enumerate(cells):
            for b in cells[i + 1 :]:
                m.Add(x[a] - x[b] <= len(cells) - 1)
                m.Add(x[b] - x[a] <= len(cells) - 1)

    return Poster(tuple(cells), post)


def _apart(m, a, b, k, name):
    """Post |a - b| >= k, with one bool saying which of the two is larger."""
    s = m.NewBoolVar(name)
    m.Add(a - b >= k).OnlyEnforceIf(s)
    m.Add(b - a >= k).OnlyEnforceIf(s.Not())


def whisper(clue):
    """Every two neighbours on the path differ by at least the clue's value:
    4 on a Dutch whispers line, 5 on a German one."""
    cells = _line(clue, 1)
    k = clue["values"][0]

    def post(m, x):
        for i, (a, b) in enumerate(itertools.pairwise(cells)):
            _apart(m, x[a], x[b], k, f"{clue['id']}.gap{i}")

    return Poster(tuple(cells), post)


def lockout(clue):
    """The path's two ends differ by at least the clue's value, and every cell
    between them is strictly outside the closed range of the ends' digits,
    equal to neither. Outside is below both ends or above both, so which end is
    larger does not matter. A two-cell path still checks the gap."""
    cells = _line(clue, 1)
    k = clue["values"][0]

    def post(m, x):
        a, b = x[cells[0]], x[cells[-1]]
        _apart(m, a, b, k, f"{clue['id']}.gap")
        for i, cell in enumerate(cells[1:-1]):
            below = m.NewBoolVar(f"{clue['id']}.{i}.below")
            above = m.NewBoolVar(f"{clue['id']}.{i}.above")
            for end in (a, b):
                m.Add(x[cell] < end).OnlyEnforceIf(below)
                m.Add(x[cell] > end).OnlyEnforceIf(above)
            m.AddBoolOr([below, above])

    return Poster(tuple(cells), post)


RULES = {
    "difference": difference,
    "ratio": ratio,
    "thermo": thermo,
    "slow_thermo": slow_thermo,
    "renban": renban,
    "whisper": whisper,
    "lockout": lockout,
}


def poster(clue):
    """The `Poster` for `clue`, from the rule function its `rule` names."""
    if clue["rule"] not in RULES:
        raise ValueError(
            f"clue {clue['id']!r} has rule {clue['rule']!r}, not one of {sorted(RULES)}"
        )
    return RULES[clue["rule"]](clue)
