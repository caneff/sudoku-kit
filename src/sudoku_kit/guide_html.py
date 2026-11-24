"""The solve guide as an HTML page: a guide file, which the `/solve-guide`
skill writes, drawn against its step record and the rules file (specs #106
and #127).

`deductions(rules, record)` groups the record's steps into deductions. A step
joins an earlier deduction naming the same set of constraints, adjacent or
not, unless a step between them changed a cell that deduction uses (a cell of
its named constraints or of its claims). A step whose claim is a chain or an
`either` is a deduction of its own. A deduction sits at its last step's
position. Grouping is computed from the record alone, so two runs over the
same record group its steps the same way.

`guide_page(rules, record, guide)` is the whole guide. The guide file, version
1, is described in `docs/guide-file.md`: an ordered list of entries, each a
key idea or a fill stretch over a run of steps, together covering every step
of the record exactly once, in order. `guide_file.check` refuses one that does
not, or that is malformed, naming the problem. The page opens
with the title, the original image once when given, the rules file's
`rules_text` and the plain grid of the starting position.

The library numbers key ideas 1..N in file order and shows the break-in label
on the flagged one; every other word is the skill's. A key idea is one card,
never split across a printed page: its grid about 16rem wide on top, then its
number badge, heading and paragraphs, so about 1 to 2 print per A4 page. The
grids follow SudokuPad's look: light cell lines, dark region lines, a heavy
border, blue pencil marks and placed digits, black givens, each digit's pencil
mark in its own fixed spot in the cell. Its grid draws
its starting candidates (those before its first step, less what the run's
steps it does not explain remove) only in the cells its explained steps use
or change, with the digits they remove drawn grey under a red slash; every
other cell shows its
placed digit or stays blank. Cells of the constraints its steps name are
tinted `used` and the cells they change `changed` (yellow). A chain claim is
drawn as
arrows along the chain, and an `either` claim circles each pattern's cells.

A fill stretch is the skill's one sentence on a light panel over a list,
collapsed behind a "Show all N steps" button, written here (#151). N counts
the steps, and one line covers several: the list's steps proved by the same
set of constraints share a line where that set first appears, saying what
goes and from what ("r1c12 lose 4; r1c3 is 3, from row 1."), and neighbouring
lines of single houses that each remove the digit of one solved cell in all
those houses become one line naming that cell first ("The 4 in r2c2: r2c134,
r134c2 and r1c1 lose 4."). Constraints are in words (`constraint_words`), a region as a
box, never a clue id. In print the collapsed lists are hidden: they do nothing
on paper. A stuck record ends the guide with the grid and candidates at the
stuck point.

A key idea may carry a `supposition` (spec #127): "suppose this cell were X".
It draws as a second grid beside the idea's own (`render_supposition`) with no
pencil marks: the givens, the assumed digit and the forced digits each in
their own colour, the forced ones numbered in order, and the clash cells
circled. `guide_file` checks its shape;
the page refuses one whose assumed digit the idea's explained steps do not
eliminate, or that draws a digit which is not among the idea's starting
candidates in its cell.

A key idea may carry `early_removals` (#147): digits its words rule out
before the record does. The page refuses one that is not a candidate after
the idea's steps and the early removals before it, or that is the cell's
solution digit (`_known_solution`), naming the key idea, cell and digit. The
idea's grid strikes them and marks their cells; every later grid starts
without them. A label mark keeps clear of its cell's pencil marks
(`_label_spot`).

`render(rules)` is the plain grid, givens and clues only; `plain_page` puts it
beside the original image for the import comparison.
"""

import html
import itertools

from sudoku_kit import guide_file, rules_file, step_search
from sudoku_kit.guide_file import join_words, plural

