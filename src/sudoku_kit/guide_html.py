"""The solve guide as an HTML page: the main steps of a step record, each on
its own SVG grid, redrawn from the rules file (spec #106).

`shown(rules, record)` picks the main steps mechanically, so two runs over the
same record show the same ones. A step is shown when it names a clue (a
variant rule) or two or more constraints, or when it carries a chain or
`either` claim. Every other step names one row, column or region, and each
unbroken run of those collapses into one line. The break-in (`break_in`) is
the first step that names a clue or two or more constraints: its section is
labelled, and a hard step (more than 3 named constraints) is marked as hard.
A stuck record ends the guide with the grid and candidates at the stuck point.

A shown step's grid draws the candidates before the step, with the digits the
step removes struck out. Cells of the constraints it names are marked `used`
and the cell it changes `changed`. A chain claim is drawn as arrows along the
chain, and an `either` claim circles each pattern's cells. A step may also
carry, written there by the skill:

- `text`: a sentence shown under its grid.
- `annotations`: a list of `{"type": "arrow", "from": cell, "to": cell}`,
  `{"type": "circle", "cell": cell}` and `{"type": "label", "cell": cell,
  "text": ...}`, each cell a [row, column] pair.

`render(rules)` is the plain grid, givens and clues only; `plain_page` puts it
beside the original image for the import comparison, and `guide_page` is the
whole guide with the image once at the top.
"""

import html
import itertools

from sudoku_kit import rules_file, step_search

CELL = 48
LINE_COLOURS = {
    "thermo": "#999",
    "slow_thermo": "#999",
    "renban": "#a6c",
    "whisper": "#4a4",
    "lockout": "#e83",
    "arrow": "#555",
}
STYLE = """
body { font-family: sans-serif; max-width: 52rem; margin: 2rem auto; }
svg.grid { width: 24rem; height: auto; display: block; }
img.original { max-width: 24rem; }
.sidebyside { display: flex; gap: 2rem; align-items: flex-start; }
.cell { fill: #fff; stroke: #bbb; }
.cell.used { fill: #cfe3ff; }
.cell.changed { fill: #ffe08a; }
.given { font-weight: bold; font-size: 26px; }
.solved { font-size: 26px; fill: #236; }
.cand { font-size: 11px; fill: #555; }
.cand.struck { fill: #c22; text-decoration: line-through; }
.breakin, .hard { font-weight: bold; color: #b00; }
.label { font-size: 12px; fill: #b00; font-weight: bold; }
.arrow, .circle { stroke: #c22; fill: none; stroke-width: 3; }
"""


def _single_house(rules, step):
    """True when the step names exactly one row, column or region."""
    houses = rules_file.house_names(rules)
    return len(step["named"]) == 1 and step["named"][0] in houses


def break_in(rules, record):
    """The number of the first step naming a clue or two or more constraints,
    or None when there is no such step."""
    return next(
        (
            i
            for i, step in enumerate(record["steps"], 1)
            if not _single_house(rules, step)
        ),
        None,
    )


def shown(rules, record):
    """The guide's items in step order: ("step", number, step) for a shown
    step and ("singles", [numbers], [steps]) for each run of the rest. Step
    numbers count from 1."""
    steps = record["steps"]
    items, run = [], []
    for i, step in enumerate(steps, 1):
        main = (
            not _single_house(rules, step)
            or "chain" in step["claim"]
            or "either" in step["claim"]
        )
        if not main:
            run.append((i, step))
            continue
        if run:
            items.append(("singles", [i for i, _ in run], [s for _, s in run]))
            run = []
        items.append(("step", i, step))
    if run:
        items.append(("singles", [i for i, _ in run], [s for _, s in run]))
    return items


def _states(rules, record):
    """The candidates before each step, by step number from 1."""
    state = step_search.State(rules)
    before = {}
    for i, step in enumerate(record["steps"], 1):
        before[i] = dict(state.candidates)
        state.apply(step_search.claim_from_json(step["claim"]))
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


def _cell_class(cell, used, changed):
    classes = ["cell"]
    if cell in used:
        classes.append("used")
    if cell in changed:
        classes.append("changed")
    return " ".join(classes)


def _text(x, y, cls, text, **data):
    attrs = "".join(f' data-{k}="{html.escape(str(v))}"' for k, v in data.items())
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
            f'r="6" fill="{fill}" stroke="#000" data-clue="{html.escape(clue["id"])}"/>'
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


def _annotation(grid, note, prefix):
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
            f'<circle class="circle" cx="{x:.1f}" cy="{y:.1f}" r="{CELL / 2 - 3}" '
            f'data-cell="{rules_file.cell_name(note["cell"])}"/>'
        )
    if kind == "label":
        x, y = grid.centre(note["cell"])
        return _text(
            x,
            y + CELL / 2 - 4,
            "label",
            note["text"],
            cell=rules_file.cell_name(note["cell"]),
        )
    raise ValueError(f"annotation {note!r} has no known type (arrow, circle, label)")


def _claim_marks(claim):
    """(changed cells, default annotations) the claim gives."""
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


