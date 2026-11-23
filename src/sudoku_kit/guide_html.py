"""The solve guide as an HTML page: the key ideas of a step record, each on
its own SVG grid, and the fill between them, redrawn from the rules file
(specs #106 and #127).

`deductions(rules, record)` groups the record's steps into deductions. A step
joins an earlier deduction naming the same set of constraints, adjacent or
not, unless a step between them changed a cell that deduction uses (a cell of
its named constraints or of its claims). A step whose claim is a chain or an
`either` is a deduction of its own. A deduction sits at its last step's
position. Grouping and the key ideas are computed from the record alone, so
two runs over the same record give the same guide.

A deduction is a key idea when it is the break-in (the first deduction that
names a clue), names two or more constraints, is the first to name a clue of
its rule type, or is hard (more than 3 named constraints, which the second
rule already takes). Key ideas are numbered 1..N. Each stretch of deductions
between them is fill: one sentence counting its placements and eliminations
and naming its houses and clues, with a collapsed list of its deductions. A
stuck record ends the guide with the grid and candidates at the stuck point.

Each deduction, key idea or fill, shows one reason sentence built from its
named constraints by `reasons.reason`. A key idea's grid draws the candidates before it, with the digits it removes
struck out. Cells of the constraints it names are marked `used` and the cells
it changes `changed`. A chain claim is drawn as arrows along the chain, and an
`either` claim circles each pattern's cells. A step may also carry, written
there by the skill, and shown only on a key idea:

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

from sudoku_kit import reasons, rules_file, step_search

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


def key_ideas(rules, groups):
    """The indices into `groups` of its key ideas, and the break-in's index
    or None."""
    houses = rules_file.house_names(rules)
    rule_of = {clue["id"]: clue["rule"] for clue in rules["clues"]}
    keys, seen, first = [], set(), None
    for i, group in enumerate(groups):
        clues = [rule_of[n] for n in group["named"] if n not in houses]
        new_rule = any(rule not in seen for rule in clues)
        seen.update(clues)
        if clues and first is None:
            first = i
        if i == first or len(group["named"]) >= 2 or new_rule:
            keys.append(i)
    return keys, first


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


def render(rules, candidates=None, idea=None, prefix="g"):
    """One grid as an SVG string. `candidates` ({cell: digits}) draws each
    cell's digits; without it only givens show. `idea`, a key idea (a
    deduction with its `key` number, `annotations` and `removed`, {cell:
    digits}), marks its cells and strikes out what it removes."""
    grid = Grid(rules)
    registry = rules_file.registry(rules)
    used, changed, removed, notes = set(), set(), {}, []
    if idea is not None:
        for name in idea["named"]:
            used.update(registry[name].cells)
        for claim in idea["claims"]:
            cells, marks = _claim_marks(claim)
            changed |= cells
            notes += marks
        removed = idea["removed"]
        notes += idea["annotations"]
    out = [
        f'<svg class="grid" xmlns="http://www.w3.org/2000/svg" '
        f'viewBox="0 0 {grid.columns * CELL} {grid.rows * CELL}"'
        + (f' data-key="{idea["key"]}"' if idea is not None else "")
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
    marked = used | changed if idea is not None else None
    for cell in rules_file.cells(rules):
        out.extend(
            _digits(grid, cell, candidates, removed.get(cell, set()), marked)
        )
    out.extend(_annotation(grid, note, prefix) for note in notes)
    out.append("</svg>")
    return "".join(out)


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
        f'y2="{grid.y(d)}" stroke="#000" stroke-width="2.5"/>'
        for a, b, c, d in edges
    ]


def _digits(grid, cell, candidates, removed, marked=None):
    """A cell's given, placed digit or candidates; with `marked`, a cell
    outside it shows only its placed digit."""
    x, y = grid.centre(cell)
    given = grid.givens.get(cell)
    if given is not None:
        return [_text(x, y + 9, "given", given)]
    if candidates is None:
        return []
    held = candidates[cell]
    if len(held) == 1:
        return [_text(x, y + 9, "solved", next(iter(held)))]
    if marked is not None and cell not in marked:
        return []
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


def _describe(claim):
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


def _claims(group):
    return ", ".join(_describe(claim) for claim in group["claims"])


def _steps_attr(group):
    return " ".join(map(str, group["steps"]))


def _plural(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


def _fill(rules, groups, before):
    """One stretch of fill: a sentence, then its deductions collapsed."""
    houses = rules_file.house_names(rules)
    rule_of = {clue["id"]: clue["rule"] for clue in rules["clues"]}
    placed = removed = 0
    for group in groups:
        for number, claim in zip(group["steps"], group["claims"], strict=True):
            if "cell" not in claim:
                continue
            held = before[number][tuple(claim["cell"])]
            if len(claim["digits"]) == 1:
                placed += 1
            else:
                removed += len(held) - len(claim["digits"])
    names = dict.fromkeys(n for g in groups for n in g["named"])
    sources = [n for n in names if n in houses]
    clues = [rule_of[n] for n in names if n not in houses]
    for rule in dict.fromkeys(clues):
        kind = rule.replace("_", " ")
        sources.append(_plural(clues.count(rule), f"{kind} clue"))
    made = [_plural(placed, "digit") + " placed"] if placed else []
    if removed:
        made.append(_plural(removed, "candidate") + " removed")
    if not made:
        made = ["no candidate changed"]
    using = (
        ", ".join(sources[:-1]) + " and " + sources[-1]
        if len(sources) > 1
        else sources[0]
    )
    items = "".join(
        f'<li class="deduction" data-steps="{_steps_attr(g)}">'
        f"{html.escape(_claims(g))}. "
        f'<span class="reason">{html.escape(reasons.reason(rules, g["named"]))}</span></li>'
        for g in groups
    )
    return (
        f'<div class="fill"><p class="fill">Fill: {" and ".join(made)}, from '
        f"{html.escape(using)}.</p><details><summary>The "
        f"{_plural(len(groups), 'deduction')}</summary><ul>{items}</ul></details></div>"
    )


def _key_section(rules, number, group, record, before, is_break_in):
    """One key idea: its heading, labels, grid and any text the skill wrote."""
    steps = [record["steps"][i - 1] for i in group["steps"]]
    held = dict(before[group["steps"][-1]])
    removed = {}
    for i, claim in zip(group["steps"], group["claims"], strict=True):
        if "cell" not in claim:
            continue
        cell = tuple(claim["cell"])
        if cell not in removed:
            held[cell] = before[i][cell]
        removed[cell] = held[cell] - set(claim["digits"])
    idea = dict(
        group,
        key=number,
        removed=removed,
        annotations=[note for s in steps for note in s.get("annotations", [])],
    )
    named = group["named"]
    parts = [
        f'<section class="key" data-key="{number}" data-steps="{_steps_attr(group)}">'
        f"<h2>Key idea {number}: {html.escape(_claims(group))}</h2>",
    ]
    if is_break_in:
        parts.append(
            '<p class="breakin">Break-in: the first deduction that needs a clue.</p>'
        )
    if len(named) > step_search.HARD:
        parts.append(
            f'<p class="hard">Hard step: it uses {len(named)} constraints together.</p>'
        )
    parts += [
        f'<p class="reason">{html.escape(reasons.reason(rules, named))}</p>',
        render(rules, held, idea, prefix=f"k{number}"),
    ]
    parts.extend(f"<p>{html.escape(s['text'])}</p>" for s in steps if s.get("text"))
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
    groups = deductions(rules, record)
    keys, first = key_ideas(rules, groups)
    stretch = []
    for i, group in enumerate(groups):
        if i not in keys:
            stretch.append(group)
            continue
        if stretch:
            body.append(_fill(rules, stretch, before))
            stretch = []
        number = keys.index(i) + 1
        body.append(_key_section(rules, number, group, record, before, i == first))
    if stretch:
        body.append(_fill(rules, stretch, before))
    if record.get("stuck"):
        body.append(_stuck(rules, record["stuck"]))
    return _page("Solve guide", "".join(body))