CELL = 48
LABEL_CHAR = 7.2  # a label letter's width at 12px bold, about 0.6em
LINE_COLOURS = {
    "thermo": "#999",
    "slow_thermo": "#999",
    "renban": "#a6c",
    "whisper": "#4a4",
    "lockout": "#e83",
    "arrow": "#555",
}
STYLE = """
:root { --ink: #1e2430; --muted: #6a7280; --line: #b9bfc8; --box: #000;
  --blue: #1d6ae5; --red: #d0342c; --changed: #fff1a8; --used: #eef3fb;
  --card: #f7f8fa; }
html { -webkit-print-color-adjust: exact; print-color-adjust: exact; }
body { font-family: "Segoe UI", "Ubuntu Sans", Ubuntu, system-ui, Roboto, Arial, sans-serif;
  color: var(--ink); font-size: 10pt; line-height: 1.5; max-width: 52rem;
  margin: 2rem auto; padding: 0 1.5rem; }
header.intro { display: flex; gap: 1.75rem; align-items: flex-start;
  background: var(--card); border-radius: 12px; padding: 1.25rem 1.4rem;
  margin-bottom: 1.1rem; }
header.intro .introtext { flex: 1; }
.overline { font-size: 8pt; font-weight: 600; letter-spacing: 0.08em;
  text-transform: uppercase; color: var(--blue); }
h1 { font-size: 22pt; font-weight: 700; margin: 0.1rem 0 0.7rem; line-height: 1.15;
  letter-spacing: -0.01em; }
.rules { white-space: pre-line; color: #3a4250; margin: 0; }
header.intro svg.grid { width: 14rem; flex: none; }
svg.grid { width: 24rem; height: auto; display: block; }
section.key { margin: 0.8rem 0; padding: 1.1rem 1.2rem; background: #fff;
  border: 1px solid #e3e6eb; border-radius: 12px;
  box-shadow: 0 1px 2px rgba(20,30,50,0.06), 0 2px 8px rgba(20,30,50,0.05);
  break-inside: avoid; }
.grids { display: flex; gap: 1.25rem; margin-bottom: 0.8rem; }
figure { margin: 0; }
figcaption { font-size: 8pt; font-weight: 600; color: var(--muted);
  text-align: center; margin-top: 0.35rem; }
section.key svg.grid { width: 16rem; }
.eyebrow { display: flex; align-items: center; gap: 0.5rem; margin-bottom: 0.3rem; }
.num { display: inline-flex; min-width: 1.45rem; height: 1.45rem; border-radius: 7px;
  background: var(--blue); color: #fff; align-items: center; justify-content: center;
  font-size: 9.5pt; font-weight: 700; }
.kicker { font-size: 8pt; font-weight: 600; letter-spacing: 0.06em;
  text-transform: uppercase; color: var(--muted); }
.breakin { font-size: 7.5pt; font-weight: 700; letter-spacing: 0.06em;
  text-transform: uppercase; color: #fff; background: var(--red);
  border-radius: 999px; padding: 0.1rem 0.55rem; }
section.key h2 { font-size: 13pt; font-weight: 700; margin: 0 0 0.35rem;
  line-height: 1.3; }
section.key p { margin: 0.4rem 0; }
div.fill { break-inside: avoid; margin: 0.8rem 0; padding: 0.7rem 1.2rem;
  background: var(--card); border-radius: 10px; }
p.fill { break-after: avoid; margin: 0; color: #3a4250; }
details { margin-top: 0.35rem; }
summary { display: inline-block; font-size: 8pt; font-weight: 600; color: var(--blue);
  cursor: pointer; list-style: none; border: 1px solid #c9d8f5; border-radius: 999px;
  padding: 0.05rem 0.6rem; background: #fff; }
summary::-webkit-details-marker { display: none; }
summary::before { content: "▸ "; }
details[open] summary::before { content: "▾ "; }
details ul { font-size: 9pt; color: #3a4250; padding-left: 1.1rem; margin: 0.4rem 0; }
img.original { max-width: 24rem; }
.sidebyside { display: flex; gap: 2rem; align-items: flex-start; }
.cell { fill: #fff; stroke: var(--line); stroke-width: 1; }
.cell.used { fill: var(--used); }
.cell.changed { fill: var(--changed); }
.cell.highlight { fill: #dff3df; }
.edge { stroke: var(--box); stroke-width: 2.6; }
.border { fill: none; stroke: var(--box); stroke-width: 4; }
.dot { stroke: #000; }
text { font-family: "Segoe UI", "Ubuntu Sans", Ubuntu, Roboto, Arial, sans-serif; }
.label { font-size: 12px; font-weight: bold; fill: var(--red); }
.given { font-size: 30px; fill: #000; }
.solved { font-size: 30px; fill: var(--blue); }
.cand { font-size: 12.5px; fill: var(--blue); }
.cand.struck { fill: #a9b0bb; }
.slash { stroke: var(--red); stroke-width: 1.4; stroke-linecap: round; }
.solved.assumed { fill: var(--red); font-weight: 700; }
.solved.forced { fill: var(--blue); font-weight: 600; }
.order { paint-order: stroke; stroke: #fff; stroke-width: 2.5px; stroke-linejoin: round; font-size: 10.5px; font-weight: 700; fill: var(--red); }
.arrow, .circle { stroke: var(--red); fill: none; stroke-width: 2.4; }
@page { size: A4; margin: 15mm; }
@media print {
  body { max-width: none; margin: 0; padding: 0; }
  section.key { margin: 0.5rem 0; padding: 0.8rem 0.85rem; }
  div.fill { margin: 0.5rem 0; }
  .grids { margin-bottom: 0.5rem; }
  details { display: none; }
}
"""


def deductions(rules, record):
    """The record's deductions in guide order, each `{"named", "steps",
    "claims"}`: `steps` its step numbers from 1, `claims` theirs in order."""
    registry = rules_file.registry(rules)
    groups, open_groups = [], {}
    for number, step in enumerate(record["steps"], 1):
        claim = step["claim"]
        key = frozenset(step["named"]) if "cell" in claim else None
        group = open_groups.get(key)
        if group is None:
            group = {"named": step["named"], "steps": [], "claims": [], "cells": set()}
            groups.append(group)
            if key is not None:
                open_groups[key] = group
        group["steps"].append(number)
        group["claims"].append(claim)
        changed, _ = _claim_marks(claim)
        group["cells"] |= changed
        for name in step["named"]:
            group["cells"].update(registry[name].cells)
        if "cell" in claim:
            open_groups = {
                k: g
                for k, g in open_groups.items()
                if g is group or tuple(claim["cell"]) not in g["cells"]
            }
    return sorted(
        ({k: g[k] for k in ("named", "steps", "claims")} for g in groups),
        key=lambda g: g["steps"][-1],
    )


def states(rules, record):
    """The candidates before each step, by step number from 1, and after the
    last step under the number past it."""
    state = step_search.State(rules)
    before = {}
    for i, step in enumerate(record["steps"], 1):
        before[i] = dict(state.candidates)
        state.apply(step_search.claim_from_json(step["claim"]))
    before[len(record["steps"]) + 1] = dict(state.candidates)
    return before


