"""The solve guide's HTML: `guide_page(rules, record, guide)` and the command
line that writes it.

Key ideas, fill and every refusal of a guide file are pinned on `TOY`, a
made-up 4x4 board, with records and guide files written by hand, so no test
pins a step of a published puzzle. Diagonal Dots (Logic Masters 000HUJ,
`tests/solve_guide/`) is read only where no guide file is needed: the plain
render, and a stuck point drawn on a guide whose one fill entry is built here
from the session's record (`diagonal_dots_run` in `conftest.py`; neither is
ever committed). The page is read back as parsed markup, and the expected
highlights are rebuilt here from the rules file and the record, not from the
renderer.
"""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest
from link_helpers import DIAMOND

from sudoku_kit import clue_rules, guide_html, rules_file, step_search, sudokupad_import
from sudoku_kit.solve_guide import main

FIXTURES = Path(__file__).parent / "solve_guide"
PUZZLE = FIXTURES / "diagonal-dots-000HUJ.json"
SKYSCRAPER = FIXTURES / "skyscraper-nextdoor-000N2S.json"


class Page(HTMLParser):
    """The guide's elements, in order: (tag, attributes, text, svg index)."""

    def __init__(self, html):
        super().__init__()
        self.elements = []
        self._svg = -1
        self._open = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        if tag == "svg":
            self._svg += 1
        element = [tag, dict(attrs), "", self._svg]
        self.elements.append(element)
        self._open.append(element)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        self._open.pop()

    def handle_endtag(self, tag):
        while self._open:
            if self._open.pop()[0] == tag:
                return

    def handle_data(self, data):
        if self._open:
            self._open[-1][2] += data

    def find(self, tag, cls=None):
        return [
            e
            for e in self.elements
            if e[0] == tag and (cls is None or cls in e[1].get("class", "").split())
        ]

    def grids(self):
        """{key idea number: svg index} for each key idea's grid."""
        return {
            int(e[1]["data-key"]): e[3]
            for e in self.find("svg", "grid")
            if e[1].get("data-key")
        }

    def cells(self, svg, cls):
        return {
            e[1]["data-cell"]
            for e in self.find("rect", "cell")
            if e[3] == svg and cls in e[1]["class"].split()
        }


def _name(cell):
    return f"r{cell[0] + 1}c{cell[1] + 1}"


TOY = {
    "size": 4,
    "regions": [
        [[0, 0], [0, 1], [1, 0], [1, 1]],
        [[0, 2], [0, 3], [1, 2], [1, 3]],
        [[2, 0], [2, 1], [3, 0], [3, 1]],
        [[2, 2], [2, 3], [3, 2], [3, 3]],
    ],
    "givens": [],
    "clues": [
        {
            "id": "white-a",
            "rule": "difference",
            "cells": [[0, 0], [0, 1]],
            "values": [1],
        },
        {
            "id": "white-b",
            "rule": "difference",
            "cells": [[2, 2], [2, 3]],
            "values": [1],
        },
        {"id": "black-a", "rule": "ratio", "cells": [[3, 0], [3, 1]], "values": [2]},
    ],
}


def _step(named, cell, digits):
    """A made-up step on the 4x4 `TOY`: the cell keeps `digits`."""
    return {
        "claim": {"cell": list(cell), "digits": digits},
        "named": named,
        "hard": len(named) > 3,
        "by": "search",
    }


def _record(*steps):
    return {"steps": list(steps), "timeouts": [], "stuck": None}


def _key(first, last, heading="An idea", paragraphs=("Why it holds.",), **extra):
    return {
        "type": "key",
        "first": first,
        "last": last,
        "heading": heading,
        "paragraphs": list(paragraphs),
        **extra,
    }


def _fill(first, last, sentence="The grid fills on."):
    return {"type": "fill", "first": first, "last": last, "sentence": sentence}


def _guide(*entries):
    return {"version": 1, "entries": list(entries)}


def _toy(steps, *entries, rules=TOY, image=None):
    return Page(guide_html.guide_page(rules, _record(*steps), _guide(*entries), image))


SIX = [
    _step(["row 1"], (0, 2), [1, 2, 3]),
    _step(["white-a"], (0, 0), [1, 2, 3]),
    _step(["row 2", "column 3"], (1, 2), [1, 2]),
    _step(["black-a"], (3, 0), [1, 2, 4]),
    _step(["white-b"], (2, 2), [1, 2, 3]),
    _step(["white-b", "row 3", "column 3", "region 4"], (2, 3), [2, 3]),
]


