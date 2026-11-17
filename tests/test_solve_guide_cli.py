"""The solve-guide command line, puzzle in, rules file and check results out,
on Diagonal Dots (Logic Masters 000HUJ, `tests/solve_guide/`, copied from the
lmd-archive backup).

The cases read the puzzle JSON committed beside the link, so they run with no
node and no recording of SudokuPad's app; the link's body decodes only through
SudokuPad's loader. One case, which needs both, pins the link to that JSON.

The expected clues are read off the puzzle's picture: eight dots, each on a
grid corner, each joining both diagonal pairs around that corner.
"""

import json
import shutil
from pathlib import Path

import pytest

from sudoku_kit import sudokupad_codec
from sudoku_kit.solve_guide import main

FIXTURES = Path(__file__).parent / "solve_guide"
DIAGONAL_DOTS = FIXTURES / "diagonal-dots-000HUJ.json"
DIAGONAL_DOTS_LINK = FIXTURES / "diagonal-dots-000HUJ.txt"
needs_app = pytest.mark.skipif(
    not shutil.which("node") or not Path(sudokupad_codec.default_har()).exists(),
    reason="node, or the recording of SudokuPad's app, is missing",
)
SOLUTION = "534162612543256431143256325614461325"


def _run(source, out):
    code = main([str(source), str(out)])
    rules = json.loads((out / "rules.json").read_text())
    checks = json.loads((out / "checks.json").read_text())
    return code, rules, checks


def _clue(rules, rule, a, b):
    """The clue of `rule` joining cells `a` and `b`, in either order."""
    pair = {tuple(a), tuple(b)}
    found = [
        c
        for c in rules["clues"]
        if c["rule"] == rule and {tuple(cell) for cell in c["cells"]} == pair
    ]
    assert len(found) == 1, (rule, a, b, rules["clues"])
    return found[0]


def test_diagonal_dots_imports_to_a_rules_file_that_passes_both_checks(tmp_path):
    code, rules, checks = _run(DIAGONAL_DOTS, tmp_path)

    assert code == 0
    assert checks["unique"]["status"] == "unique"
    assert checks["unique"]["passed"]
    assert checks["solution_fits"] == {"passed": True, "failing": []}

    assert rules["size"] == 6
    assert rules["givens"] == [{"cell": [4, 5], "digit": 4}]
    assert "".join(str(d) for row in rules["solution"] for d in row) == SOLUTION
    assert sorted(map(sorted, rules["regions"]))[0] == [
        [0, 0], [0, 1], [0, 2], [1, 0], [1, 1], [1, 2]
    ]  # fmt: skip
    # Eight dots, both diagonals of each: 6 white (difference 1), 2 black (ratio 2).
    assert len(rules["clues"]) == 16
    assert len({c["id"] for c in rules["clues"]}) == 16
    # The black dot at the corner below r1c5 and right of it (top right).
    assert _clue(rules, "ratio", [0, 4], [1, 5])["values"] == [2]
    assert _clue(rules, "ratio", [0, 5], [1, 4])["values"] == [2]
    # The white dot on the box corner at the top middle.
    assert _clue(rules, "difference", [0, 2], [1, 3])["values"] == [1]
    assert _clue(rules, "difference", [0, 3], [1, 2])["values"] == [1]


@needs_app
def test_the_committed_puzzle_json_is_what_the_link_decodes_to():
    decoded = sudokupad_codec.read_puzzle(str(DIAGONAL_DOTS_LINK))
    assert decoded == json.loads(DIAGONAL_DOTS.read_text())


@needs_app
def test_the_link_and_its_puzzle_json_import_to_the_same_rules_file(tmp_path):
    _, from_link, _ = _run(DIAGONAL_DOTS_LINK, tmp_path / "link")
    _, from_json, _ = _run(DIAGONAL_DOTS, tmp_path / "json")
    assert from_link == from_json


def test_a_json_file_that_is_neither_a_puzzle_nor_a_rules_file_is_refused(
    tmp_path, capsys
):
    source = tmp_path / "other.json"
    source.write_text(json.dumps({"hello": 1}))
    assert main([str(source), str(tmp_path / "out")]) == 2
    assert str(source) in capsys.readouterr().err