class Grid:
    """The geometry of one board's drawing: every cell, outside ones too."""

    def __init__(self, rules):
        self.rules = rules
        self.n = rules["size"]
        every = rules_file.cells(rules)
        self.top = min(r for r, _ in every)
        self.left = min(c for _, c in every)
        self.rows = max(r for r, _ in every) - self.top + 1
        self.columns = max(c for _, c in every) - self.left + 1
        self.givens = {tuple(g["cell"]): g["digit"] for g in rules["givens"]}
        self.region = {
            tuple(cell): k
            for k, region in enumerate(rules["regions"])
            for cell in region
        }

    def x(self, column):
        return (column - self.left) * CELL

    def y(self, row):
        return (row - self.top) * CELL

    def centre(self, cell):
        return self.x(cell[1]) + CELL / 2, self.y(cell[0]) + CELL / 2


def _cell_class(cell, used, changed, lit=()):
    classes = ["cell"]
    if cell in used:
        classes.append("used")
    if cell in changed:
        classes.append("changed")
    if cell in lit:
        classes.append("highlight")
    return " ".join(classes)


def _text(x, y, cls, text, width=None, **data):
    """A centred text; `width` squeezes it to exactly that many units."""
    attrs = "".join(f' data-{k}="{html.escape(str(v))}"' for k, v in data.items())
    if width is not None:
        attrs = f' textLength="{width:.1f}" lengthAdjust="spacingAndGlyphs"' + attrs
    return (
        f'<text class="{cls}" x="{x:.1f}" y="{y:.1f}" text-anchor="middle"'
        f"{attrs}>{html.escape(str(text))}</text>"
    )


def _clue(grid, clue):
    """The SVG for one clue's mark."""
    cells = [tuple(c) for c in clue["cells"]]
    rule, values = clue["rule"], clue["values"]
    points = " ".join(f"{x:.1f},{y:.1f}" for x, y in map(grid.centre, cells))
    if rule in ("difference", "ratio"):
        (ax, ay), (bx, by) = grid.centre(cells[0]), grid.centre(cells[1])
        white = rule == "difference"
        fill = "#fff" if white else "#000"
        shown_value = values[0] not in (1, 2)
        mark = (
            f'<circle class="dot" cx="{(ax + bx) / 2:.1f}" cy="{(ay + by) / 2:.1f}" '
            f'r="7.5" fill="{fill}" stroke="#111" stroke-width="1.6" '
            f'data-clue="{html.escape(clue["id"])}"/>'
        )
        if shown_value:
            mark += _text((ax + bx) / 2, (ay + by) / 2 + 4, "dotvalue", values[0])
        return mark
    if rule in LINE_COLOURS:
        bulb = ""
        if rule in ("thermo", "slow_thermo", "arrow"):
            bx, by = grid.centre(cells[0])
            bulb = (
                f'<circle class="bulb" cx="{bx:.1f}" cy="{by:.1f}" r="14" '
                f'fill="none" stroke="{LINE_COLOURS[rule]}" stroke-width="3"/>'
            )
        return (
            f'<polyline class="line {rule}" points="{points}" fill="none" '
            f'stroke="{LINE_COLOURS[rule]}" stroke-width="6" opacity="0.6"/>{bulb}'
        )
    if rule in ("killer_cage", "little_killer"):
        out = [
            f'<rect class="cage" x="{grid.x(cell[1]) + 4}" y="{grid.y(cell[0]) + 4}" '
            f'width="{CELL - 8}" height="{CELL - 8}" fill="none" stroke="#555" '
            'stroke-dasharray="3 2"/>'
            for cell in cells
        ]
        x, y = grid.centre(cells[0])
        out.append(_text(x - 12, y - 10, "cagesum", values[0]))
        return "".join(out)
    if rule in ("skyscraper", "numbered_rooms"):
        # The clue's digit is the solver's to find: its outside cell is drawn
        # empty, like any cell, and fills only through the candidates.
        return ""
    return f'<polyline class="line" points="{points}" fill="none" stroke="#888"/>'


def _label_spot(grid, cell, text, drawn):
    """(x, baseline y, width or None) of a label in `cell` that keeps clear of
    `drawn`, the digits whose pencil marks the cell draws. With none, the label
    sits along the cell's foot. Otherwise it takes the widest run of empty
    pencil-mark spots in one row of them, the lowest such row on a tie,
    squeezed to fit; with no spot empty it sits just under the cell, or just
    over it on the grid's last row."""
    x, y = grid.centre(cell)
    if not drawn:
        return x, y + CELL / 2 - 4, None
    natural = LABEL_CHAR * len(text)
    runs = []  # (length, band, first column) of each run of empty spots
    for band in range(_bands(grid)):
        empty = [col for col in range(3) if band * 3 + col + 1 not in drawn]
        for _, run in itertools.groupby(enumerate(empty), lambda p: p[1] - p[0]):
            columns = [col for _, col in run]
            runs.append((len(columns), band, columns[0]))
    if not runs:
        last_row = cell[0] == grid.top + grid.rows - 1
        top = grid.y(cell[0])
        return x, (top - 3 if last_row else top + CELL + 11), natural
    length, band, start = max(runs)
    slot = (CELL - 10) / 3
    left = grid.x(cell[1]) + 5 + slot * start
    _, baseline = _spot(grid, cell, band * 3 + 1)
    return left + slot * length / 2, baseline, min(natural, slot * length - 2)