def _keys(page):
    """[(key number, its step numbers)] for each key idea, in page order."""
    return [
        (int(e[1]["data-key"]), e[1]["data-steps"]) for e in page.find("section", "key")
    ]


def _grouped(*steps):
    """The step numbers of each deduction, in guide order."""
    return [g["steps"] for g in guide_html.deductions(TOY, _record(*steps))]


def test_steps_on_the_same_constraints_merge_across_a_step_elsewhere():
    grouped = _grouped(
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["row 4"], (3, 3), [1, 2, 3]),
        _step(["white-a"], (0, 1), [1, 2, 3]),
    )

    assert grouped == [[2], [1, 3]]


def test_a_step_changing_a_cell_the_group_uses_keeps_them_apart():
    grouped = _grouped(
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["row 1"], (0, 1), [1, 2, 3]),
        _step(["white-a"], (0, 0), [1, 2]),
    )

    assert grouped == [[1], [2], [3]]


def test_key_ideas_are_numbered_1_to_n_in_file_order_with_their_words():
    page = _toy(
        SIX,
        _fill(1, 1),
        _key(2, 3, "The dot and the pair", ["First this.", "Then that."]),
        _fill(4, 4),
        _key(5, 6, "Round the cage"),
    )

    assert _keys(page) == [(1, "2 3"), (2, "5 6")]
    assert [e[2] for e in page.find("h2")] == [
        "Key idea 1: The dot and the pair",
        "Key idea 2: Round the cage",
    ]
    first = page.find("section", "key")[0]
    at = page.elements.index
    inside = page.elements[at(first) : at(page.find("section", "key")[1])]
    paragraphs = [e[2] for e in inside if e[0] == "p" and not e[1].get("class")]
    assert paragraphs == ["First this.", "Then that."]


def test_each_key_idea_is_one_row_with_its_grid_left_of_its_text():
    page = _toy(SIX[:3], _key(1, 1), _key(2, 2), _key(3, 3))

    sections = page.find("section", "key")
    at = page.elements.index
    assert len(sections) == 3
    for k, section in enumerate(sections):
        end = at(sections[k + 1]) if k + 1 < len(sections) else len(page.elements)
        inside = page.elements[at(section) : end]
        tags = [e[0] for e in inside if e[0] in ("svg", "div", "h2")]
        assert tags[:3] == ["svg", "div", "h2"]
        assert "text" in inside[[e[0] for e in inside].index("div")][1]["class"]
        assert len([e for e in inside if e[0] == "svg"]) == 1


def test_the_break_in_label_shows_on_the_flagged_idea_only():
    page = _toy(SIX, _key(1, 2), _key(3, 4, break_in=True), _key(5, 6))

    breakin = page.find("p", "breakin")
    sections = page.find("section", "key")
    at = page.elements.index
    assert len(breakin) == 1
    assert at(sections[1]) < at(breakin[0]) < at(sections[2])


def test_a_guide_with_no_flag_has_no_break_in_label():
    page = _toy(SIX, _key(1, 6))

    assert not page.find("p", "breakin")


def test_each_fill_stretch_is_its_sentence_and_a_collapsed_line_per_step():
    page = _toy(
        SIX,
        _fill(1, 3, "Singles in the top rows."),
        _key(4, 4),
        _fill(5, 6, "The cage finishes the corner."),
    )

    fills = page.find("div", "fill")
    assert [e[2] for e in page.find("p", "fill")] == [
        "Singles in the top rows.",
        "The cage finishes the corner.",
    ]
    assert len(fills) == len(page.find("details")) == 2
    assert [e[1]["data-step"] for e in page.find("li", "step")] == [
        "1",
        "2",
        "3",
        "5",
        "6",
    ]
    assert [e[2] for e in page.find("li", "step")] == [
        "r1c3 keeps 1 2 3, from row 1.",
        "r1c1 keeps 1 2 3, from white dot r1c1-r1c2.",
        "r2c3 keeps 1 2, from row 2 and column 3.",
        "r3c3 keeps 1 2 3, from white dot r3c3-r3c4.",
        "r3c4 keeps 2 3, from white dot r3c3-r3c4, row 3, column 3 and region 4.",
    ]


