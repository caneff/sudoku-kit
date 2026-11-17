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

A sheet bigger than the grid (SudokuMaker's outside-clue puzzles draw the grid
inside a ring of clue cells) is read by its regions: the square they cover is
the grid, and its coordinates are the rules file's. Outside cells then sit one
step off the grid, and a rule reads one only where the stored solution holds a
digit there.

Sums and outside clues are read the same way, each only where the rules text
names it:

- Arrows ("arrow"): a rounded overlay with no text is a bulb, one cell or a
  pill of two or more (read as a number, first cell most significant), and an
  arrow starting inside it draws the shaft along cell centres.
- Killer cages ("killer", or "cage" with "sum"): a cage with a `value` and
  `unique` is a killer cage; the hidden `unique` cages that repeat a row or
  column are the houses already there.
- Little killers ("little killer"): a rounded overlay whose text is a number,
  on a cell beside the grid, and the diagonal arrow that starts in it. The
  diagonal runs from the cell next to the clue to the grid's edge.
- Skyscrapers ("skyscraper") and numbered rooms ("numbered room"): each
  outside cell the stored solution holds a digit for is a clue whose digit is
  the solver's to find, over the row or column it sits beside.
- Anti-knight ("knight" with "not", "no", "never" or "anti"): every pair of
  cells a knight's move apart.

Lines drawn on grid corners (the frame, the boxes round clue cells) are
decoration and are skipped. A line is read as the one line rule a sentence
names without a colour only when no sentence names a colour.