def test_a_rules_file_with_one_dot_flipped_fails_a_check_naming_the_clue(tmp_path):
    _run(DIAGONAL_DOTS, tmp_path / "first")
    rules = json.loads((tmp_path / "first" / "rules.json").read_text())
    flipped = _clue(rules, "difference", [0, 2], [1, 3])
    flipped["rule"], flipped["values"] = "ratio", [2]
    source = tmp_path / "flipped.json"
    source.write_text(json.dumps(rules))

    code, _, checks = _run(source, tmp_path / "second")

    assert code == 1
    assert checks["solution_fits"] == {"passed": False, "failing": [flipped["id"]]}


def test_a_rules_file_with_no_single_solution_fails_the_uniqueness_check(tmp_path):
    _run(DIAGONAL_DOTS, tmp_path / "first")
    rules = json.loads((tmp_path / "first" / "rules.json").read_text())
    rules["clues"] = []
    rules["givens"] = []
    source = tmp_path / "bare.json"
    source.write_text(json.dumps(rules))

    code, _, checks = _run(source, tmp_path / "second")

    assert code == 1
    assert checks["unique"]["status"] == "not_unique"
    assert not checks["unique"]["passed"]


def _link_file(tmp_path, change):
    """Diagonal Dots' puzzle JSON, written to a file after `change(puzzle)`."""
    puzzle = json.loads(DIAGONAL_DOTS.read_text())
    change(puzzle)
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(puzzle))
    return path


def test_rules_text_naming_no_reading_for_a_dot_colour_is_refused(tmp_path, capsys):
    def no_black_reading(puzzle):
        puzzle["metadata"]["rules"] = (
            "Normal 6x6 sudoku rules apply. Diagonal Kropki dots: digits "
            "diagonally joined by a white dot are consecutive."
        )

    assert main([str(_link_file(tmp_path, no_black_reading)), str(tmp_path)]) == 2
    assert "gives no reading for a black dot" in capsys.readouterr().err
    assert not (tmp_path / "rules.json").exists()


def test_a_corner_dot_without_diagonal_rules_text_is_refused(tmp_path, capsys):
    def orthogonal_text(puzzle):
        puzzle["metadata"]["rules"] = (
            "Normal sudoku rules apply. Cells joined by a white dot are "
            "consecutive; cells joined by a black dot are in a 2:1 ratio."
        )

    assert main([str(_link_file(tmp_path, orthogonal_text)), str(tmp_path)]) == 2
    assert "corner" in capsys.readouterr().err


def test_an_orthogonal_dot_joins_the_two_cells_either_side_of_its_edge(tmp_path):
    def add_edge_dot(puzzle):
        puzzle["overlays"].append(
            {
                "center": [3.5, 1],
                "width": 0.3,
                "height": 0.3,
                "rounded": True,
                "backgroundColor": "#FFFFFF",
                "borderColor": "#000000",
            }
        )
        puzzle["metadata"]["rules"] += " Orthogonal dots follow the same rules."

    main([str(_link_file(tmp_path, add_edge_dot)), str(tmp_path)])
    rules = json.loads((tmp_path / "rules.json").read_text())

    assert _clue(rules, "difference", [3, 0], [3, 1])["values"] == [1]


@pytest.mark.parametrize(
    "shape",
    [
        ("lines", {"wayPoints": [[0.5, 0.5], [1.5, 1.5]], "color": "#000"}),
        ("arrows", {"wayPoints": [[0.5, 0.5], [1.5, 1.5]]}),
        ("cages", {"cells": [[0, 0], [0, 1]], "value": "5"}),
        ("underlays", {"center": [0.5, 0.5], "width": 1, "height": 1}),
        ("overlays", {"center": [2.5, 2.5], "width": 0.6, "height": 0.6}),
    ],
    ids=lambda s: s[0] if isinstance(s, tuple) else s,
)
def test_a_shape_the_importer_does_not_read_is_refused_by_name(tmp_path, capsys, shape):
    kind, item = shape

    def add(puzzle):
        puzzle.setdefault(kind, []).append(item)

    assert main([str(_link_file(tmp_path, add)), str(tmp_path)]) == 2
    assert kind in capsys.readouterr().err