def test_a_placement_reads_as_the_digit_it_places():
    page = _toy([_step(["black-a"], (3, 0), [4])], _fill(1, 1))

    assert [e[2] for e in page.find("li", "step")] == [
        "r4c1 = 4, from black dot r4c1-r4c2."
    ]


PAIRS = {"difference", "ratio", "anti_knight", "tessellation"}


@pytest.mark.parametrize("rule", sorted(clue_rules.RULES))
def test_every_rule_types_constraint_is_named_by_its_cells_and_never_its_id(rule):
    cells = [[0, 0], [0, 1]] if rule in PAIRS else [[0, 0], [0, 1], [0, 2]]
    rules = dict(
        TOY,
        clues=[{"id": "zz-secret-id", "rule": rule, "cells": cells, "values": [1]}],
    )

    words = guide_html.constraint_words(rules, "zz-secret-id")

    assert rules_file.cell_name(cells[0]) in words
    assert "zz-secret-id" not in words


def test_a_key_ideas_grid_strikes_out_what_all_its_steps_remove():
    page = _toy(
        [
            _step(["white-a"], (0, 0), [1, 2, 3]),
            _step(["white-a"], (0, 1), [1, 2, 3]),
            _step(["white-a"], (0, 0), [2, 3]),
        ],
        _key(1, 3),
    )

    struck = {
        (e[1]["data-cell"], int(e[1]["data-digit"]))
        for e in page.find("text", "struck")
    }
    assert struck == {("r1c1", 1), ("r1c1", 4), ("r1c2", 4)}
    assert page.cells(page.grids()[1], "changed") == {"r1c1", "r1c2"}
    assert page.cells(page.grids()[1], "used") == {"r1c1", "r1c2"}


def test_a_key_ideas_grid_starts_from_the_candidates_before_its_first_step():
    page = _toy(
        [
            _step(["row 1"], (0, 0), [1, 2, 3]),
            _step(["white-a"], (0, 0), [2, 3]),
        ],
        _fill(1, 1),
        _key(2, 2),
    )

    grid = page.grids()[1]
    drawn = {
        (e[1]["data-cell"], int(e[1]["data-digit"]))
        for e in page.find("text", "cand")
        if e[3] == grid and e[1]["data-cell"] == "r1c1"
    }
    struck = {
        (e[1]["data-cell"], int(e[1]["data-digit"]))
        for e in page.find("text", "struck")
        if e[3] == grid
    }
    assert drawn == {("r1c1", 1), ("r1c1", 2), ("r1c1", 3)}
    assert struck == {("r1c1", 1)}


def test_a_key_idea_draws_candidates_only_in_the_cells_it_uses_or_changes():
    page = _toy(
        [
            _step(["row 1"], (0, 3), [4]),
            _step(["row 1"], (0, 1), [1, 2, 3]),
            _step(["row 2"], (1, 3), [1, 2, 3]),
            _step(["white-a"], (0, 0), [1, 2, 3]),
        ],
        _fill(1, 3),
        _key(4, 4),
    )

    grid = page.grids()[1]
    drawn = {e[1]["data-cell"] for e in page.find("text", "cand") if e[3] == grid}
    assert drawn == {"r1c1", "r1c2"}
    assert [e[2] for e in page.find("text", "solved") if e[3] == grid] == ["4"]


@pytest.mark.parametrize(
    ("entries", "cause"),
    [
        ([_fill(1, 2), _key(4, 6)], r"skips step 3"),
        ([_key(1, 3), _fill(3, 6)], r"repeats step 3"),
        ([_fill(1, 2), _fill(5, 6), _key(3, 4)], r"out of order.*steps 3-4"),
        ([_key(1, 5)], r"skips step 6"),
        ([_key(1, 7)], r"step 7.*6 steps"),
        (
            [_key(1, 2, break_in=True), _key(3, 6, break_in=True)],
            r"entries 1 and 2.*break-in",
        ),
        ([_key(3, 2), _fill(1, 6)], r"entry 1.*first 3.*after.*last 2"),
    ],
    ids=["skip", "repeat", "reorder", "short", "past-end", "two-break-ins", "backward"],
)
def test_a_guide_file_that_does_not_fit_the_record_is_refused_naming_why(
    entries, cause
):
    with pytest.raises(ValueError, match=cause):
        guide_html.guide_page(TOY, _record(*SIX), _guide(*entries))