Any shape it does not read (a cage without a sum, an underlay that is not a
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
KNIGHT_MOVES = ((1, 2), (2, 1), (-1, 2), (-2, 1))
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
    """({colour: (rule, value)}, [(rule, value)]) for the line rules a sentence
    of `text` names: by colour where it names one, else the colourless list."""
    found, colourless = {}, []
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
        named = [c for c in ("orange", "pink", "grey", "gray") if c in sentence]
        for colour in named:
            found["grey" if colour == "gray" else colour] = (rule, value)
        if not named and (rule, value) not in colourless:
            colourless.append((rule, value))
    return found, colourless


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


def _decoration(line):
    """True for a line drawn over the grid along cell corners: the frame, the
    boxes round clue cells. No rule runs there, since a rule's line runs
    through cell centres."""
    return line.get("target") == "overlay" and all(
        abs(v - round(v)) < 1e-6 for point in line["wayPoints"] for v in point
    )


def _line_clues(puzzle, text):
    lines = [x for x in puzzle.get("lines") or [] if not _decoration(x)]
    underlays = puzzle.get("underlays") or []
    readings, colourless = _line_readings(text)
    bulbs, used, clues, seen = _bulb_ends(underlays), set(), [], set()
    for line in lines:
        colour = _hue_name(line.get("color", ""))
        if colour in readings:
            rule, value = readings[colour]
        elif len(colourless) == 1 and not readings:
            rule, value = colourless[0]
        else:
            why = (
                "the rules text names more than one line rule without a colour"
                if colourless
                else "the rules text gives no reading for it"
            )
            raise ValueError(
                "the importer does not read lines of colour "
                f"{colour or line.get('color')}: {why}: {_preview(line)}"
            )
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
        clues.append(
            {
                "prefix": rule,
                "rule": rule,
                "cells": cells,
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


def _says(text, *patterns):
    """True when one sentence of `text` matches every pattern."""
    return any(
        all(re.search(p, sentence) for p in patterns)
        for sentence in re.split(r"[.;\n]", text.lower())
    )


def _cell_of(point):
    return tuple(int((v + 1e-9) // 1) for v in point)


def _board(puzzle, size):
    """(top, left, n): the square the regions cover, in sheet coordinates."""
    cells = [tuple(c) for region in puzzle["regions"] for c in region]
    rows, columns = [c[0] for c in cells], [c[1] for c in cells]
    top, left = min(rows), min(columns)
    n = max(rows) - top + 1
    if max(columns) - left + 1 != n or len({*cells}) != n * n:
        raise ValueError(
            f"the regions do not cover a square: {n * n} cells wanted, "
            f"{len({*cells})} found"
        )
    if top + n > size or left + n > size:
        raise ValueError(f"the regions run off the {size}x{size} sheet")
    return top, left, n


def _solution(text, size, top, left, n):
    """(solution, {sheet cell: digit} beside the grid), or (None, {}). The
    sheet's digits cover the grid; a digit elsewhere is an outside cell's."""
    if text is None:
        return None, {}
    grid = [
        [text[(top + r) * size + left + c] for c in range(n)]
        if len(text) == size**2
        else []
        for r in range(n)
    ]
    if len(text) != size**2 or not all(d.isdigit() for row in grid for d in row):
        raise ValueError(f"the stored solution is not {size**2} digits: {text!r}")
    inside = {(top + r, left + c) for r in range(n) for c in range(n)}
    beside = {
        divmod(k, size): int(d)
        for k, d in enumerate(text)
        if d.isdigit() and divmod(k, size) not in inside
    }
    return [[int(d) for d in row] for row in grid], beside


def _dot_clues(puzzle, size, text):
    readings = _readings(text)
    diagonal = "diagonal" in text.lower()
    seen, clues = set(), []
    for overlay in puzzle.get("overlays") or []:
        colour = _colour(overlay)
        if colour is None:
            continue
        key = (colour, *(round(2 * v) for v in overlay["center"]))
        if key in seen:
            continue
        seen.add(key)
        if colour not in readings:
            raise ValueError(
                f"the rules text gives no reading for a {colour} dot: {_preview(text)}"
            )
        rule, value = readings[colour]
        for a, b in _pairs(overlay["center"], size, diagonal, overlay):
            clues.append(
                {
                    "prefix": f"{colour}-dot",
                    "rule": rule,
                    "cells": [a, b],
                    "values": [value],
                }
            )
    return clues


def _is_bulb(overlay):
    return (
        overlay.get("rounded")
        and not str(overlay.get("text", ""))
        and min(overlay["width"], overlay["height"]) > DOT_MAX_SIZE
    )


def _is_number(overlay):
    return str(overlay.get("text", "")).isdigit() and overlay.get("rounded")


def _bulb_cells(overlay):
    """The sheet cells under a bulb overlay: one, or a pill's run of them."""
    width, height = overlay["width"], overlay["height"]
    row, column = overlay["center"]
    length = round(max(width, height) - min(width, height)) + 1
    if length == 1:
        return [_cell_of((row, column))]
    turned = round(overlay.get("angle", 0)) % 180 == 90
    vertical = (width > height) == turned
    offsets = [k - (length - 1) / 2 for k in range(length)]
    points = [(row + o, column) if vertical else (row, column + o) for o in offsets]
    return [_cell_of(p) for p in points]


def _sign(value):
    return (value > 0) - (value < 0)


def _diagonal(start, arrow, board, overlay):
    """The cells a little killer's arrow points along from the clue cell
    `start`, to the grid's edge."""
    (r0, c0), (r1, c1) = arrow["wayPoints"][0], arrow["wayPoints"][-1]
    if not r1 - r0 or abs(abs(r1 - r0) - abs(c1 - c0)) > 0.1:
        raise ValueError(
            f"a little killer arrow that is not diagonal: {_preview(arrow)}"
        )
    dr, dc = _sign(r1 - r0), _sign(c1 - c0)
    top, left, n = board
    cells, (r, c) = [], (start[0] + dr, start[1] + dc)
    while top <= r < top + n and left <= c < left + n:
        cells.append((r, c))
        r, c = r + dr, c + dc
    if not cells:
        raise ValueError(
            f"a little killer arrow pointing off the grid: {_preview(arrow)}"
        )
    return cells


def _arrow_clues(puzzle, text, board):
    """(clues, the overlays they read): arrows from a bulb, little killers from
    a number, each only where the rules text names it."""
    overlays = puzzle.get("overlays") or []
    bulbs, numbers = {}, {}
    for i, overlay in enumerate(overlays):
        if _is_bulb(overlay):
            bulbs.update(dict.fromkeys(_bulb_cells(overlay), i))
        elif _is_number(overlay) and _colour(overlay) is None:
            numbers[_cell_of(overlay["center"])] = i
    clues, used = [], set()
    for arrow in puzzle.get("arrows") or []:
        start = _cell_of(arrow["wayPoints"][0])
        if start in bulbs:
            if not _says(text, "arrow"):
                raise ValueError(
                    "the importer does not read arrows: the rules text never "
                    f"says arrow: {_preview(arrow)}"
                )
            used.add(bulbs[start])
            bulb = sorted(_bulb_cells(overlays[bulbs[start]]))
            centre = (start[0] + 0.5, start[1] + 0.5)
            shaft = _path({"wayPoints": [centre, *arrow["wayPoints"][1:]]})[1:]
            if not shaft or {*shaft} & {*bulb}:
                raise ValueError(
                    f"an arrow with no shaft past its bulb: {_preview(arrow)}"
                )
            clues.append(
                {
                    "prefix": "arrow",
                    "rule": "arrow",
                    "cells": [*bulb, *shaft],
                    "values": [len(bulb)],
                }
            )
        elif start in numbers:
            if not _says(text, "little killer"):
                raise ValueError(
                    "the importer does not read arrows: the rules text never "
                    f"says little killer: {_preview(arrow)}"
                )
            overlay = overlays[numbers[start]]
            used.add(numbers[start])
            clues.append(
                {
                    "prefix": "little-killer",
                    "rule": "little_killer",
                    "cells": _diagonal(start, arrow, board, overlay),
                    "values": [int(overlay["text"])],
                }
            )
        else:
            raise ValueError(
                "the importer does not read arrows that start outside a bulb "
                f"or a clue number: {_preview(arrow)}"
            )
    return clues, used


def _refuse_overlays(puzzle, used):
    for i, overlay in enumerate(puzzle.get("overlays") or []):
        if i not in used and _colour(overlay) is None:
            raise ValueError(
                "the importer does not read overlays other than black and white "
                f"dots, arrow bulbs and little killer numbers: {_preview(overlay)}"
            )


def _cage_clues(puzzle, text, board):
    top, left, n = board
    houses = {
        frozenset(
            (top + a, left + b) if flip else (top + b, left + a) for b in range(n)
        )
        for a in range(n)
        for flip in (False, True)
    }
    killer = _says(text, "killer") or _says(text, "cage", "sum")
    clues = []
    for cage in puzzle.get("cages") or []:
        if not cage.get("cells"):
            continue
        cells = [tuple(c) for c in cage["cells"]]
        value = str(cage.get("value", ""))
        if cage.get("hidden") and "value" not in cage and {*cells} in houses:
            continue  # a row or column, already a house
        if not (
            killer and cage.get("unique") and not cage.get("hidden") and value.isdigit()
        ):
            raise ValueError(f"the importer does not read cages: {_preview(cage)}")
        clues.append(
            {
                "prefix": "killer-cage",
                "rule": "killer_cage",
                "cells": sorted(cells),
                "values": [int(value)],
            }
        )
    return clues


def _knight_clues(text, board):
    sentences = [x for x in re.split(r"[.;\n]", text.lower()) if "knight" in x]
    if not sentences:
        return []
    if not any(re.search(r"\b(not|no|never|anti)\b|anti-|n't", x) for x in sentences):
        raise ValueError(
            f"a knight sentence that does not forbid a repeat: {_preview(sentences[0])}"
        )
    top, left, n = board
    return [
        {
            "prefix": "anti-knight",
            "rule": "anti_knight",
            "cells": [(top + r, left + c), (top + r + dr, left + c + dc)],
            "values": [],
        }
        for r, c in itertools.product(range(n), repeat=2)
        for dr, dc in KNIGHT_MOVES
        if 0 <= r + dr < n and 0 <= c + dc < n
    ]


def _outside_clues(beside, text, board):
    """A skyscraper or numbered-room clue for each outside cell with a stored
    digit, over the row or column it sits beside."""
    top, left, n = board
    rules = [
        rule
        for rule, word in (
            ("skyscraper", "skyscraper"),
            ("numbered_rooms", "numbered room"),
        )
        if _says(text, word)
    ]
    if len(rules) != 1:
        return []
    clues = []
    for (r, c), _ in sorted(beside.items()):
        if r in (top - 1, top + n) and left <= c < left + n:
            rows = range(top, top + n) if r < top else range(top + n - 1, top - 1, -1)
            line = [(i, c) for i in rows]
        elif c in (left - 1, left + n) and top <= r < top + n:
            columns = (
                range(left, left + n) if c < left else range(left + n - 1, left - 1, -1)
            )
            line = [(r, j) for j in columns]
        else:
            raise ValueError(
                f"a stored solution digit at {(r, c)}, which no row or column "
                "of the grid starts or ends at"
            )
        clues.append(
            {
                "prefix": rules[0].replace("_", "-"),
                "rule": rules[0],
                "cells": [(r, c), *line],
                "values": [],
            }
        )
    return clues


def _finish(raw, top, left):
    """The clues with cells in the grid's coordinates and unique ids."""
    clues, ids = [], set()
    for clue in raw:
        cells = [[r - top, c - left] for r, c in clue["cells"]]
        base = f"{clue['prefix']}-{_name(cells[0])}-{_name(cells[-1])}"
        clue_id = base
        while clue_id in ids:
            clue_id += "-b"
        ids.add(clue_id)
        clues.append(
            {
                "id": clue_id,
                "rule": clue["rule"],
                "cells": cells,
                "values": clue["values"],
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
    cells = puzzle["cells"]
    size = len(cells)
    if any(len(row) != size for row in cells):
        raise ValueError(
            f"the grid is not square: {len(cells)} rows of {len(cells[0])}"
        )
    board = _board(puzzle, size)
    top, left, n = board
    metadata = puzzle.get("metadata") or {}
    text = metadata.get("rules", "")
    solution, beside = _solution(metadata.get("solution"), size, top, left, n)
    arrows, used = _arrow_clues(puzzle, text, board)
    _refuse_overlays(puzzle, used)
    raw = (
        _dot_clues(puzzle, size, text)
        + _line_clues(puzzle, text)
        + arrows
        + _cage_clues(puzzle, text, board)
        + _knight_clues(text, board)
        + _outside_clues(beside, text, board)
    )
    clues = _finish(raw, top, left)
    outside = {tuple(cell) for clue in clues for cell in clue["cells"]} - {
        (r, c) for r in range(n) for c in range(n)
    }
    stored = {(r - top, c - left): d for (r, c), d in beside.items()}
    unread = sorted(set(stored) - outside)
    if unread:
        raise ValueError(
            f"the stored solution has digits beside the grid at {unread} that "
            "no rule reads"
        )
    rules = {
        "size": n,
        "regions": [
            [[r - top, c - left] for r, c in region] for region in puzzle["regions"]
        ],
        "givens": [
            {"cell": [r - top, c - left], "digit": int(cell["value"])}
            for r, row in enumerate(cells)
            for c, cell in enumerate(row)
            if cell.get("value") not in (None, "")
        ],
        "solution": solution,
        "clues": clues,
        "title": metadata.get("title", ""),
        "rules_text": text,
    }
    if solution is not None and outside:
        rules["solution_outside"] = [
            {"cell": list(cell), "digit": stored[cell]}
            for cell in sorted(outside)
            if cell in stored
        ]
    validate(rules)
    return rules