def render(rules, candidates=None, step=None, prefix="g"):
    """One grid as an SVG string. `candidates` ({cell: digits}) draws each
    cell's digits; without it only givens show. `step` marks that step's cells
    and strikes out what it removes."""
    grid = Grid(rules)
    registry = rules_file.registry(rules)
    used, changed, removed, notes = set(), set(), {}, []
    if step is not None:
        for name in step["named"]:
            used.update(registry[name].cells)
        claim = step["claim"]
        changed, notes = _claim_marks(claim)
        if "cell" in claim:
            cell = tuple(claim["cell"])
            removed[cell] = candidates[cell] - set(claim["digits"])
        notes = notes + step.get("annotations", [])
    out = [
        f'<svg class="grid" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {grid.columns * CELL} {grid.rows * CELL}"'
        + (f' data-step="{step["number"]}"' if step is not None else "")
        + ">",
        f'<defs><marker id="{prefix}-head" markerWidth="8" markerHeight="8" refX="6" '
        'refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="#c22"/></marker></defs>',
    ]
    out.extend(
        f'<rect class="{_cell_class(cell, used, changed)}" '
        f'x="{grid.x(cell[1])}" y="{grid.y(cell[0])}" width="{CELL}" '
        f'height="{CELL}" data-cell="{rules_file.cell_name(cell)}"/>'
        for cell in rules_file.cells(rules)
    )
    out.extend(_house_edges(grid))
    out.extend(_clue(grid, clue) for clue in rules["clues"])
    for cell in rules_file.cells(rules):
        out.extend(_digits(grid, cell, candidates, removed.get(cell, set())))
    out.extend(_annotation(grid, note, prefix) for note in notes)
    out.append("</svg>")
    return "".join(out)


def _house_edges(grid):
    """Thick lines on the board's outline and between regions."""
    n, edges = grid.n, []
    for r in range(n):
        for c in range(n):
            region = grid.region.get((r, c))
            if c == n - 1 or grid.region.get((r, c + 1)) != region:
                edges.append((c + 1, r, c + 1, r + 1))
            if r == n - 1 or grid.region.get((r + 1, c)) != region:
                edges.append((c, r + 1, c + 1, r + 1))
            if c == 0:
                edges.append((c, r, c, r + 1))
            if r == 0:
                edges.append((c, r, c + 1, r))
    return [
        f'<line class="edge" x1="{grid.x(a)}" y1="{grid.y(b)}" x2="{grid.x(c)}" '
        f'y2="{grid.y(d)}" stroke="#000" stroke-width="2.5"/>'
        for a, b, c, d in edges
    ]


def _digits(grid, cell, candidates, removed):
    x, y = grid.centre(cell)
    given = grid.givens.get(cell)
    if given is not None:
        return [_text(x, y + 9, "given", given)]
    if candidates is None:
        return []
    held = candidates[cell]
    if len(held) == 1:
        return [_text(x, y + 9, "solved", next(iter(held)))]
    drawn = held | removed
    if len(drawn) == grid.n and not removed:
        return []
    out = []
    for d in sorted(drawn):
        dx = grid.x(cell[1]) + CELL * (1 + (d - 1) % 3) / 4
        dy = grid.y(cell[0]) + CELL * (1 + (d - 1) // 3) / 4 + 4
        cls = "cand struck" if d in removed else "cand"
        out.append(_text(dx, dy, cls, d, cell=rules_file.cell_name(cell), digit=d))
    return out


def _describe(step):
    claim = step["claim"]
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


def _singles(numbers, steps):
    span = f"{numbers[0]}-{numbers[-1]}"
    houses = ", ".join(dict.fromkeys(n for s in steps for n in s["named"]))
    claims = "; ".join(_describe(s) for s in steps)
    label = f"Step {numbers[0]}" if len(numbers) == 1 else f"Steps {span}"
    return (
        f'<p class="singles" data-steps="{span}">{label}: {len(steps)} from '
        f"{html.escape(houses)} alone. {html.escape(claims)}.</p>"
    )


def _step_section(rules, number, step, before, is_break_in):
    named = ", ".join(step["named"])
    drawn = dict(step, number=number)
    parts = [
        f"<section><h2>Step {number}: {html.escape(_describe(step))}</h2>",
    ]
    if is_break_in:
        parts.append(
            '<p class="breakin">Break-in: the first step that needs a clue.</p>'
        )
    if len(step["named"]) > step_search.HARD:
        parts.append(
            f'<p class="hard">Hard step: it uses {len(step["named"])} constraints '
            "together.</p>"
        )
    parts += [
        f"<p>Uses {html.escape(named)}.</p>",
        render(rules, before, drawn, prefix=f"s{number}"),
    ]
    if step.get("text"):
        parts.append(f"<p>{html.escape(step['text'])}</p>")
    parts.append("</section>")
    return "".join(parts)


def _stuck(rules, stuck):
    """The stuck point: the candidates the search ended with, on one grid."""
    held = {
        (r, c): set(digits)
        for r, row in enumerate(stuck["candidates"])
        for c, digits in enumerate(row)
    }
    held |= {tuple(o["cell"]): set(o["candidates"]) for o in stuck["outside"]}
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


def guide_page(rules, record, image=None):
    """The solve guide for `record`, the image once at the top when given."""
    before = _states(rules, record)
    body = [f"<h1>{html.escape(rules.get('title', 'Solve guide'))}</h1>"]
    if image:
        body.append(_image(image))
    first = break_in(rules, record)
    for item in shown(rules, record):
        if item[0] == "singles":
            body.append(_singles(item[1], item[2]))
        else:
            _, number, step = item
            body.append(
                _step_section(rules, number, step, before[number], number == first)
            )
    if record.get("stuck"):
        body.append(_stuck(rules, record["stuck"]))
    return _page("Solve guide", "".join(body))