@pytest.mark.parametrize(
    ("guide", "cause"),
    [
        ([], r"not a JSON object"),
        ({"entries": []}, r"version.*1"),
        ({"version": 2, "entries": []}, r"version 2.*1"),
        ({"version": 1}, r"entries"),
        (_guide({"type": "note", "first": 1, "last": 6}), r"entry 1.*type 'note'"),
        (_guide(_fill(1, 6) | {"heading": "x"}), r"entry 1.*heading"),
        (_guide(_key(1, 6) | {"paragraphs": "one"}), r"entry 1.*paragraphs"),
        (_guide({"type": "fill", "first": 1, "last": 6}), r"entry 1.*sentence"),
        (_guide(_fill("1", 6)), r"entry 1.*first"),
    ],
    ids=[
        "not-object",
        "no-version",
        "wrong-version",
        "no-entries",
        "bad-type",
        "unknown-field",
        "bad-paragraphs",
        "missing-sentence",
        "bad-first",
    ],
)
def test_a_malformed_guide_file_is_refused_naming_the_field(guide, cause):
    with pytest.raises(ValueError, match=cause):
        guide_html.guide_page(TOY, _record(*SIX), guide)


def test_the_page_opens_with_the_title_the_rules_text_and_the_starting_grid():
    rules = dict(
        TOY,
        title="Toy dots",
        rules_text="Normal sudoku rules apply.\nWhite dots join consecutive digits.",
        givens=[{"cell": [3, 3], "digit": 2}],
    )
    page = _toy(
        [_step(["white-a"], (0, 0), [1, 2, 3])],
        _key(1, 1),
        rules=rules,
        image="original.png",
    )

    heading, text, start = page.find("h1"), page.find("p", "rules"), page.find("svg")
    assert [e[2] for e in heading] == ["Toy dots"]
    assert [e[2] for e in text] == [rules["rules_text"]]
    assert [e[1]["src"] for e in page.find("img")] == ["original.png"]
    first_key = page.elements.index(page.find("section", "key")[0])
    assert (
        page.elements.index(heading[0])
        < page.elements.index(page.find("img")[0])
        < page.elements.index(text[0])
        < page.elements.index(start[0])
        < first_key
    )
    svg = start[0][3]
    assert "data-key" not in start[0][1]
    assert [e[2] for e in page.find("text", "given") if e[3] == svg] == ["2"]
    assert not [e for e in page.find("text", "cand") if e[3] == svg]


def test_without_an_image_the_page_shows_none():
    page = _toy([_step(["white-a"], (0, 0), [1, 2, 3])], _key(1, 1))

    assert not page.find("img")


@pytest.fixture(scope="module")
def dots_rules(diagonal_dots_run):
    return json.loads((diagonal_dots_run[0] / "rules.json").read_text())


def test_a_stuck_guide_draws_the_grid_and_candidates_at_the_stuck_point(
    dots_rules, diagonal_dots_record
):
    rules = dots_rules
    record = json.loads(json.dumps(diagonal_dots_record))
    record["steps"] = record["steps"][:41]
    state = step_search.State(rules)
    for step in record["steps"]:
        state.apply(step_search.claim_from_json(step["claim"]))
    record["stuck"] = state.snapshot()

    page = Page(guide_html.guide_page(rules, record, _guide(_fill(1, 41))))

    stuck = page.find("svg", "grid")[-1][3]
    assert not page.grids()
    drawn = {
        (e[1]["data-cell"], int(e[1]["data-digit"]))
        for e in page.find("text", "cand")
        if e[3] == stuck
    }
    held = state.candidates
    # A cell still holding every digit is drawn blank.
    unsolved = {c: d for c, d in held.items() if 1 < len(d) < rules["size"]}
    assert unsolved
    assert drawn == {(_name(c), d) for c, digits in unsolved.items() for d in digits}
    assert [e[2] for e in page.find("text", "solved") if e[3] == stuck] == [
        str(next(iter(d)))
        for c, d in sorted(held.items())
        if len(d) == 1 and c not in {tuple(g["cell"]) for g in rules["givens"]}
    ]


