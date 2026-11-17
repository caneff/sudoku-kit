"""SudokuPad puzzle JSON to a rules file, for normal sudoku plus Kropki dots and
coloured lines (thermo, renban, whispers).

`rules_file(puzzle)` reads the grid, regions, givens and stored solution, and
turns each dot overlay into clues. The puzzle's rules text picks the reading:
a sentence naming white dots and "consecutive" reads white as difference 1; a
sentence naming black dots and "2:1", "ratio" or "double" reads black as
ratio 2. A dot on an edge joins the two cells either side of it. A dot on a
grid corner joins both diagonal pairs around it, and is read only when the
rules text says "diagonal".

A line's colour picks its rule through the rules text, the same way: a
sentence naming a colour (orange, pink, grey) and "whisper", "renban" or
"thermo" reads that colour as that rule. A whisper's smallest step is the
number after "at least" in the sentence (4 for Dutch whispers, 5 for German);
a sentence with "slow" reads a thermo as slow. The bulb of a thermo is the
round underlay under one end of its line, and the path is written from it.
Waypoints run along cell centres, straight or diagonal, and fill in the cells
between. Lockout lines are not read.

Any shape it does not read (an arrow, a cage, an underlay that is not a
thermo's bulb, a line whose colour the text does not name, any other overlay)
is refused by name, so a rule is never dropped silently; a rules file for such
a puzzle is written by hand. Every refusal is a ValueError.
"""

import colorsys
import itertools
import re

from sudoku_kit.rules_file import validate

PREVIEW_CHARACTERS = 80
COLOURS = {
    "white": {"#fff", "#ffff", "#ffffff", "#ffffffff", "white"},
    "black": {"#000", "#000f", "#000000", "#000000ff", "black"},
}
READINGS = {
    "white": (re.compile(r"consecutive"), "difference", 1),
    "black": (re.compile(r"2:1|ratio|double"), "ratio", 2),
}
DOT_MAX_SIZE = 0.5
UNREAD_KINDS = ("arrows",)
LINE_RULES = (
    ("whisper", re.compile(r"whisper")),
    ("renban", re.compile(r"renban")),
    ("thermo", re.compile(r"thermo")),
)


def _preview(item):
    return repr(item)[:PREVIEW_CHARACTERS]


def _colour(overlay):
    """ "white" or "black" for a Kropki dot overlay, else None."""
    size = (overlay.get("width"), overlay.get("height"))
    if not overlay.get("rounded") or size[0] != size[1] or not size[0]:
        return None
    if size[0] > DOT_MAX_SIZE:
        return None
    fill = str(overlay.get("backgroundColor", "")).lower()
    return next((name for name, fills in COLOURS.items() if fill in fills), None)


def _readings(text):
    """{colour: (rule, value)} for each colour a sentence of `text` reads."""
    sentences = re.split(r"[.;\n]", text.lower())
    found = {}
    for colour, (pattern, rule, value) in READINGS.items():
        if any(colour in s and pattern.search(s) for s in sentences):
            found[colour] = (rule, value)
    return found


def _pairs(center, n, diagonal, overlay):
    """The cell pairs a dot at `center` joins."""
    y2, x2 = (round(2 * v) for v in center)
    if (y2, x2) != tuple(2 * v for v in center):
        raise ValueError(f"a dot off the grid's half-cell lines: {_preview(overlay)}")
    if y2 % 2 and x2 % 2:
        raise ValueError(f"a dot in the middle of a cell: {_preview(overlay)}")
    if y2 % 2:  # on a vertical edge
        r, c = y2 // 2, x2 // 2
        pairs = [((r, c - 1), (r, c))]
    elif x2 % 2:  # on a horizontal edge
        r, c = y2 // 2, x2 // 2
        pairs = [((r - 1, c), (r, c))]
    else:
        if not diagonal:
            raise ValueError(
                "a dot on a grid corner, and the rules text never says "
                f"diagonal: {_preview(overlay)}"
            )
        r, c = y2 // 2, x2 // 2
        pairs = [((r - 1, c - 1), (r, c)), ((r - 1, c), (r, c - 1))]
    on_board = [p for p in pairs if all(0 <= i < n for cell in p for i in cell)]
    if not on_board:
        raise ValueError(f"a dot joining no two cells of the grid: {_preview(overlay)}")
    return on_board


