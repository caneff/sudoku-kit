"""SudokuPad puzzle JSON to a rules file: normal sudoku plus Kropki dots,
coloured lines (thermo, renban, whispers, lockout), arrows, killer cages, little
killers, skyscrapers, numbered rooms, anti-knight, tessellation and consecutive
sets.

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
between.

A lockout line ("lockout") is a line drawn through diamond overlays, a diamond
at each end. Its smallest end gap is the "at least <number>" of the sentence
that names the "endpoints". A diamond mid-line ends one lockout line and starts
the next, so a stroke through a middle diamond is two lines. Lines SudokuPad
stores as an SVG path (`d`, in 64-pixel cells, `M` and `L` only) are read like
waypoints when every point is a cell centre; any other path is tile art. A
white stroke drawn under a line is the same path again, and is read once.

A puzzle with no regions is a board of no boxes: the sheet is the grid. Where
its stored solution has no digit in a cell the cell is a hole, not part of the
puzzle (a diamond board on a square sheet); `holes` in the rules file lists them.

A sheet bigger than the grid (SudokuMaker's outside-clue puzzles draw the grid
inside a ring of outside cells) is read by its regions: the square they cover is
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
- Tessellation ("sharing an edge" with a refusal to repeat): the puzzle is a
  tiling of octagons and squares, one tile a cell. Every two cells side by side
  share an edge, and so do two octagons corner to corner. The squares are the
  cells with a small square's four corners among the thin lines' points, all of
  one parity of row plus column; a tessellation with none is refused.
- Consecutive sets ("consecutive set" with "row" or "column"): each row, column
  or both, over its cells but the holes, holds a consecutive set of digits.

Lines drawn on grid corners (the frame, the boxes round outside cells) are
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

from sudoku_kit.rules_file import cell_name, validate

PREVIEW_CHARACTERS = 80
SENTENCE_BREAK = re.compile(r"[.;\n]")
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
    ("lockout", re.compile(r"lockout")),
)
CELL_PIXELS = 64  # SudokuPad's cell size, the unit of a line's SVG path
PATH_POINT = re.compile(r"([ML])\s*(-?[\d.]+)[\s,]+(-?[\d.]+)")
PATH_COMMAND = re.compile(r"[A-Za-z]")
TILE_HALF_SIDES = range(10, 29)  # pixels: a tessellation's small square


def _preview(item):
    return repr(item)[:PREVIEW_CHARACTERS]


def _sentences(text):
    return SENTENCE_BREAK.split(text.lower())


def _cell_of(point):
    """The sheet cell a point on the sheet falls in."""
    return tuple(int((v + 1e-9) // 1) for v in point)


def _is_path(line):
    """True for a line SudokuPad stores as an SVG path, not as waypoints."""
    return "wayPoints" not in line and "d" in line


def _d_points(line):
    """A line's SVG path as (row, column) points in cell units. Anything but
    `M` and `L` commands, each with one x y pair, is refused: such a path is
    unread, and a rule's line must never be dropped silently as tile art."""
    path = line["d"]
    points = [
        (float(y) / CELL_PIXELS, float(x) / CELL_PIXELS)
        for _, x, y in PATH_POINT.findall(path)
    ]
    if not points or PATH_POINT.sub("", path).strip():
        raise ValueError(
            f"a line path the importer does not read (only M and L, one x y "
            f"pair each): {_preview(line)}"
        )
    return points


def _way_points(item):
    """The waypoints of a line or arrow, refusing one with none."""
    points = _d_points(item) if _is_path(item) else item["wayPoints"]
    if not points:
        raise ValueError(f"a line or arrow with no waypoints: {_preview(item)}")
    return points


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
    sentences = _sentences(text)
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
    for sentence in _sentences(text):
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
        if rule == "lockout":
            value = _lockout_gap(text)
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
    for point in _way_points(line):
        cell = _cell_of(point)
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


def _at_centre(point):
    return all(abs(v - 0.5 - round(v - 0.5)) < 1e-6 for v in point)


def _is_diamond(overlay):
    """A square turned a quarter on a cell centre: a lockout line's end."""
    return (
        not overlay.get("rounded")
        and not str(overlay.get("text", ""))
        and overlay.get("width") == overlay.get("height")
        and round(overlay.get("angle", 0)) % 90 == 45
        and _at_centre(overlay["center"])
    )


def _lockout_gap(text):
    """The smallest gap between a lockout line's ends: the "at least <number>"
    of the sentence that names the endpoints."""
    for sentence in _sentences(text):
        gap = re.search(r"at least (\d+)", sentence) if "endpoint" in sentence else None
        if gap:
            return int(gap.group(1))
    raise ValueError(
        "a lockout sentence, and no sentence naming the endpoints with "
        f"'at least <number>': {_preview(text)}"
    )