def test_no_step_line_of_a_diagonal_dots_guide_shows_a_bare_clue_id(
    dots_rules, diagonal_dots_record
):
    steps = diagonal_dots_record["steps"]
    guide = _guide(_fill(1, len(steps)))

    page = Page(guide_html.guide_page(dots_rules, diagonal_dots_record, guide))

    lines = [e[2] for e in page.find("li", "step")]
    ids = [c["id"] for c in dots_rules["clues"]]
    assert len(lines) == len(steps)
    assert all(re.fullmatch(r"r\dc\d (= \d|keeps[\d ]+), from .+\.", s) for s in lines)
    assert not [s for s in lines for clue_id in ids if clue_id in s]


def test_outside_clue_cells_start_empty_on_every_grid(tmp_path):
    """Nextdoor (000N2S): the four skyscraper digits are the solver's to find,
    so the render and every step grid draw nothing in those cells."""
    out = tmp_path / "out"
    main([str(SKYSCRAPER), str(out), "--max-steps", "0"])
    rules = json.loads((out / "rules.json").read_text())

    assert rules["solution_outside"]
    page = Page((out / "render.html").read_text())
    assert not page.find("text", "clue")
    assert [e[2] for e in page.find("text", "given")] == [
        str(g["digit"]) for g in rules["givens"]
    ]
    assert not page.find("text", "solved")
    assert len(page.find("rect", "cell")) == 16 + len(rules["solution_outside"])

    record = {"steps": [], "timeouts": [], "stuck": None}
    guide = Page(guide_html.guide_page(rules, record, _guide()))
    assert not guide.find("text", "clue")


def test_the_command_line_writes_a_plain_render_beside_the_original(tmp_path):
    out = tmp_path / "out"
    main([str(PUZZLE), str(out), "--max-steps", "0", "--image", "original.png"])
    page = Page((out / "render.html").read_text())

    assert [e[1]["src"] for e in page.find("img")] == ["original.png"]
    svg = page.find("svg")[0][3]
    assert page.find("svg", "grid") and not page.grids()
    # The given and every clue drawn: 6x6 cells, one 4 given, the dots.
    assert len([e for e in page.find("rect", "cell") if e[3] == svg]) == 36
    assert [e[2] for e in page.find("text", "given")] == ["4"]
    assert len(page.find("circle", "dot")) == len(
        json.loads((out / "rules.json").read_text())["clues"]
    )
    assert not page.find("rect", "used")


def test_the_render_is_written_even_when_a_check_fails(tmp_path, dots_rules):
    rules = dict(dots_rules, clues=[], givens=[])
    source = tmp_path / "bare.json"
    source.write_text(json.dumps(rules))
    out = tmp_path / "second"

    assert main([str(source), str(out)]) == 1
    assert (out / "render.html").exists()
    assert not (out / "guide.html").exists()


DIAMOND_BOARD = FIXTURES / "lockout-tessellation-000PT1.json"


