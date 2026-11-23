"""The solve guide's HTML through the command line, on Diagonal Dots (Logic
Masters 000HUJ, `tests/solve_guide/`).

Most tests resume from the step record of the session's one full search
(`diagonal_dots_run` in `conftest.py`; the record is never committed), so they
read the guide without paying for the search; one more runs the search fresh.
The guide is read back as parsed markup, and the expected highlights are
rebuilt here from the rules file and the record, not from the renderer.

Grouping, key ideas and fill are pinned on `TOY`, a made-up 4x4 board, with
records written by hand, so no test pins a step of a published puzzle.
"""

import json
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest
from link_helpers import DIAMOND

from sudoku_kit import guide_html, step_search, sudokupad_import
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


def _guide(out, *extra, seed=None):
    """Run the guide into `out`, resuming from the step record `seed` if given."""
    out.mkdir(parents=True, exist_ok=True)
    if seed:
        shutil.copy(seed, out / "steps.json")
    code = main([str(PUZZLE), str(out), *extra])
    return code, Page((out / "guide.html").read_text())


@pytest.fixture(scope="module")
def guide(tmp_path_factory, diagonal_dots_steps):
    out = tmp_path_factory.mktemp("guide")
    code, page = _guide(out, seed=diagonal_dots_steps)
    assert code == 0
    return out, page


def _own_copy(record):
    """A deep copy, so a test that edits the session-wide record leaves it be."""
    return json.loads(json.dumps(record))


def _name(cell):
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def _house(rules, name):
    n = rules["size"]
    kind, k = name.split()
    k = int(k) - 1
    if kind == "row":
        return {_name((k, c)) for c in range(n)}
    if kind == "column":
        return {_name((r, k)) for r in range(n)}
    return {_name(c) for c in rules["regions"][k]}


def _is_house(name):
    return name.split()[0] in ("row", "column", "region")


def _used(rules, names):
    clues = {c["id"]: c for c in rules["clues"]}
    used = set()
    for name in names:
        used |= (
            _house(rules, name)
            if _is_house(name)
            else {_name(c) for c in clues[name]["cells"]}
        )
    return used


def test_a_key_ideas_grid_lights_its_cells_and_strikes_what_it_removes(
    guide, diagonal_dots_record
):
    out, page = guide
    rules = json.loads((out / "rules.json").read_text())
    steps = diagonal_dots_record["steps"]
    state, before = step_search.State(rules), []
    for step in steps:
        before.append(dict(state.candidates))
        state.apply(step_search.claim_from_json(step["claim"]))
    for e in page.find("section", "key"):
        group = [int(n) for n in e[1]["data-steps"].split()]
        svg = page.grids()[int(e[1]["data-key"])]
        claims = [steps[n - 1]["claim"] for n in group]
        removed = {}
        for n, claim in zip(group, claims, strict=True):
            cell = tuple(claim["cell"])
            start = removed.get(cell, (before[n - 1][cell], None))[0]
            removed[cell] = (start, start - set(claim["digits"]))
        struck = {
            (t[1]["data-cell"], int(t[1]["data-digit"]))
            for t in page.find("text", "struck")
            if t[3] == svg
        }

        assert page.cells(svg, "changed") == {_name(c["cell"]) for c in claims}
        assert page.cells(svg, "used") >= _used(rules, steps[group[0] - 1]["named"])
        assert struck == {
            (_name(c), d) for c, (_, gone) in removed.items() for d in gone
        }


def test_a_second_fresh_run_shows_the_same_key_ideas_as_the_sessions_run(
    tmp_path, guide
):
    """One more fresh search of the whole solve, about 45 seconds."""
    _, shared = guide
    code, page = _guide(tmp_path)
    assert code == 0
    assert _keys(page) == _keys(shared)
    assert _fill(page) == _fill(shared)


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


def _step(named, cell, digits, **extra):
    """A made-up step on the 4x4 `TOY`: the cell keeps `digits`."""
    return {
        "claim": {"cell": list(cell), "digits": digits},
        "named": named,
        "hard": len(named) > 3,
        "by": "search",
        **extra,
    }


def _toy(*steps):
    return Page(
        guide_html.guide_page(
            TOY, {"steps": list(steps), "timeouts": [], "stuck": None}
        )
    )


def _keys(page):
    """[(key number, its step numbers)] for each key idea, in page order."""
    return [
        (int(e[1]["data-key"]), e[1]["data-steps"]) for e in page.find("section", "key")
    ]


def _fill(page):
    """The step numbers of each fill deduction, in page order."""
    return [e[1]["data-steps"] for e in page.find("li", "deduction")]


def test_steps_on_the_same_constraints_merge_across_a_step_elsewhere():
    page = _toy(
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["row 4"], (3, 3), [1, 2, 3]),
        _step(["white-a"], (0, 1), [1, 2, 3]),
    )

    assert _keys(page) == [(1, "1 3")]
    assert _fill(page) == ["2"]


def test_a_step_changing_a_cell_the_group_uses_keeps_them_apart():
    page = _toy(
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["row 1"], (0, 1), [1, 2, 3]),
        _step(["white-a"], (0, 0), [1, 2]),
    )

    assert _keys(page) == [(1, "1")]
    assert _fill(page) == ["2", "3"]