def _annotation(grid, note, prefix, drawn=frozenset()):
    kind = note["type"]
    if kind == "arrow":
        (ax, ay), (bx, by) = grid.centre(note["from"]), grid.centre(note["to"])
        return (
            f'<line class="arrow" x1="{ax:.1f}" y1="{ay:.1f}" x2="{bx:.1f}" '
            f'y2="{by:.1f}" marker-end="url(#{prefix}-head)" '
            f'data-from="{rules_file.cell_name(note["from"])}" '
            f'data-to="{rules_file.cell_name(note["to"])}"/>'
        )
    if kind == "circle":
        x, y = grid.centre(note["cell"])
        return (
            f'<circle class="circle" cx="{x:.1f}" cy="{y:.1f}" r="{CELL / 2 - 9.5}" '
            f'data-cell="{rules_file.cell_name(note["cell"])}"/>'
        )
    if kind == "label":
        x, y, width = _label_spot(grid, note["cell"], note["text"], drawn)
        return _text(
            x, y, "label", note["text"], width, cell=rules_file.cell_name(note["cell"])
        )
    return ""  # a highlight is drawn as its cell's fill


def _claim_marks(claim):
    """(changed cells, marks: arrows along a chain, circles round an `either`)
    the claim gives."""
    if "cell" in claim:
        return {tuple(claim["cell"])}, []
    if "chain" in claim:
        cells = [tuple(c) for c in claim["chain"]]
        arrows = [
            {"type": "arrow", "from": a, "to": b} for a, b in itertools.pairwise(cells)
        ]
        return set(cells), arrows
    cells = {tuple(c) for pattern in claim["either"] for c, _ in pattern}
    return cells, [{"type": "circle", "cell": c} for c in sorted(cells)]


def _frame(grid, prefix, data="", used=(), changed=(), lit=()):
    """The opening of a grid's SVG: its cells, house edges and clues."""
    out = [
        f'<svg class="grid" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {grid.columns * CELL} {grid.rows * CELL}"{data}>',
        f'<defs><marker id="{prefix}-head" markerWidth="8" markerHeight="8" refX="6" '
        'refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#c22"/></marker></defs>',
    ]
    out.extend(
        f'<rect class="{_cell_class(cell, used, changed, lit)}" '
        f'x="{grid.x(cell[1])}" y="{grid.y(cell[0])}" width="{CELL}" '
        f'height="{CELL}" data-cell="{rules_file.cell_name(cell)}"/>'
        for cell in rules_file.cells(grid.rules)
    )
    out.extend(_house_edges(grid))
    out.append(
        f'<rect class="border" x="0" y="0" width="{grid.columns * CELL}" '
        f'height="{grid.rows * CELL}"/>'
    )
    out.extend(_clue(grid, clue) for clue in grid.rules["clues"])
    return out


def render(rules, candidates=None, idea=None, prefix="g"):
    """One grid as an SVG string. `candidates` ({cell: digits}) draws each
    cell's digits; without it only givens show. `idea`, a key idea (its `key`
    number, the `named` constraints and `claims` of its steps, `removed`,
    {cell: digits}, the cells of its `early` removals, and its guide file
    `marks`), marks its cells, draws candidates only in them and strikes out
    what it removes."""
    grid = Grid(rules)
    removed, marked, notes = {}, None, []
    if idea is None:
        out = _frame(grid, prefix)
    else:
        registry = rules_file.registry(rules)
        used, changed = set(), set()
        for name in idea["named"]:
            used.update(registry[name].cells)
        for claim in idea["claims"]:
            cells, marks = _claim_marks(claim)
            changed |= cells
            notes += marks
        changed |= set(idea["early"])
        notes += idea["marks"]
        lit = {m["cell"] for m in notes if m["type"] == "highlight"}
        out = _frame(grid, prefix, f' data-key="{idea["key"]}"', used, changed, lit)
        removed, marked = idea["removed"], used | changed
    drawn = {}
    for cell in rules_file.cells(rules):
        gone = removed.get(cell, set())
        drawn[cell] = _drawn(grid, cell, candidates, gone, marked)
        out.extend(_digits(grid, cell, candidates, gone, marked=marked))
    out.extend(
        _annotation(grid, note, prefix, drawn.get(note.get("cell"), set()))
        for note in notes
    )
    out.append("</svg>")
    return "".join(out)


def render_supposition(rules, suppose, key, prefix):
    """Key idea `key`'s supposition as its own grid, `suppose` being
    `assume`: (cell, digit), `forces`: [(cell, digit)] and `breaks`: [cell].
    It draws no pencil marks: only the givens, the assumed digit and the
    forced digits, each in its own colour and the forced ones numbered in
    order, with the cells it names tinted and the clash circled."""
    grid = Grid(rules)
    marked = {
        suppose["assume"][0],
        *(c for c, _ in suppose["forces"]),
        *suppose["breaks"],
    }
    cell, digit = suppose["assume"]
    placed = {cell: (digit, "assumed", {})}
    placed |= {
        cell: (digit, "forced", {"order": order})
        for order, (cell, digit) in enumerate(suppose["forces"], 1)
    }
    out = _frame(grid, prefix, f' data-supposition="{key}"', changed=marked)
    for cell in rules_file.cells(rules):
        if cell in grid.givens:
            out.extend(_digits(grid, cell, None))
        elif cell in placed:
            digit, role, extra = placed[cell]
            x, y = grid.centre(cell)
            name = rules_file.cell_name(cell)
            out.append(
                _text(
                    x, y + 10, f"solved {role}", digit, cell=name, digit=digit, **extra
                )
            )
    out.extend(_suppose_marks(grid, suppose))
    out.append("</svg>")
    return "".join(out)


