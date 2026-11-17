"""SudokuPad puzzle JSON to a rules file, for normal sudoku plus Kropki dots.

`rules_file(puzzle)` reads the grid, regions, givens and stored solution, and
turns each dot overlay into clues. The puzzle's rules text picks the reading:
a sentence naming white dots and "consecutive" reads white as difference 1; a
sentence naming black dots and "2:1", "ratio" or "double" reads black as
ratio 2. A dot on an edge joins the two cells either side of it. A dot on a
grid corner joins both diagonal pairs around it, and is read only when the
rules text says "diagonal".

Any shape it does not read (a line, an arrow, a cage, an underlay, any other
overlay) is refused by name, so a rule is never dropped silently; a rules
file for such a puzzle is written by hand. Every refusal is a ValueError.
"""

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
UNREAD_KINDS = ("lines", "arrows", "underlays")


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
        "clues": _clues(puzzle, n, text),
        "title": metadata.get("title", ""),
        "rules_text": text,
    }
    validate(rules)
    return rules
