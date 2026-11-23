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
of the record exactly once, in order. `check_guide` refuses one that does
not, or that flags more than one break-in, naming the problem. The page opens
with the title, the original image once when given, the rules file's
`rules_text` and the plain grid of the starting position.

The library numbers key ideas 1..N in file order and shows the break-in label
on the flagged one; every other word is the skill's. A key idea is one row:
its grid on the left at half the page grid's width, and its numbered heading
and paragraphs on the right, so about 2 to 3 print per page. Its grid draws
the candidates before its first step only in the cells its steps use or
change, with the digits they remove struck out; every other cell shows its
placed digit or stays blank. Cells of the constraints its steps name are
marked `used` and the cells they change `changed`. A chain claim is drawn as
arrows along the chain, and an `either` claim circles each pattern's cells.

A fill stretch is the skill's one sentence over a collapsed list with one
line per step, written here: the claim, then each named constraint in words
(`constraint_words`), never a clue id. A stuck record ends the guide with the
grid and candidates at the stuck point.

`render(rules)` is the plain grid, givens and clues only; `plain_page` puts it
beside the original image for the import comparison.
"""

import html
import itertools
import json
from pathlib import Path

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
section.key { display: flex; gap: 1.5rem; align-items: flex-start;
  margin: 1.5rem 0; break-inside: avoid; }
section.key svg.grid { width: 12rem; flex: none; }
section.key h2 { font-size: 1.1rem; margin: 0 0 0.5rem; }
section.key p { margin: 0.4rem 0; }
img.original { max-width: 24rem; }
.sidebyside { display: flex; gap: 2rem; align-items: flex-start; }
.cell { fill: #fff; stroke: #bbb; }
.cell.used { fill: #cfe3ff; }
.cell.changed { fill: #ffe08a; }
.given { font-weight: bold; font-size: 26px; }
.solved { font-size: 26px; fill: #236; }
.cand { font-size: 14px; fill: #555; }
.cand.struck { fill: #c22; text-decoration: line-through; }
.breakin { font-weight: bold; color: #b00; }
.rules { white-space: pre-line; }
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


def _states(rules, record):
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
    raise ValueError(f"mark {note!r} has no known type (arrow, circle)")


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


def render(rules, candidates=None, idea=None, prefix="g"):
    """One grid as an SVG string. `candidates` ({cell: digits}) draws each
    cell's digits; without it only givens show. `idea`, a key idea (its `key`
    number, the `named` constraints and `claims` of its steps, and `removed`,
    {cell: digits}), marks its cells and strikes out what it removes."""
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
        out.extend(_digits(grid, cell, candidates, removed.get(cell, set()), marked))
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


def _list(words):
    return ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]


def _plural(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


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


def constraint_words(rules, name):
    """A named constraint as a solver reads it: a house by its name, a clue by
    its kind and its cells (first to last, or the outside cell of a clue read
    from outside), never by its id."""
    if name in rules_file.house_names(rules):
        return name
    clue = next(c for c in rules["clues"] if c["id"] == name)
    cells = [rules_file.cell_name(c) for c in clue["cells"]]
    if clue["rule"] in OUTSIDE_RULES or len(cells) == 1:
        where = cells[0]
    else:
        where = f"{cells[0]}-{cells[-1]}"
    value = clue["values"][0] if clue["values"] else None
    return f"{CLUE_WORDS[clue['rule']](value)} {where}"


def _step_line(rules, step):
    named = [constraint_words(rules, name) for name in step["named"]]
    return f"{_describe(step['claim'])}, from {_list(named)}."


GUIDE_VERSION = 1
ENTRY_FIELDS = {
    "key": ({"heading", "paragraphs"}, {"break_in"}),
    "fill": ({"sentence"}, set()),
}


def load_guide(path):
    """The guide file at `path`, parsed; `check_guide` judges its contents."""
    try:
        return json.loads(Path(path).read_text())
    except OSError as e:
        raise ValueError(f"cannot read guide file {path}: {e.strerror}") from e
    except ValueError as e:
        raise ValueError(f"guide file {path} is not JSON: {e}") from e


def _check_entry(k, entry, total):
    if not isinstance(entry, dict):
        raise ValueError(f"entry {k} is not a JSON object: {str(entry)[:60]!r}")
    kind = entry.get("type")
    if kind not in ENTRY_FIELDS:
        raise ValueError(f"entry {k} has type {kind!r}; an entry is 'key' or 'fill'")
    required, optional = ENTRY_FIELDS[kind]
    required = required | {"first", "last"}
    unknown = set(entry) - required - optional - {"type"}
    if unknown:
        raise ValueError(f"entry {k} ({kind}) has unknown fields {sorted(unknown)}")
    missing = required - set(entry)
    if missing:
        raise ValueError(f"entry {k} ({kind}) has no {sorted(missing)}")
    for field in ("first", "last"):
        value = entry[field]
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"entry {k}'s {field} {value!r} is not a step number")
    first, last = entry["first"], entry["last"]
    if first < 1:
        raise ValueError(f"entry {k} starts at step {first}; steps count from 1")
    if first > last:
        raise ValueError(f"entry {k} has its first {first} after its last {last}")
    if last > total:
        raise ValueError(
            f"entry {k} reaches step {last}, past the record's {_plural(total, 'step')}"
        )
    for field in ("heading", "sentence"):
        if field in entry and not isinstance(entry[field], str):
            raise ValueError(f"entry {k}'s {field} is not a string")
    paragraphs = entry.get("paragraphs", [])
    if not isinstance(paragraphs, list) or not all(
        isinstance(p, str) for p in paragraphs
    ):
        raise ValueError(f"entry {k}'s paragraphs is not a list of strings")
    if not isinstance(entry.get("break_in", False), bool):
        raise ValueError(f"entry {k}'s break_in is not true or false")


def check_guide(record, guide):
    """Refuse, naming the problem, a guide file that is malformed, that skips,
    repeats or reorders a step of `record`, or that flags more than one
    break-in."""
    if not isinstance(guide, dict):
        raise ValueError(f"the guide file is not a JSON object: {str(guide)[:60]!r}")
    version = guide.get("version")
    if version != GUIDE_VERSION:
        raise ValueError(
            f"the guide file has version {version!r}; "
            f"only version {GUIDE_VERSION} is read"
        )
    entries = guide.get("entries")
    if not isinstance(entries, list):
        raise ValueError("the guide file has no entries list")
    total = len(record["steps"])
    for k, entry in enumerate(entries, 1):
        _check_entry(k, entry, total)
    flagged = [str(k) for k, e in enumerate(entries, 1) if e.get("break_in")]
    if len(flagged) > 1:
        raise ValueError(
            f"entries {_list(flagged)} each flag the break-in; a guide has one at most"
        )
    covered = {}
    for k, entry in enumerate(entries, 1):
        for step in range(entry["first"], entry["last"] + 1):
            if step in covered:
                raise ValueError(
                    f"entry {k} repeats step {step}, already in entry {covered[step]}"
                )
            covered[step] = k
    missing = [step for step in range(1, total + 1) if step not in covered]
    if missing:
        more = f" and {len(missing) - 1} more" if len(missing) > 1 else ""
        raise ValueError(f"the guide file skips step {missing[0]}{more}")
    for k, (a, b) in enumerate(itertools.pairwise(entries), 2):
        if b["first"] < a["first"]:
            raise ValueError(
                f"entry {k} is out of order: steps {b['first']}-{b['last']} come "
                f"after steps {a['first']}-{a['last']} of entry {k - 1}"
            )


def _fill(rules, entry, record):
    """One stretch of fill: the skill's sentence, then a line per step."""
    numbers = range(entry["first"], entry["last"] + 1)
    items = "".join(
        f'<li class="step" data-step="{i}">'
        f"{html.escape(_step_line(rules, record['steps'][i - 1]))}</li>"
        for i in numbers
    )
    return (
        f'<div class="fill" data-steps="{entry["first"]}-{entry["last"]}">'
        f'<p class="fill">{html.escape(entry["sentence"])}</p><details><summary>The '
        f"{_plural(len(numbers), 'step')}</summary><ul>{items}</ul></details></div>"
    )