def _name(cell):
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def _refuse_unread(puzzle):
    for kind in UNREAD_KINDS:
        if puzzle.get(kind):
            raise ValueError(
                f"the importer does not read {kind}: {_preview(puzzle[kind][0])}"
            )
    for cage in puzzle.get("cages") or []:
        if cage.get("cells"):
            raise ValueError(f"the importer does not read cages: {_preview(cage)}")
    for overlay in puzzle.get("overlays") or []:
        if _colour(overlay) is None:
            raise ValueError(
                f"the importer does not read overlays other than black and white "
                f"dots: {_preview(overlay)}"
            )


def _hue_name(colour):
    """ "orange", "pink", "grey", "black" or "white" for a SudokuPad hex colour
    (#rgb, #rgba, #rrggbb or #rrggbbaa, alpha ignored), else None."""
    digits = str(colour).lstrip("#")
    if len(digits) in (3, 4):
        digits = "".join(d * 2 for d in digits)
    try:
        r, g, b = (int(digits[i : i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        return None
    h, sat, v = colorsys.rgb_to_hsv(r, g, b)
    if sat < 0.2:
        return "black" if v < 0.15 else "white" if v > 0.85 else "grey"
    degrees = h * 360
    if 20 <= degrees <= 50:
        return "orange"
    if 280 <= degrees <= 345:
        return "pink"
    return None


def _line_readings(text):
    """{colour: (rule, value)} for each line colour a sentence of `text`
    names beside a line word."""
    found = {}
    for sentence in re.split(r"[.;\n]", text.lower()):
        rule = next((r for r, pat in LINE_RULES if pat.search(sentence)), None)
        if rule is None:
            continue
        value = None
        if rule == "whisper":
            at_least = re.search(r"at least (\d+)", sentence)
            if not at_least:
                raise ValueError(
                    f"a whispers sentence with no 'at least <number>': {_preview(sentence)}"
                )
            value = int(at_least.group(1))
        if rule == "thermo" and "slow" in sentence:
            rule = "slow_thermo"
        for colour in ("orange", "pink", "grey", "gray"):
            if colour in sentence:
                found["grey" if colour == "gray" else colour] = (rule, value)
    return found


def _path(line):
    """The cells a line's waypoints run through, centre to centre in straight
    or diagonal steps."""
    points = []
    for point in line["wayPoints"]:
        cell = tuple(round(v - 0.5) for v in point)
        if any(abs(v - 0.5 - c) > 1e-6 for v, c in zip(point, cell, strict=False)):
            raise ValueError(f"a line off the cell centres: {_preview(line)}")
        points.append(cell)
    cells = [points[0]]
    for (r0, c0), (r1, c1) in itertools.pairwise(points):
        dr, dc = r1 - r0, c1 - c0
        if dr and dc and abs(dr) != abs(dc):
            raise ValueError(f"a line bending between cells: {_preview(line)}")
        steps = max(abs(dr), abs(dc))
        if not steps:
            continue
        cells += [
            (r0 + dr // steps * k, c0 + dc // steps * k) for k in range(1, steps + 1)
        ]
    return cells


def _bulb_ends(underlays):
    """The cells that carry a round underlay, the bulbs a thermo may start at."""
    return {
        tuple(round(v - 0.5) for v in u["center"])
        for u in underlays
        if u.get("rounded")
        and all(abs(v - 0.5 - round(v - 0.5)) < 1e-6 for v in u["center"])
    }


def _line_clues(puzzle, n, text):
    lines = puzzle.get("lines") or []
    underlays = puzzle.get("underlays") or []
    readings = _line_readings(text)
    bulbs, used, clues, seen = _bulb_ends(underlays), set(), [], set()
    for line in lines:
        colour = _hue_name(line.get("color", ""))
        if colour not in readings:
            raise ValueError(
                "the importer does not read lines of colour "
                f"{colour or line.get('color')}: the rules text gives no reading "
                f"for it: {_preview(line)}"
            )
        rule, value = readings[colour]
        cells = _path(line)
        if rule in ("thermo", "slow_thermo"):
            if cells[0] in bulbs:
                used.add(cells[0])
            elif cells[-1] in bulbs:
                cells.reverse()
                used.add(cells[0])
            else:
                raise ValueError(f"a thermo line with no bulb: {_preview(line)}")
        key = (rule, tuple(cells))
        if key in seen or key[1][::-1] in {k[1] for k in seen if k[0] == rule}:
            continue
        seen.add(key)
        base = f"{rule}-{_name(cells[0])}-{_name(cells[-1])}"
        clue_id = base
        while clue_id in {c["id"] for c in clues}:
            clue_id += "-b"
        clues.append(
            {
                "id": clue_id,
                "rule": rule,
                "cells": [list(c) for c in cells],
                "values": [] if value is None else [value],
            }
        )
    for underlay in underlays:
        centre = tuple(round(v - 0.5) for v in underlay["center"])
        if centre not in used or not underlay.get("rounded"):
            raise ValueError(
                "the importer does not read underlays other than a thermo's "
                f"bulb: {_preview(underlay)}"
            )
    return clues


def _solution(text, n):
    if text is None:
        return None
    if len(text) != n * n or not text.isdigit():
        raise ValueError(f"the stored solution is not {n * n} digits: {text!r}")
    return [[int(d) for d in text[r * n : (r + 1) * n]] for r in range(n)]


def _clues(puzzle, n, text):
    readings = _readings(text)
    diagonal = "diagonal" in text.lower()
    seen, clues = set(), []
    for overlay in puzzle.get("overlays") or []:
        colour = _colour(overlay)
        key = (colour, *(round(2 * v) for v in overlay["center"]))
        if key in seen:
            continue
        seen.add(key)
        if colour not in readings:
            raise ValueError(
                f"the rules text gives no reading for a {colour} dot: {_preview(text)}"
            )
        rule, value = readings[colour]
        for a, b in _pairs(overlay["center"], n, diagonal, overlay):
            clues.append(
                {
                    "id": f"{colour}-dot-{_name(a)}-{_name(b)}",
                    "rule": rule,
                    "cells": [list(a), list(b)],
                    "values": [value],
                }
            )
    return clues


def rules_file(puzzle):
    """The rules file for a SudokuPad `puzzle` (`sudokupad_codec.read_puzzle`'s
    output), validated."""
    try:
        return _rules_file(puzzle)
    except (KeyError, TypeError, AttributeError) as e:
        raise ValueError(f"the puzzle is missing or has a bad {e}") from e


def _rules_file(puzzle):
    _refuse_unread(puzzle)
    cells = puzzle["cells"]
    n = len(cells)
    if any(len(row) != n for row in cells):
        raise ValueError(
            f"the grid is not square: {len(cells)} rows of {len(cells[0])}"
        )
    metadata = puzzle.get("metadata") or {}
    text = metadata.get("rules", "")
    rules = {
        "size": n,
        "regions": [[list(cell) for cell in region] for region in puzzle["regions"]],
        "givens": [
            {"cell": [r, c], "digit": int(cell["value"])}
            for r, row in enumerate(cells)
            for c, cell in enumerate(row)
            if cell.get("value") not in (None, "")
        ],
        "solution": _solution(metadata.get("solution"), n),
        "clues": _clues(puzzle, n, text) + _line_clues(puzzle, n, text),
        "title": metadata.get("title", ""),
        "rules_text": text,
    }
    validate(rules)
    return rules