def _suppose_marks(grid, suppose):
    """The order numbers of the forced digits and a circle round each clash."""
    out = []
    for order, (cell, _) in enumerate(suppose["forces"], 1):
        x, y = grid.centre(cell)
        out.append(
            _text(
                x + 18.5,
                y - 5,
                "order",
                order,
                cell=rules_file.cell_name(cell),
            )
        )
    out.extend(
        _annotation(grid, {"type": "circle", "cell": cell}, "s")
        for cell in suppose["breaks"]
    )
    return out


def _house_edges(grid):
    """Thick lines on the board's outline, round its holes and between regions."""
    n, edges = grid.n, []
    holes = rules_file.holes(grid.rules)
    on = lambda r, c: 0 <= r < n and 0 <= c < n and (r, c) not in holes
    for r in range(n):
        for c in range(n):
            if not on(r, c):
                continue
            region = grid.region.get((r, c))
            if not on(r, c + 1) or grid.region.get((r, c + 1)) != region:
                edges.append((c + 1, r, c + 1, r + 1))
            if not on(r + 1, c) or grid.region.get((r + 1, c)) != region:
                edges.append((c, r + 1, c + 1, r + 1))
            if not on(r, c - 1):
                edges.append((c, r, c, r + 1))
            if not on(r - 1, c):
                edges.append((c, r, c + 1, r))
    return [
        f'<line class="edge" x1="{grid.x(a)}" y1="{grid.y(b)}" x2="{grid.x(c)}" '
        f'y2="{grid.y(d)}" stroke-linecap="square"/>'
        for a, b, c, d in edges
    ]