def _lockout_lines(cells, diamonds, line):
    """The lockout lines a stroke is: its cells cut at every diamond, which
    must be at both ends."""
    ends = [i for i, cell in enumerate(cells) if cell in diamonds]
    if len(ends) < 2 or ends[0] != 0 or ends[-1] != len(cells) - 1:
        raise ValueError(
            f"a lockout line that does not start and end on a diamond: {_preview(line)}"
        )
    return [cells[a : b + 1] for a, b in itertools.pairwise(ends)]


def _bulb_ends(underlays):
    """The cells that carry a round underlay, the bulbs a thermo may start at."""
    return {
        _cell_of(u["center"])
        for u in underlays
        if u.get("rounded")
        and all(abs(v - 0.5 - round(v - 0.5)) < 1e-6 for v in u["center"])
    }


def _decoration(line):
    """True for a line drawn over the grid along cell corners: the frame, the
    boxes round outside cells, a tessellation's tile outlines. No rule runs
    there, since a rule's line runs through cell centres."""
    if _is_path(line):
        # Tile art touches no cell centre; a path that touches some and not all
        # is a rule's line gone wrong, left for `_path` to refuse.
        return not any(_at_centre(p) for p in _d_points(line))
    return line.get("target") == "overlay" and all(
        abs(v - round(v)) < 1e-6 for point in _way_points(line) for v in point
    )


def _line_clues(puzzle, text):
    """(clues, the diamond overlays they read)."""
    lines = [x for x in puzzle.get("lines") or [] if not _decoration(x)]
    underlays = puzzle.get("underlays") or []
    diamonds = {
        _cell_of(o["center"]): i
        for i, o in enumerate(puzzle.get("overlays") or [])
        if _is_diamond(o)
    }
    readings, colourless = _line_readings(text)
    bulbs, used, clues, seen = _bulb_ends(underlays), set(), [], set()
    used_diamonds = set()
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
        pieces = [cells]
        if rule == "lockout":
            pieces = _lockout_lines(cells, diamonds, line)
            used_diamonds |= {diamonds[c] for c in cells if c in diamonds}
        for cells in pieces:
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
        centre = _cell_of(underlay["center"])
        if centre not in used or not underlay.get("rounded"):
            raise ValueError(
                "the importer does not read underlays other than a thermo's "
                f"bulb: {_preview(underlay)}"
            )
    return clues, used_diamonds


def _says(text, *patterns):
    """True when one sentence of `text` matches every pattern."""
    return any(
        all(re.search(p, sentence) for p in patterns) for sentence in _sentences(text)
    )


def _board(puzzle, size):
    """(top, left, n): the square the regions cover, in sheet coordinates; the
    whole sheet when there are none."""
    if not puzzle["regions"]:
        return 0, 0, size
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


def _solution(text, size, board, holes_ok):
    """(solution, {sheet cell: digit} beside the grid, holes), or (None, {}, set()).
    The sheet's digits cover the grid; a digit elsewhere is an outside cell's. A
    grid cell holding "." is a hole where `holes_ok` (a board of no regions),
    its solution entry None; any other non-digit, or a "." beside regions, is
    refused."""
    top, left, n = board
    if text is None:
        return None, {}, set()
    if len(text) != size**2:
        raise ValueError(f"the stored solution is not {size**2} characters: {text!r}")
    grid = [[text[(top + r) * size + left + c] for c in range(n)] for r in range(n)]
    odd = [d for row in grid for d in row if not d.isdigit() and d != "."]
    if odd or (not holes_ok and any("." in row for row in grid)):
        raise ValueError(
            "the stored solution has a grid cell with no digit"
            + ("" if odd else " beside regions, which mark every cell")
            + f": {text!r}"
        )
    holes = {
        (top + r, left + c)
        for r, row in enumerate(grid)
        for c, d in enumerate(row)
        if d == "."
    }
    if len(holes) == n * n:
        raise ValueError(f"the stored solution has no digit in the grid: {text!r}")
    inside = {(top + r, left + c) for r in range(n) for c in range(n)}
    beside = {
        divmod(k, size): int(d)
        for k, d in enumerate(text)
        if d.isdigit() and divmod(k, size) not in inside
    }
    rows = [[int(d) if d.isdigit() else None for d in row] for row in grid]
    return rows, beside, holes


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


def _diagonal(start, arrow, board):
    """The cells a little killer's arrow points along from the outside cell
    `start`, to the grid's edge."""
    points = _way_points(arrow)
    (r0, c0), (r1, c1) = points[0], points[-1]
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
        start = _cell_of(_way_points(arrow)[0])
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
                    "cells": _diagonal(start, arrow, board),
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
                "dots, arrow bulbs, little killer numbers and the diamonds on a "
                f"lockout line: {_preview(overlay)}"
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


def _knight_clues(text, board, holes):
    sentences = [x for x in _sentences(text) if "knight" in x]
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
        if 0 <= r + dr < n
        and 0 <= c + dc < n
        and {(top + r, left + c), (top + r + dr, left + c + dc)}.isdisjoint(holes)
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


