"""The solve guide's HTML through the command line, on Diagonal Dots (Logic
Masters 000HUJ, `tests/solve_guide/`).

Most tests resume from a committed step record of the whole solve
(`diagonal-dots-000HUJ-steps.json`), so they read the guide without paying for
the search; one runs the search fresh, twice. The guide is read back as parsed
markup, and the expected shown steps and highlights are rebuilt here from the
rules file and the record, not from the renderer.
"""

import json
import shutil
from html.parser import HTMLParser
from pathlib import Path

import pytest

from sudoku_kit import guide_html, step_search, sudokupad_import
from sudoku_kit.solve_guide import main

FIXTURES = Path(__file__).parent / "solve_guide"
PUZZLE = FIXTURES / "diagonal-dots-000HUJ.json"
RECORD = FIXTURES / "diagonal-dots-000HUJ-steps.json"
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
        """{step number: svg index} for each step grid."""
        return {
            int(e[1]["data-step"]): e[3]
            for e in self.find("svg", "grid")
            if e[1].get("data-step")
        }

    def cells(self, svg, cls):
        return {
            e[1]["data-cell"]
            for e in self.find("rect", "cell")
            if e[3] == svg and cls in e[1]["class"].split()
        }


def _guide(out, *extra, seed=True):
    out.mkdir(parents=True, exist_ok=True)
    if seed:
        shutil.copy(RECORD, out / "steps.json")
    code = main([str(PUZZLE), str(out), *extra])
    return code, Page((out / "guide.html").read_text())


@pytest.fixture(scope="module")
def guide(tmp_path_factory):
    out = tmp_path_factory.mktemp("guide")
    code, page = _guide(out)
    assert code == 0
    return out, page


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


def _expected_shown(steps):
    """Step numbers shown: every step naming a clue or two or more
    constraints."""
    return {
        i
        for i, s in enumerate(steps, 1)
        if len(s["named"]) > 1 or not _is_house(s["named"][0])
    }


def test_the_guide_has_one_grid_per_shown_step_with_that_steps_cells_lit(guide):
    out, page = guide
    rules = json.loads((out / "rules.json").read_text())
    steps = json.loads(RECORD.read_text())["steps"]
    shown = _expected_shown(steps)

    grids = page.grids()
    assert set(grids) == shown
    clues = {c["id"]: c for c in rules["clues"]}
    for i in shown:
        step = steps[i - 1]
        used = set()
        for name in step["named"]:
            used |= (
                _house(rules, name)
                if _is_house(name)
                else {_name(c) for c in clues[name]["cells"]}
            )
        assert page.cells(grids[i], "used") >= used - {_name(step["claim"]["cell"])}
        assert page.cells(grids[i], "changed") == {_name(step["claim"]["cell"])}


def test_a_step_grid_strikes_out_the_digits_the_step_removes(guide):
    _, page = guide
    steps = json.loads(RECORD.read_text())["steps"]
    # Step 41 places r5c3 = 5; before it the cell still held 1, 3 and 5.
    assert steps[40]["claim"] == {"cell": [4, 2], "digits": [5]}
    struck = {
        int(e[1]["data-digit"])
        for e in page.find("text", "struck")
        if e[3] == page.grids()[41] and e[1]["data-cell"] == "r5c3"
    }
    assert struck == {1, 3}


def test_runs_of_singles_appear_as_one_line_each(guide):
    _, page = guide
    steps = json.loads(RECORD.read_text())["steps"]
    shown = _expected_shown(steps)
    runs, run = [], []
    for i in range(1, len(steps) + 1):
        if i in shown:
            runs, run = ([*runs, run] if run else runs), []
        else:
            run.append(i)
    runs = [*runs, run] if run else runs

    lines = page.find("p", "singles")

    assert len(runs) >= 2
    assert [e[1]["data-steps"] for e in lines] == [f"{r[0]}-{r[-1]}" for r in runs]
    assert page.find("svg", "grid") and len(page.grids()) == len(shown)
    assert "r5c1" in lines[0][2]


def test_two_runs_on_the_same_puzzle_show_the_same_steps(tmp_path):
    """Two fresh searches of the whole solve, about 45 seconds each."""
    shown = []
    for k in range(2):
        code, page = _guide(tmp_path / str(k), seed=False)
        assert code == 0
        shown.append(page.grids())
    assert shown[0] == shown[1]
    assert len(shown[0]) == len(
        _expected_shown(json.loads(RECORD.read_text())["steps"])
    )