def test_a_board_with_holes_draws_only_its_cells_and_outlines_them():
    """The diamond of Logic Masters 000PT1: a stuck point at the start draws
    the 41 cells of the diamond and a thick edge wherever a cell meets a hole
    or the sheet's edge."""
    rules = sudokupad_import.rules_file(json.loads(DIAMOND_BOARD.read_text()))
    record = step_search.new_record()
    record["stuck"] = step_search.State(rules).snapshot() | {"timeouts": 0}
    page = Page(guide_html.guide_page(rules, record, _guide()))

    stuck = page.find("svg", "grid")[-1][3]
    drawn = {e[1]["data-cell"] for e in page.find("rect", "cell") if e[3] == stuck}
    assert drawn == {_name(c) for c in DIAMOND}
    drawn_edges = {
        tuple(int(float(e[1][k]) // guide_html.CELL) for k in ("x1", "y1", "x2", "y2"))
        for e in page.find("line", "edge")
        if e[3] == stuck
    }
    # Where a cell meets a hole: the cell's own side, as (x1, y1, x2, y2) in
    # cell units. The diamond's perimeter is 36 edges, as a 9x9 square's is, so
    # the count alone cannot tell the two outlines apart.
    sides = {(0, 1): (1, 0, 1, 1), (0, -1): (0, 0, 0, 1)}
    sides |= {(1, 0): (0, 1, 1, 1), (-1, 0): (0, 0, 1, 0)}
    expected = {
        (c + a, r + b, c + x, r + y)
        for r, c in DIAMOND
        for (dr, dc), (a, b, x, y) in sides.items()
        if (r + dr, c + dc) not in DIAMOND
    }
    assert drawn_edges == expected


def _guide_file(tmp_path, guide):
    path = tmp_path / "guide.json"
    path.write_text(json.dumps(guide))
    return path


def test_the_command_line_renders_the_guide_file_it_is_given(
    tmp_path, diagonal_dots_steps, diagonal_dots_record
):
    out = tmp_path / "out"
    out.mkdir()
    (out / "steps.json").write_bytes(diagonal_dots_steps.read_bytes())
    steps = len(diagonal_dots_record["steps"])
    path = _guide_file(tmp_path, _guide(_fill(1, steps, "Every step, as fill.")))

    code = main([str(PUZZLE), str(out), "--guide", str(path)])

    page = Page((out / "guide.html").read_text())
    assert code == 0
    assert [e[2] for e in page.find("p", "fill")] == ["Every step, as fill."]
    assert len(page.find("li", "step")) == steps


def test_a_guide_file_that_is_not_json_is_refused_before_anything_is_written(
    tmp_path, capsys
):
    path = tmp_path / "guide.json"
    path.write_text("{not json")
    out = tmp_path / "out"

    assert main([str(PUZZLE), str(out), "--guide", str(path)]) == 2
    assert "guide.json" in capsys.readouterr().err
    assert not out.exists()


def test_a_guide_file_that_skips_a_step_is_refused_and_no_guide_is_written(
    tmp_path, capsys
):
    path = _guide_file(tmp_path, _guide(_fill(2, 2)))
    out = tmp_path / "out"

    code = main([str(PUZZLE), str(out), "--max-steps", "2", "--guide", str(path)])

    assert code == 2
    assert "skips step 1" in capsys.readouterr().err
    assert not (out / "guide.html").exists()
    assert (out / "steps.json").exists()


def _struck(page, grid):
    return {
        (e[1]["data-cell"], int(e[1]["data-digit"]))
        for e in page.find("text", "struck")
        if e[3] == grid
    }


SUBSET_STEPS = [
    _step(["white-a"], (0, 0), [1, 2, 3]),
    _step(["white-b"], (2, 2), [1, 2, 3]),
    _step(["white-a"], (0, 1), [1, 2, 3]),
]


def test_an_idea_that_explains_a_subset_strikes_and_marks_only_those_steps():
    page = _toy(SUBSET_STEPS, _key(1, 3, explains=[1, 3]))

    grid = page.grids()[1]
    assert _struck(page, grid) == {("r1c1", 4), ("r1c2", 4)}
    assert page.cells(grid, "changed") == {"r1c1", "r1c2"}
    assert "r3c3" not in {e[1]["data-cell"] for e in page.find("text", "cand")}


def test_the_steps_an_idea_does_not_explain_are_applied_but_not_drawn():
    page = _toy(
        [
            _step(["row 1"], (0, 0), [1, 2, 3]),
            _step(["white-a"], (0, 0), [2, 3]),
        ],
        _key(1, 2, explains=[2]),
    )

    grid = page.grids()[1]
    drawn = {
        int(e[1]["data-digit"])
        for e in page.find("text", "cand")
        if e[3] == grid and e[1]["data-cell"] == "r1c1"
    }
    assert drawn == {1, 2, 3}
    assert _struck(page, grid) == {("r1c1", 1)}


def test_a_later_unexplained_step_leaves_the_explained_steps_start_alone():
    page = _toy(
        [
            _step(["white-a"], (0, 0), [1, 2, 3]),
            _step(["white-b"], (2, 2), [1, 2, 3]),
        ],
        _key(
            1,
            2,
            explains=[1],
            supposition=_suppose(assume=("r1c1", 4), forces=(), breaks=("r1c2",)),
        ),
    )

    assert page.find("svg", "grid")[2][1]["data-supposition"] == "1"


def test_the_unexplained_steps_are_listed_under_also_in_this_stretch():
    page = _toy(SUBSET_STEPS, _key(1, 3, explains=[1, 3]))

    details = page.find("details", "also")
    assert len(details) == 1
    summary = page.find("summary")
    assert [e[2] for e in summary] == ["Also in this stretch"]
    assert [(e[1]["data-step"], e[2]) for e in page.find("li", "step")] == [
        ("2", "r3c3 keeps 1 2 3, from white dot r3c3-r3c4.")
    ]


def test_an_idea_with_no_list_explains_its_whole_run_and_lists_nothing_else():
    page = _toy(SUBSET_STEPS, _key(1, 3))

    assert not page.find("details")
    assert _struck(page, page.grids()[1]) == {
        ("r1c1", 4),
        ("r1c2", 4),
        ("r3c3", 4),
    }


def test_extra_marks_draw_on_the_ideas_grid():
    page = _toy(
        SUBSET_STEPS[:1],
        _key(
            1,
            1,
            marks=[
                {"type": "arrow", "from": "r1c1", "to": "r2c2"},
                {"type": "circle", "cell": "r4c4"},
                {"type": "label", "cell": "r3c1", "text": "pair"},
                {"type": "highlight", "cell": "r2c3"},
            ],
        ),
    )

    grid = page.grids()[1]
    arrows = [e for e in page.find("line", "arrow") if e[3] == grid]
    assert [(e[1]["data-from"], e[1]["data-to"]) for e in arrows] == [("r1c1", "r2c2")]
    circles = [e for e in page.find("circle", "circle") if e[3] == grid]
    assert [e[1]["data-cell"] for e in circles] == ["r4c4"]
    labels = [e for e in page.find("text", "label") if e[3] == grid]
    assert [(e[1]["data-cell"], e[2]) for e in labels] == [("r3c1", "pair")]
    assert page.cells(grid, "highlight") == {"r2c3"}


@pytest.mark.parametrize(
    ("entry", "cause"),
    [
        (_key(1, 3, explains=[4]), r"entry 1.*step 4.*outside.*steps 1-3"),
        (_key(2, 3, explains=[1]), r"entry 1.*step 1.*outside.*steps 2-3"),
        (_key(1, 3, explains=[2, 2]), r"entry 1.*repeats step 2"),
        (_key(1, 3, explains="1"), r"entry 1.*explains.*list"),
        (_key(1, 3, explains=[]), r"entry 1.*explains.*empty"),
        (
            _key(1, 3, marks=[{"type": "circle", "cell": "r5c1"}]),
            r"entry 1.*mark 1.*r5c1.*outside the grid",
        ),
        (
            _key(1, 3, marks=[{"type": "arrow", "from": "r1c1", "to": "r1c9"}]),
            r"entry 1.*mark 1.*r1c9.*outside the grid",
        ),
        (
            _key(1, 3, marks=[{"type": "star", "cell": "r1c1"}]),
            r"entry 1.*mark 1.*type 'star'",
        ),
        (
            _key(1, 3, marks=[{"type": "label", "cell": "r1c1"}]),
            r"entry 1.*mark 1.*text",
        ),
        (
            _key(1, 3, marks=[{"type": "circle", "cell": "x"}]),
            r"entry 1.*mark 1.*cell 'x'",
        ),
    ],
    ids=[
        "past-run",
        "before-run",
        "repeated",
        "not-a-list",
        "empty",
        "circle-outside",
        "arrow-outside",
        "unknown-type",
        "label-no-text",
        "not-a-cell-name",
    ],
)
def test_a_bad_explained_step_or_mark_is_refused_naming_its_cause(entry, cause):
    with pytest.raises(ValueError, match=cause):
        guide_html.guide_page(TOY, _record(*SUBSET_STEPS), _guide(entry))


def _suppose(assume=("r1c1", 4), forces=(("r1c2", 3), ("r2c2", 2)), breaks=("r2c1",)):
    return {
        "assume": {"cell": assume[0], "digit": assume[1]},
        "forces": [{"cell": c, "digit": d} for c, d in forces],
        "breaks": list(breaks),
    }


def _by_grid(page, cls, grid):
    return [e for e in page.find("text", cls) if e[3] == grid]


def test_a_supposition_draws_a_second_grid_in_the_ideas_row():
    page = _toy(SUBSET_STEPS[:1], _key(1, 1, supposition=_suppose()))

    row = page.find("section", "key")
    assert len(row) == 1
    grids = page.find("svg", "grid")[1:]
    assert [(e[1].get("data-key"), e[1].get("data-supposition")) for e in grids] == [
        ("1", None),
        (None, "1"),
    ]


def test_a_supposition_numbers_the_forced_digits_in_order_and_circles_the_clash():
    page = _toy(SUBSET_STEPS[:1], _key(1, 1, supposition=_suppose()))

    second = next(e for e in page.find("svg", "grid") if e[1].get("data-supposition"))[
        3
    ]
    assumed = _by_grid(page, "assumed", second)
    assert [(e[1]["data-cell"], e[1]["data-digit"]) for e in assumed] == [("r1c1", "4")]
    forced = _by_grid(page, "forced", second)
    assert [
        (e[1]["data-cell"], e[1]["data-digit"], e[1]["data-order"]) for e in forced
    ] == [
        ("r1c2", "3", "1"),
        ("r2c2", "2", "2"),
    ]
    assert [(e[1]["data-cell"], e[2]) for e in _by_grid(page, "order", second)] == [
        ("r1c2", "1"),
        ("r2c2", "2"),
    ]
    circles = [e for e in page.find("circle", "circle") if e[3] == second]
    assert [e[1]["data-cell"] for e in circles] == ["r2c1"]
    # the main grid carries no supposition marks
    main = page.grids()[1]
    assert not _by_grid(page, "assumed", main) and not _by_grid(page, "forced", main)
    assert not [e for e in page.find("circle", "circle") if e[3] == main]


def test_a_supposition_grid_starts_from_the_ideas_starting_candidates():
    page = _toy(SUBSET_STEPS[:1], _key(1, 1, supposition=_suppose()))

    second = next(e for e in page.find("svg", "grid") if e[1].get("data-supposition"))[
        3
    ]
    drawn = {
        int(e[1]["data-digit"])
        for e in page.find("text", "cand")
        if e[3] == second and e[1].get("data-cell") == "r1c2"
    }
    assert drawn == {1, 2, 3, 4}


def test_an_idea_without_a_supposition_draws_one_grid():
    page = _toy(SUBSET_STEPS[:1], _key(1, 1))

    assert len([e for e in page.find("svg", "grid") if e[1].get("data-key")]) == 1


def test_an_assumed_digit_the_steps_do_not_eliminate_is_refused_naming_it():
    with pytest.raises(ValueError, match=r"entry 1.*r1c1.*1.*eliminate"):
        guide_html.guide_page(
            TOY,
            _record(*SUBSET_STEPS[:1]),
            _guide(_key(1, 1, supposition=_suppose(assume=("r1c1", 1)))),
        )


def test_an_assumed_digit_only_an_unexplained_step_eliminates_is_refused():
    with pytest.raises(ValueError, match=r"entry 1.*r1c1.*4.*eliminate"):
        guide_html.guide_page(
            TOY,
            _record(*SUBSET_STEPS),
            _guide(_key(1, 3, explains=[2], supposition=_suppose())),
        )


def test_a_drawn_digit_that_is_not_a_candidate_is_refused_naming_it():
    steps = [_step(["row 1"], (0, 2), [1, 2, 3]), SUBSET_STEPS[0]]
    guide = _guide(
        _fill(1, 1),
        _key(2, 2, supposition=_suppose(forces=(("r1c3", 4),))),
    )
    with pytest.raises(ValueError, match=r"entry 2.*r1c3.*4.*not a candidate"):
        guide_html.guide_page(TOY, _record(*steps), guide)


@pytest.mark.parametrize(
    ("supposition", "cause"),
    [
        ("r1c1", r"entry 1.*supposition.*object"),
        ({"assume": {"cell": "r1c1", "digit": 4}}, r"entry 1.*supposition.*no"),
        (
            {**_suppose(), "extra": 1},
            r"entry 1.*supposition.*unknown fields.*extra",
        ),
        (_suppose(assume=("r9c1", 4)), r"entry 1.*r9c1.*outside the grid"),
        (_suppose(assume=("r1c1", 9)), r"entry 1.*digit 9"),
        (_suppose(forces=(("r1c9", 1),)), r"entry 1.*r1c9.*outside the grid"),
        (_suppose(breaks=("r7c7",)), r"entry 1.*r7c7.*outside the grid"),
        (_suppose(breaks=()), r"entry 1.*breaks.*empty"),
    ],
    ids=[
        "not-object",
        "missing",
        "unknown",
        "assume-outside",
        "digit-range",
        "force-outside",
        "break-outside",
        "no-break",
    ],
)
def test_a_malformed_supposition_is_refused_naming_its_cause(supposition, cause):
    with pytest.raises(ValueError, match=cause):
        guide_html.guide_page(
            TOY,
            _record(*SUBSET_STEPS[:1]),
            _guide(_key(1, 1, supposition=supposition)),
        )
