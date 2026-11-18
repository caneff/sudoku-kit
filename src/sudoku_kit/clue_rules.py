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

The sum and outside-clue rules copy gridfind's `arrow`, `cage` with
`group_sum`, `numbered_rooms` and `offset_adjacency`; gridfind has no skyscraper
or little-killer layer, so those two follow their stated rules. Cells are
[row, column] pairs, and an outside clue's cell is one step off the board (row
or column -1, or n), a variable with digits 1..n like any other. An arrow's
`cells` are its bulb's then its shaft's, its one value the bulb's length (a
pill of two or more reads as a number, first cell most significant). A
skyscraper's and a numbered room's `cells` are the outside cell, then the
line from the clue inward, over a board whose lines are n cells long (a
numbered room's near digit may name any of them).

The line rules post only comparisons between the cells' variables, so they
need no board size: a lockout's smallest end gap is the clue's value (gridfind
derived it from the board, size // 2), and a whisper's smallest step is its
value.
"""

import itertools

from sudoku_kit.step_prover import Poster


def _read(clue, fewest, values, most=None):
    """The clue's cells as tuples, refusing fewer than `fewest`, more than
    `most` (any number when None) and any count of values but `values`."""
    cells = [tuple(cell) for cell in clue["cells"]]
    if (
        len(cells) < fewest
        or (most is not None and len(cells) > most)
        or len(clue["values"]) != values
    ):
        wanted = str(fewest) if most == fewest else f"{fewest} or more"
        raise ValueError(
            f"clue {clue['id']!r} ({clue['rule']}) needs {wanted} cells and "
            f"{values} value(s), got cells {clue['cells']} and values "
            f"{clue['values']}"
        )
    return cells


def _pair(clue):
    """The clue's two cells and its one value, refusing any other shape."""
    a, b = _read(clue, 2, 1, 2)
    return a, b, clue["values"][0]


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


def _climb(clue, strict):
    cells = _read(clue, 2, 0)

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
    cells = _read(clue, 2, 0)

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
    cells = _read(clue, 2, 1)
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
    cells = _read(clue, 2, 1)
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


def arrow(clue):
    """The shaft's digits sum to the bulb: its one value is the bulb's length,
    the first cells; two or more read as a number, first cell most
    significant. The shaft may repeat digits."""
    cells = _read(clue, 2, 1)
    width = clue["values"][0]
    if not 1 <= width < len(cells):
        raise ValueError(
            f"clue {clue['id']!r} (arrow) has bulb length {width} over "
            f"{len(cells)} cells: it needs a bulb and a shaft"
        )

    def post(m, x):
        bulb = sum(x[c] * 10 ** (width - 1 - i) for i, c in enumerate(cells[:width]))
        m.Add(sum(x[c] for c in cells[width:]) == bulb)

    return Poster(tuple(cells), post)


def killer_cage(clue):
    """The cage's digits all differ and sum to the clue's value."""
    cells = _read(clue, 2, 1)

    def post(m, x):
        m.AddAllDifferent([x[c] for c in cells])
        m.Add(sum(x[c] for c in cells) == clue["values"][0])

    return Poster(tuple(cells), post)


def little_killer(clue):
    """The diagonal's digits sum to the clue's value; repeats are allowed."""
    cells = _read(clue, 2, 1)

    def post(m, x):
        m.Add(sum(x[c] for c in cells) == clue["values"][0])

    return Poster(tuple(cells), post)


def skyscraper(clue):
    """The outside cell holds how many digits of the line show from the clue:
    a digit shows when it is taller than every digit before it."""
    cells = _read(clue, 2, 0)
    line = cells[1:]

    def post(m, x):
        shown = 1
        for i, cell in enumerate(line[1:], 1):
            taller = []
            for j, before in enumerate(line[:i]):
                above = m.NewBoolVar(f"{clue['id']}.{i}>{j}")
                m.Add(x[cell] > x[before]).OnlyEnforceIf(above)
                m.Add(x[cell] <= x[before]).OnlyEnforceIf(above.Not())
                taller.append(above)
            seen = m.NewBoolVar(f"{clue['id']}.seen{i}")
            m.AddBoolAnd(taller).OnlyEnforceIf(seen)
            m.AddBoolOr([above.Not() for above in taller]).OnlyEnforceIf(seen.Not())
            shown += seen
        m.Add(x[cells[0]] == shown)

    return Poster(tuple(cells), post)


def numbered_rooms(clue):
    """The outside cell holds the digit the line holds at the position its near
    cell's digit names: near cell 3 puts the outside digit third from the
    clue."""
    cells = _read(clue, 2, 0)
    outside, line = cells[0], cells[1:]

    def post(m, x):
        near = x[line[0]]
        m.Add(near <= len(line))
        for position, cell in enumerate(line, 1):
            names = m.NewBoolVar(f"{clue['id']}.names{position}")
            m.Add(near == position).OnlyEnforceIf(names)
            m.Add(near != position).OnlyEnforceIf(names.Not())
            m.Add(x[cell] == x[outside]).OnlyEnforceIf(names)

    return Poster(tuple(cells), post)


def anti_knight(clue):
    """The two cells, a chess knight's move apart, differ."""
    a, b = _read(clue, 2, 0, 2)

    def post(m, x):
        m.Add(x[a] != x[b])

    return Poster((a, b), post)


RULES = {
    "difference": difference,
    "ratio": ratio,
    "thermo": thermo,
    "slow_thermo": slow_thermo,
    "renban": renban,
    "whisper": whisper,
    "lockout": lockout,
    "arrow": arrow,
    "killer_cage": killer_cage,
    "little_killer": little_killer,
    "skyscraper": skyscraper,
    "numbered_rooms": numbered_rooms,
    "anti_knight": anti_knight,
}


def poster(clue):
    """The `Poster` for `clue`, from the rule function its `rule` names."""
    if clue["rule"] not in RULES:
        raise ValueError(
            f"clue {clue['id']!r} has rule {clue['rule']!r}, not one of {sorted(RULES)}"
        )
    return RULES[clue["rule"]](clue)