def _key_section(rules, number, entry, record, before):
    """One key idea as one row: its grid, then its numbered heading, the
    break-in label when flagged, and its paragraphs."""
    first, last = entry["first"], entry["last"]
    numbers = range(first, last + 1)
    steps = [record["steps"][i - 1] for i in numbers]
    claims = [step["claim"] for step in steps]
    held, after = before[first], before[last + 1]
    changed = {tuple(c["cell"]) for c in claims if "cell" in c}
    idea = {
        "key": number,
        "named": list(dict.fromkeys(n for step in steps for n in step["named"])),
        "claims": claims,
        "removed": {cell: held[cell] - after[cell] for cell in changed},
    }
    parts = [
        f'<section class="key" data-key="{number}" '
        f'data-steps="{" ".join(map(str, numbers))}">',
        render(rules, held, idea, prefix=f"k{number}"),
        f'<div class="text"><h2>Key idea {number}: {html.escape(entry["heading"])}</h2>',
    ]
    if entry.get("break_in"):
        parts.append('<p class="breakin">Break-in</p>')
    parts.extend(f"<p>{html.escape(p)}</p>" for p in entry["paragraphs"])
    parts.append("</div></section>")
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


def guide_page(rules, record, guide, image=None):
    """The solve guide `guide`, a guide file as `load_guide` reads it, draws
    for `record`, the image once at the top when given."""
    check_guide(record, guide)
    before = _states(rules, record)
    body = [f"<h1>{html.escape(rules.get('title', 'Solve guide'))}</h1>"]
    if image:
        body.append(_image(image))
    if rules.get("rules_text"):
        body.append(f'<p class="rules">{html.escape(rules["rules_text"])}</p>')
    body.append(render(rules, prefix="start"))
    keys = 0
    for entry in guide["entries"]:
        if entry["type"] == "fill":
            body.append(_fill(rules, entry, record))
            continue
        keys += 1
        body.append(_key_section(rules, keys, entry, record, before))
    if record.get("stuck"):
        body.append(_stuck(rules, record["stuck"]))
    return _page("Solve guide", "".join(body))