def _square_tiles(puzzle, playable):
    """The cells of `playable` drawn as a tessellation's small square: the four
    corners of a square centred on the cell are all points of the thin lines
    that SudokuPad stores as paths."""
    points = {
        (round(r * CELL_PIXELS), round(c * CELL_PIXELS))
        for line in puzzle.get("lines") or []
        if _is_path(line)
        for r, c in _d_points(line)
    }
    return {
        (r, c)
        for r, c in playable
        for half in TILE_HALF_SIDES
        if all(
            (
                round((r + 0.5) * CELL_PIXELS) + dr * half,
                round((c + 0.5) * CELL_PIXELS) + dc * half,
            )
            in points
            for dr, dc in itertools.product((-1, 1), repeat=2)
        )
    }


def _tessellation_clues(puzzle, text, playable):
    """One clue for each pair of `playable` cells that share an edge, where a
    sentence says that cells sharing an edge may not repeat: side by side,
    and corner to corner for two octagons (the cells that are not squares)."""
    sentences = [x for x in _sentences(text) if re.search(r"shar(e|ing) an edge", x)]
    if not sentences or not _says(text, "tessellation"):
        return []
    if not any(re.search(r"\b(not|never)\b|n't|differ", x) for x in sentences):
        raise ValueError(
            f"an edge sentence that does not forbid a repeat: {_preview(sentences[0])}"
        )
    parities = {(r + c) % 2 for r, c in _square_tiles(puzzle, playable)}
    if len(parities) != 1:
        raise ValueError(
            "a tessellation, and "
            + (
                "no tile outline in the puzzle's lines draws a small square"
                if not parities
                else "small squares on cells of both parities"
            )
            + f", so squares cannot be told from octagons: {_preview(sentences[0])}"
        )
    (square,) = parities
    pairs = []
    for r, c in sorted(playable):
        moves = [(0, 1), (1, 0)]
        if (r + c) % 2 != square:
            moves += [(1, 1), (1, -1)]
        pairs += [
            ((r, c), (r + dr, c + dc))
            for dr, dc in moves
            if (r + dr, c + dc) in playable
        ]
    return [
        {
            "prefix": "tessellation",
            "rule": "tessellation",
            "cells": list(p),
            "values": [],
        }
        for p in pairs
    ]


def _consecutive_clues(text, playable, board):
    """A consecutive-set clue for each row, each column or both, as the
    sentence names them, over the `playable` cells of every line with two. A
    consecutive-set sentence about a line rule's path is that rule's."""
    top, left, n = board
    lines = {
        "row": [[(r, c) for c in range(left, left + n)] for r in range(top, top + n)],
        "column": [
            [(r, c) for r in range(top, top + n)] for c in range(left, left + n)
        ],
    }
    clues = []
    for sentence in (x for x in _sentences(text) if "consecutive set" in x):
        named = [kind for kind in lines if re.search(rf"\b{kind}s?\b", sentence)]
        if not named and any(pattern.search(sentence) for _, pattern in LINE_RULES):
            continue
        if not named:
            raise ValueError(
                f"a consecutive set sentence naming no row or column: {_preview(sentence)}"
            )
        for kind in named:
            for line in lines[kind]:
                cells = [cell for cell in line if cell in playable]
                if len(cells) > 1:
                    clues.append(
                        {
                            "prefix": "consecutive-set",
                            "rule": "consecutive_set",
                            "cells": cells,
                            "values": [],
                        }
                    )
    return clues


def _finish(raw, top, left):
    """The clues with cells in the grid's coordinates and unique ids."""
    clues, ids = [], set()
    for clue in raw:
        cells = [[r - top, c - left] for r, c in clue["cells"]]
        base = f"{clue['prefix']}-{cell_name(cells[0])}-{cell_name(cells[-1])}"
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
    if not puzzle["regions"] and metadata.get("solution") is None:
        raise ValueError(
            "the puzzle has no regions and no stored solution, so which cells "
            "of the sheet are part of the board cannot be told"
        )
    solution, beside, holes = _solution(
        metadata.get("solution"), size, board, not puzzle["regions"]
    )
    playable = {
        (r, c)
        for r in range(top, top + n)
        for c in range(left, left + n)
        if (r, c) not in holes
    }
    arrows, used = _arrow_clues(puzzle, text, board)
    lines, diamonds = _line_clues(puzzle, text)
    _refuse_overlays(puzzle, used | diamonds)
    raw = (
        _dot_clues(puzzle, size, text)
        + lines
        + arrows
        + _cage_clues(puzzle, text, board)
        + _knight_clues(text, board, holes)
        + _tessellation_clues(puzzle, text, playable)
        + _consecutive_clues(text, playable, board)
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
    if holes:
        rules["holes"] = [[r - top, c - left] for r, c in sorted(holes)]
    if solution is not None and outside:
        rules["solution_outside"] = [
            {"cell": list(cell), "digit": stored[cell]}
            for cell in sorted(outside)
            if cell in stored
        ]
    validate(rules)
    return rules