def test_the_break_in_is_the_first_step_naming_a_clue_or_two_constraints(guide):
    """Pinned on 000HUJ's committed record: step 13 is the first to name a clue
    (a dot), though the first placement is step 41. Only it is labelled."""
    _, page = guide
    steps = json.loads(RECORD.read_text())["steps"]
    first = next(
        i
        for i, s in enumerate(steps, 1)
        if len(s["named"]) > 1 or not _is_house(s["named"][0])
    )

    assert first == 13
    # The label sits above the grid it belongs to, so after the previous svg.
    assert [e[3] + 1 for e in page.find("p", "breakin")] == [page.grids()[13]]
    assert not page.find("p", "hard")


def test_a_step_naming_more_than_three_constraints_is_marked_hard(tmp_path):
    out = tmp_path / "out"
    _guide(out)
    rules = json.loads((out / "rules.json").read_text())
    record = json.loads(RECORD.read_text())
    record["steps"][12]["named"] = [
        "row 5",
        "column 1",
        "region 3",
        "black-dot-r5c1-r6c2",
    ]

    page = Page(guide_html.guide_page(rules, record))

    assert len(page.find("p", "hard")) == 1
    assert "4 constraints" in page.find("p", "hard")[0][2]


def test_a_stuck_guide_draws_the_grid_and_candidates_at_the_stuck_point(tmp_path):
    out = tmp_path / "out"
    _guide(out)
    rules = json.loads((out / "rules.json").read_text())
    record = json.loads(RECORD.read_text())
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


def test_an_arrow_and_a_label_added_to_a_steps_data_are_drawn_on_its_grid(tmp_path):
    record = json.loads(RECORD.read_text())
    record["steps"][40]["annotations"] = [
        {"type": "arrow", "from": [4, 1], "to": [5, 2]},
        {"type": "label", "cell": [3, 3], "text": "no 5 here"},
    ]
    record["steps"][40]["text"] = "The dots pin the 5."
    out = tmp_path / "out"
    out.mkdir()
    (out / "steps.json").write_text(json.dumps(record))

    code, page = _guide(out, seed=False)

    grid = page.grids()[41]
    assert code == 0
    assert [
        (e[1]["data-from"], e[1]["data-to"])
        for e in page.find("line", "arrow")
        if e[3] == grid
    ] == [("r5c2", "r6c3")]
    assert [
        (e[1]["data-cell"], e[2]) for e in page.find("text", "label") if e[3] == grid
    ] == [("r4c4", "no 5 here")]
    assert "The dots pin the 5." in (out / "guide.html").read_text()
    # Nothing leaks onto the other steps' grids.
    assert not [e for e in page.find("line", "arrow") if e[3] != grid]


def test_the_original_image_appears_once_at_the_top_when_given(tmp_path):
    _, page = _guide(tmp_path / "with", "--image", "original.png")
    _, bare = _guide(tmp_path / "without")

    images = page.find("img")
    assert [e[1]["src"] for e in images] == ["original.png"]
    assert page.elements.index(images[0]) < page.elements.index(page.find("svg")[0])
    assert not bare.find("img")


def test_the_command_line_writes_a_plain_render_beside_the_original(tmp_path):
    out = tmp_path / "out"
    _guide(out, "--image", "original.png")
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


def test_the_render_is_written_even_when_a_check_fails(tmp_path):
    first = tmp_path / "first"
    _guide(first)
    rules = json.loads((first / "rules.json").read_text())
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
    diamond = {
        (r, c) for r in range(9) for c in range(9) if abs(r - 4) + abs(c - 4) <= 4
    }

    page = Page(guide_html.guide_page(rules, record))

    stuck = page.find("svg", "grid")[-1][3]
    drawn = {e[1]["data-cell"] for e in page.find("rect", "cell") if e[3] == stuck}
    assert drawn == {_name(c) for c in diamond}
    edges = [e for e in page.find("line", "edge") if e[3] == stuck]
    meeting_a_hole = sum(
        (r + dr, c + dc) not in diamond
        for r, c in diamond
        for dr, dc in ((0, 1), (0, -1), (1, 0), (-1, 0))
    )
    assert len(edges) == meeting_a_hole