def test_key_ideas_are_the_break_in_two_constraints_and_each_rule_types_first_use():
    page = _toy(
        _step(["row 1"], (0, 2), [1, 2, 3]),
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["white-b"], (2, 2), [1, 2, 3]),
        _step(["black-a"], (3, 0), [1, 2, 4]),
        _step(["row 2", "column 3"], (1, 2), [1, 2]),
        _step(["white-b", "row 3", "column 3", "region 4"], (2, 3), [2, 3]),
    )

    assert _keys(page) == [(1, "2"), (2, "4"), (3, "5"), (4, "6")]
    assert _fill(page) == ["1", "3"]
    breakin = page.find("p", "breakin")
    assert len(breakin) == 1
    assert page.elements.index(breakin[0]) < page.elements.index(
        page.find("section", "key")[1]
    )
    hard = page.find("p", "hard")
    assert len(hard) == 1 and "4 constraints" in hard[0][2]
    assert page.elements.index(hard[0]) > page.elements.index(
        page.find("section", "key")[3]
    )


def test_a_guide_with_no_clue_has_no_break_in():
    page = _toy(
        _step(["row 1"], (0, 2), [1, 2, 3]),
        _step(["row 2", "column 3"], (1, 2), [1, 2]),
    )

    assert _keys(page) == [(1, "2")]
    assert not page.find("p", "breakin")


def test_each_stretch_of_fill_is_one_sentence_and_a_collapsed_list():
    page = _toy(
        _step(["row 1"], (0, 0), [2]),
        _step(["row 1"], (0, 1), [1, 3]),
        _step(["column 3"], (2, 2), [1, 2, 3]),
        _step(["white-a"], (0, 1), [3]),
        _step(["white-b"], (2, 2), [1, 3]),
        _step(["white-b"], (2, 3), [1, 3]),
    )

    fills = page.find("div", "fill")
    sentences = page.find("p", "fill")
    assert len(fills) == len(sentences) == 2
    assert sentences[0][2] == (
        "Fill: 1 digit placed and 3 candidates removed, from row 1 and column 3."
    )
    assert sentences[1][2] == "Fill: 3 candidates removed, from 1 difference clue."
    assert _fill(page) == ["1 2", "3", "5 6"]
    assert len(page.find("details")) == 2
    text = "".join(e[2] for e in page.elements if e[0] in ("p", "li", "summary"))
    assert ";" not in text
    assert "Step" not in text


def test_a_key_idea_strikes_out_what_all_its_steps_remove():
    page = _toy(
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["white-a"], (0, 1), [1, 2, 3]),
        _step(["white-a"], (0, 0), [2, 3]),
    )

    struck = {
        (e[1]["data-cell"], int(e[1]["data-digit"]))
        for e in page.find("text", "struck")
    }
    assert struck == {("r1c1", 1), ("r1c1", 4), ("r1c2", 4)}
    assert page.cells(page.grids()[1], "changed") == {"r1c1", "r1c2"}
    assert page.cells(page.grids()[1], "used") == {"r1c1", "r1c2"}


def test_the_skills_text_and_marks_show_on_a_key_idea_and_not_in_fill():
    marks = [
        {"type": "arrow", "from": [0, 0], "to": [0, 1]},
        {"type": "label", "cell": [1, 1], "text": "no 4 here"},
    ]
    page = _toy(
        _step(["row 1"], (0, 2), [1, 2, 3], text="Only a fill step."),
        _step(
            ["white-a"], (0, 0), [1, 2, 3], text="The dot pins it.", annotations=marks
        ),
    )

    grid = page.grids()[1]
    assert [
        (e[1]["data-from"], e[1]["data-to"]) for e in page.find("line", "arrow")
    ] == [("r1c1", "r1c2")]
    assert [(e[1]["data-cell"], e[2]) for e in page.find("text", "label")] == [
        ("r2c2", "no 4 here")
    ]
    assert {e[3] for e in page.find("line", "arrow")} == {grid}
    paragraphs = [e[2] for e in page.find("p")]
    assert "The dot pins it." in paragraphs
    assert "Only a fill step." not in "".join(e[2] for e in page.elements)


def test_a_stuck_guide_draws_the_grid_and_candidates_at_the_stuck_point(
    guide, diagonal_dots_record
):
    out, _ = guide
    rules = json.loads((out / "rules.json").read_text())
    record = _own_copy(diagonal_dots_record)
    record["steps"] = record["steps"][:41]
    state = step_search.State(rules)
    for step in record["steps"]:
        state.apply(step_search.claim_from_json(step["claim"]))
    record["stuck"] = state.snapshot()

    page = Page(guide_html.guide_page(rules, record))

    stuck = page.find("svg", "grid")[-1][3]
    assert not [e for e in page.grids().values() if e == stuck]
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
    guide = Page(guide_html.guide_page(rules, record))
    assert not guide.find("text", "clue")


def test_the_original_image_appears_once_at_the_top_when_given(
    tmp_path, diagonal_dots_steps
):
    seed = diagonal_dots_steps
    _, page = _guide(tmp_path / "with", "--image", "original.png", seed=seed)
    _, bare = _guide(tmp_path / "without", seed=seed)

    images = page.find("img")
    assert [e[1]["src"] for e in images] == ["original.png"]
    assert page.elements.index(images[0]) < page.elements.index(page.find("svg")[0])
    assert not bare.find("img")


def test_the_command_line_writes_a_plain_render_beside_the_original(
    tmp_path, diagonal_dots_steps
):
    out = tmp_path / "out"
    _guide(out, "--image", "original.png", seed=diagonal_dots_steps)
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


def test_the_render_is_written_even_when_a_check_fails(tmp_path, diagonal_dots_run):
    rules = json.loads((diagonal_dots_run[0] / "rules.json").read_text())
    rules["clues"], rules["givens"] = [], []
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
    page = Page(guide_html.guide_page(rules, record))

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