def _bands(grid):
    """How many rows of pencil-mark spots a cell has, three spots to a row."""
    return -(-grid.n // 3)


def _spot(grid, cell, d):
    """(x, baseline y) of digit `d`'s pencil mark, the same in every cell."""
    dx = grid.x(cell[1]) + 5 + (CELL - 10) * ((d - 1) % 3 + 0.5) / 3
    dy = grid.y(cell[0]) + 3 + (CELL - 6) * ((d - 1) // 3 + 0.5) / _bands(grid) + 4.5
    return dx, dy


def _drawn(grid, cell, candidates, removed, marked):
    """The digits whose pencil marks `cell` draws: none for a given, a placed
    digit, a cell outside `marked` or one still holding every digit."""
    if candidates is None or cell in grid.givens or len(candidates[cell]) == 1:
        return set()
    if marked is not None and cell not in marked:
        return set()
    drawn = candidates[cell] | removed
    return set() if len(drawn) == grid.n and not removed else drawn


def _digits(grid, cell, candidates, removed=frozenset(), marked=None):
    """A cell's given, placed digit or candidates; with `marked`, a cell
    outside it shows only its placed digit. Each digit's pencil mark has its
    own fixed spot in the cell, three to a row; a struck one gets a slash."""
    x, y = grid.centre(cell)
    given = grid.givens.get(cell)
    if given is not None:
        return [_text(x, y + 10, "given", given)]
    if candidates is None:
        return []
    held = candidates[cell]
    if len(held) == 1:
        return [_text(x, y + 10, "solved", next(iter(held)))]
    out = []
    for d in sorted(_drawn(grid, cell, candidates, removed, marked)):
        dx, dy = _spot(grid, cell, d)
        cls = "cand struck" if d in removed else "cand"
        out.append(_text(dx, dy, cls, d, cell=rules_file.cell_name(cell), digit=d))
        if d in removed:
            out.append(
                f'<line class="slash" x1="{dx - 5:.1f}" y1="{dy + 1.5:.1f}" '
                f'x2="{dx + 5:.1f}" y2="{dy - 10.5:.1f}"/>'
            )
    return out


def describe_claim(claim):
    if "cell" in claim:
        cell = rules_file.cell_name(claim["cell"])
        digits = claim["digits"]
        return (
            f"{cell} = {digits[0]}"
            if len(digits) == 1
            else (f"{cell} keeps {' '.join(map(str, digits))}")
        )
    if "chain" in claim:
        return "chain " + " < ".join(rules_file.cell_name(c) for c in claim["chain"])
    return "at least one of several patterns holds"


def _cell_words(cells):
    """Cells as a list of blocks in words: r2c134, r134c2 and r1c1."""
    return join_words(rules_file.cell_list(cells).split(", "))


def _digit_words(digits):
    return join_words([str(d) for d in sorted(digits)])


def _changes(record, before, numbers):
    """{cell: (digits removed, digits left)} over the cell claims of steps
    `numbers`, in order of each cell's first claim."""
    out = {}
    for i in numbers:
        claim = record["steps"][i - 1]["claim"]
        if "cell" not in claim:
            continue
        cell = tuple(claim["cell"])
        gone, _ = out.get(cell, (frozenset(), None))
        out[cell] = (
            gone | (before[i][cell] - before[i + 1][cell]),
            before[i + 1][cell],
        )
    return out


def _change_words(changes, record, numbers):
    """What `changes` does in words, joined by `;`: cells losing the same
    digits share one phrase (r1c12 lose 4), a placed cell reads as its digit
    (r1c3 is 3), and one that loses nothing by what it keeps. A claim on no
    cell reads as `describe_claim` gives it."""
    phrases = {}
    for cell, (gone, left) in changes.items():
        if len(left) == 1:
            key = ("is", next(iter(left)))
        elif gone:
            key = ("loses", gone)
        else:
            key = ("keeps", left)
        phrases.setdefault(key, []).append(cell)
    out = []
    for (verb, digits), cells in phrases.items():
        one = len(cells) == 1
        if verb == "is":
            out.append(f"{_cell_words(cells)} {'is' if one else 'are'} {digits}")
        elif verb == "loses":
            words = _digit_words(digits)
            out.append(f"{_cell_words(cells)} {'loses' if one else 'lose'} {words}")
        else:
            out.append(
                f"{_cell_words(cells)} {'keeps' if one else 'keep'} "
                + " ".join(map(str, sorted(digits)))
            )
    for i in numbers:
        claim = record["steps"][i - 1]["claim"]
        if "cell" not in claim:
            out.append(describe_claim(claim))
    return "; ".join(out)


def describe_steps(record, before, numbers):
    """What steps `numbers` of `record` do, in words: the digits each cell
    loses, or the digit it is, cells with the same change in one phrase.
    `before` is `states(rules, record)`."""
    return _change_words(_changes(record, before, numbers), record, numbers)


CLUE_WORDS = {
    "difference": lambda v: "white dot" if v == 1 else f"white dot {v}",
    "ratio": lambda v: "black dot" if v == 2 else f"black dot {v}",
    "thermo": lambda v: "thermometer",
    "slow_thermo": lambda v: "slow thermometer",
    "renban": lambda v: "renban line",
    "whisper": lambda v: "whisper line",
    "lockout": lambda v: "lockout line",
    "arrow": lambda v: "arrow",
    "killer_cage": lambda v: f"killer cage {v}",
    "little_killer": lambda v: f"little killer {v}",
    "skyscraper": lambda v: "skyscraper",
    "numbered_rooms": lambda v: "numbered room",
    "anti_knight": lambda v: "knight's move",
    "tessellation": lambda v: "tessellation edge",
    "consecutive_set": lambda v: "consecutive set",
}
OUTSIDE_RULES = ("skyscraper", "numbered_rooms")


def _corner_partner(rules, clue):
    """The clue that crosses `clue` at one corner, a dot of the same kind and
    value on the other diagonal of the same 2x2 block, or None."""
    if clue["rule"] not in ("difference", "ratio") or len(clue["cells"]) != 2:
        return None
    (r1, c1), (r2, c2) = clue["cells"]
    if abs(r1 - r2) != 1 or abs(c1 - c2) != 1:
        return None
    other = {(r1, c2), (r2, c1)}
    return next(
        (
            c
            for c in rules["clues"]
            if c["rule"] == clue["rule"]
            and c["values"] == clue["values"]
            and {tuple(x) for x in c["cells"]} == other
        ),
        None,
    )


def constraint_words(rules, name):
    """A named constraint as a solver reads it: a row or column by its name, a
    region as a box, a clue by its kind and its cells (first to last, or the
    outside cell of a clue read from outside), never by its id. Two diagonal
    dots that cross at one corner are one dot at their 2x2 block, as the
    picture draws them."""
    if name in rules_file.house_names(rules):
        return name.replace("region", "box")
    clue = next(c for c in rules["clues"] if c["id"] == name)
    value = clue["values"][0] if clue["values"] else None
    kind = CLUE_WORDS[clue["rule"]](value)
    partner = _corner_partner(rules, clue)
    if partner is not None:
        return f"{kind} at {rules_file.cell_list(clue['cells'] + partner['cells'])}"
    cells = [rules_file.cell_name(c) for c in clue["cells"]]
    if clue["rule"] in OUTSIDE_RULES or len(cells) == 1:
        where = cells[0]
    else:
        where = f"{cells[0]}-{cells[-1]}"
    return f"{kind} {where}"


def named_words(rules, named):
    """A step's named constraints in words, each once, joined."""
    return join_words(list(dict.fromkeys(constraint_words(rules, n) for n in named)))


def _removes_one(record, before, i):
    """The one digit step `i` removes from its cell, or None."""
    claim = record["steps"][i - 1]["claim"]
    if "cell" not in claim:
        return None
    cell = tuple(claim["cell"])
    gone = before[i][cell] - before[i + 1][cell]
    return next(iter(gone)) if len(gone) == 1 else None


def _sources(houses, record, before, i):
    """(digit, cells): the one digit step `i` removes and the solved cells
    holding it in the one house the step names, other than its own cell; or
    (None, empty) when the step removes more or names more than one house."""
    step = record["steps"][i - 1]
    digit = _removes_one(record, before, i)
    house = houses.get(step["named"][0]) if len(set(step["named"])) == 1 else None
    if digit is None or house is None:
        return None, set()
    cell = tuple(step["claim"]["cell"])
    return digit, {c for c in house if c != cell and before[i][c] == {digit}}


def _runs(rules, record, before, numbers):
    """Steps `numbers` as runs for one line each (Chris on #151). Cell claims
    proved by the same set of constraints share a run, wherever they fall in
    the list, placed where the set first appears; a claim on no cell is a run
    of its own. Then neighbouring runs of single houses that each remove only
    the digit of one solved cell in all of them join (a given clearing its
    row, column and box). Each run is `{"steps", "named", "sources",
    "digit"}`: `named` the one set of constraints, or None once the run spans
    houses; `sources` the solved cells holding `digit` in every house of the
    run, empty when there is none."""
    houses = rules_file.house_names(rules)
    runs, by_named = [], {}
    for i in numbers:
        step = record["steps"][i - 1]
        named = frozenset(step["named"])
        digit, sources = _sources(houses, record, before, i)
        run = by_named.get(named) if "cell" in step["claim"] else None
        if run is None:
            run = {"steps": [], "named": named, "sources": sources, "digit": digit}
            runs.append(run)
            if "cell" in step["claim"]:
                by_named[named] = run
        elif run["digit"] == digit:
            run["sources"] = run["sources"] & sources
        else:
            run["sources"] = set()
        run["steps"].append(i)
    joined = []
    for run in runs:
        last = joined[-1] if joined else None
        shared = (
            last["sources"] & run["sources"]
            if last is not None and last["digit"] == run["digit"]
            else set()
        )
        if shared:
            last["steps"] += run["steps"]
            last["named"] = None
            last["sources"] = shared
        else:
            joined.append(dict(run))
    return joined


def _run_line(rules, record, before, run):
    """One run's line: a constraint's run says what goes and from what; a
    solved cell clearing its houses names the cell and its digit first."""
    steps = run["steps"]
    if run["named"] is not None:
        named = record["steps"][steps[0] - 1]["named"]
        what = describe_steps(record, before, steps)
        return f"{what}, from {named_words(rules, named)}."
    source = min(run["sources"])
    digit = run["digit"]
    by_house = {}
    for i in steps:
        step = record["steps"][i - 1]
        by_house.setdefault(step["named"][0], []).append(step["claim"]["cell"])
    blocks = [
        b
        for cells in by_house.values()
        for b in rules_file.cell_list(cells).split(", ")
    ]
    changes = _changes(record, before, steps)
    placed = [
        f"{rules_file.cell_name(c)} is {next(iter(left))}"
        for c, (_, left) in changes.items()
        if len(left) == 1
    ]
    then = f", so {join_words(placed)}" if placed else ""
    return (
        f"The {digit} in {rules_file.cell_name(source)}: "
        f"{join_words(blocks)} lose {digit}{then}."
    )


def _step_items(rules, record, before, numbers):
    """A collapsed list's items: one line per run of `numbers` (`_runs`)."""
    return "".join(
        f'<li class="step" data-steps="{" ".join(map(str, run["steps"]))}">'
        f"{html.escape(_run_line(rules, record, before, run))}</li>"
        for run in _runs(rules, record, before, numbers)
    )


def _fill(rules, entry, record, before):
    """One stretch of fill: the skill's sentence, then its steps' lines."""
    numbers = range(entry["first"], entry["last"] + 1)
    return (
        f'<div class="fill" data-steps="{entry["first"]}-{entry["last"]}">'
        f'<p class="fill">{html.escape(entry["sentence"])}</p><details><summary>'
        f"Show all {plural(len(numbers), 'step')}</summary>"
        f"<ul>{_step_items(rules, record, before, numbers)}</ul></details></div>"
    )


def _eliminations(record, before, numbers):
    """{cell: digits} the steps `numbers` remove. `State.apply` narrows only a
    cell claim's own cell, and a chain or `either` removes no candidate."""
    out = {}
    for i in numbers:
        claim = record["steps"][i - 1]["claim"]
        if "cell" in claim:
            cell = tuple(claim["cell"])
            out[cell] = out.get(cell, set()) | (before[i][cell] - before[i + 1][cell])
    return out


def _check_supposed_digits(sup, removed, start, *, entry_number):
    """Refuse a supposition whose assumed digit the explained steps do not
    eliminate, or that draws a digit not among the idea's starting
    candidates in its cell."""
    cell, digit = sup["assume"]
    if digit not in removed.get(cell, set()):
        raise ValueError(
            f"entry {entry_number}'s supposition assumes {rules_file.cell_name(cell)} "
            f"= {digit}, which none of the steps the idea explains eliminate"
        )
    for cell, digit in [sup["assume"], *sup["forces"]]:
        if digit not in start[cell]:
            raise ValueError(
                f"entry {entry_number}'s supposition draws "
                f"{rules_file.cell_name(cell)} = {digit}, which is not a candidate "
                "there at the idea's start"
            )


def _less(candidates, gone):
    return {cell: digits - gone.get(cell, set()) for cell, digits in candidates.items()}


def _known_solution(rules, final):
    """{cell: digit} of the solution as far as it is known: the rules file's
    stored solution, else each cell `final`, the record's last candidates,
    has solved."""
    known = {cell: next(iter(ds)) for cell, ds in final.items() if len(ds) == 1}
    stored = rules.get("solution")
    if stored is not None:
        known |= {
            (r, c): d
            for r, row in enumerate(stored)
            for c, d in enumerate(row)
            if d is not None
        }
        known |= {
            tuple(o["cell"]): o["digit"] for o in rules.get("solution_outside") or []
        }
    return known


def _check_early_removals(entry, after, solution, *, key, entry_number):
    """{cell: digits} entry's early removals take out, refused naming the key
    idea, cell and digit when one is not a candidate in `after` (the
    candidates after the idea's steps), with the earlier ones applied, or is
    the cell's solution digit."""
    out = {}
    for cell, digit in entry.get("early_removals", []):
        name = rules_file.cell_name(cell)
        where = (
            f"key idea {key} (entry {entry_number}) removes {digit} from {name} early"
        )
        if digit not in after[cell] - out.get(cell, set()):
            raise ValueError(
                f"{where}, but {digit} is not a candidate there after the idea's "
                "steps and the early removals before it"
            )
        if cell not in solution:
            raise ValueError(
                f"{where}, but the solution digit there is not known: the rules "
                "file stores no solution and the step record does not solve it"
            )
        if solution[cell] == digit:
            raise ValueError(f"{where}, but {digit} is the solution digit there")
        out.setdefault(cell, set()).add(digit)
    return out


def _key_section(rules, entry, record, before, early, solution, *, key, entry_number):
    """Key idea `key`, the guide file's entry `entry_number`, as one card: its
    grid (and its supposition's), then its number badge, the break-in label
    when flagged, its heading and its paragraphs, with {cell: digits} of the
    early removals it adds. Its starting candidates are those before its first
    step less what the run's unexplained steps and `early`, the earlier ideas'
    early removals, remove."""
    first, last = entry["first"], entry["last"]
    numbers = range(first, last + 1)
    states = before
    before = {i: _less(before[i], early) for i in range(first, last + 2)}
    explained = entry.get("explains") or list(numbers)
    also = [i for i in numbers if i not in explained]
    steps = [record["steps"][i - 1] for i in explained]
    unexplained = _eliminations(record, before, also)
    start = {
        cell: digits - unexplained.get(cell, set())
        for cell, digits in before[first].items()
    }
    removed = _eliminations(record, before, explained)
    added = _check_early_removals(
        entry, before[last + 1], solution, key=key, entry_number=entry_number
    )
    idea = {
        "key": key,
        "named": list(dict.fromkeys(n for step in steps for n in step["named"])),
        "claims": [step["claim"] for step in steps],
        "removed": {
            cell: removed.get(cell, set()) | added.get(cell, set())
            for cell in removed.keys() | added.keys()
        },
        "early": added,
        "marks": entry.get("marks", []),
    }
    parts = [
        f'<section class="key" data-key="{key}" '
        f'data-steps="{" ".join(map(str, numbers))}">',
        '<div class="grids"><figure>',
        render(rules, start, idea, prefix=f"k{key}"),
    ]
    if "supposition" in entry:
        sup = entry["supposition"]
        _check_supposed_digits(sup, removed, start, entry_number=entry_number)
        cell, digit = sup["assume"]
        parts.append("<figcaption>The candidates</figcaption></figure><figure>")
        parts.append(render_supposition(rules, sup, key, prefix=f"s{key}"))
        parts.append(
            f"<figcaption>Suppose {rules_file.cell_name(cell)} were {digit}"
            "</figcaption>"
        )
    parts.append("</figure></div>")
    tag = '<span class="breakin">Break-in</span>' if entry.get("break_in") else ""
    parts.append(
        f'<div class="text"><div class="eyebrow"><span class="num">{key}</span>'
        f'<span class="kicker">Key idea {key}</span>{tag}</div>'
        f"<h2>{html.escape(entry['heading'])}</h2>"
    )
    parts.extend(f"<p>{html.escape(p)}</p>" for p in entry["paragraphs"])
    if also:
        parts.append(
            '<details class="also"><summary>Also in this stretch</summary>'
            f"<ul>{_step_items(rules, record, states, also)}</ul></details>"
        )
    parts.append("</div></section>")
    return "".join(parts), added


def _stuck(rules, stuck, early):
    """The stuck point: the candidates the search ended with, less `early`,
    the guide's early removals, on one grid."""
    held = {
        (r, c): set(digits)
        for r, row in enumerate(stuck["candidates"])
        for c, digits in enumerate(row)
    }
    held |= {tuple(o["cell"]): set(o["candidates"]) for o in stuck["outside"]}
    held = _less(held, early)
    why = (
        f"{stuck['timeouts']} proofs ran out of time"
        if stuck.get("timeouts")
        else "no further step was proved"
    )
    return (
        f'<section class="stuck"><p>The search is stuck here: {why}. '
        "These are the candidates left.</p>"
        f"{render(rules, held, prefix='stuck')}</section>"
    )


def _page(title, body):
    return (
        '<!DOCTYPE html>\n<html><head><meta charset="utf-8">'
        f"<title>{html.escape(title)}</title><style>{STYLE}</style></head>"
        f"<body>{body}</body></html>\n"
    )


def _image(image):
    return (
        f'<img class="original" src="{html.escape(image)}" alt="the original puzzle">'
    )


def plain_page(rules, image=None):
    """The rules file's plain render, beside the original image when given."""
    grid = render(rules, prefix="plain")
    body = f"<h1>{html.escape(rules.get('title', 'Rules file'))}</h1>"
    pair = (_image(image) if image else "") + grid
    return _page("Rules file render", body + f'<div class="sidebyside">{pair}</div>')


def guide_page(rules, record, guide, image=None):
    """The solve guide `guide`, a guide file as JSON parses it, draws for
    `record`, the image once at the top when given."""
    guide = guide_file.check(rules, record, guide)
    before = states(rules, record)
    body = [
        '<header class="intro"><div class="introtext">'
        '<div class="overline">Solve guide</div>'
        f"<h1>{html.escape(rules.get('title', 'Solve guide'))}</h1>"
    ]
    if image:
        body.append(_image(image))
    if rules.get("rules_text"):
        body.append(f'<p class="rules">{html.escape(rules["rules_text"])}</p>')
    body.append("</div>")
    body.append(render(rules, prefix="start"))
    body.append("</header>")
    keys, early = 0, {}
    solution = _known_solution(rules, before[len(record["steps"]) + 1])
    for k, entry in enumerate(guide["entries"], 1):
        if entry["type"] == "fill":
            body.append(_fill(rules, entry, record, before))
            continue
        keys += 1
        section, added = _key_section(
            rules, entry, record, before, early, solution, key=keys, entry_number=k
        )
        body.append(section)
        for cell, digits in added.items():
            early[cell] = early.get(cell, set()) | digits
    if record.get("stuck"):
        body.append(_stuck(rules, record["stuck"], early))
    return _page("Solve guide", "".join(body))
