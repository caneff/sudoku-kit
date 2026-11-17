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


COOL_S = FIXTURES / "cool-s-000K0Q.json"
COOL_S_LINK = FIXTURES / "cool-s-000K0Q.txt"


def _by_rule(rules, rule):
    return [c for c in rules["clues"] if c["rule"] == rule]


def test_cool_s_imports_its_lines_and_passes_both_checks(tmp_path):
    """Logic Masters 000K0Q: slow thermos, renbans, Dutch whispers and a white
    dot on a 9x9, the stored solution satisfying every one."""
    code, rules, checks = _run(COOL_S, tmp_path)

    assert code == 0
    assert checks["unique"]["status"] == "unique"
    assert checks["solution_fits"] == {"passed": True, "failing": []}
    assert len(rules["clues"]) == 13
    assert len(_by_rule(rules, "renban")) == 2
    assert len(_by_rule(rules, "slow_thermo")) == 2
    assert len(_by_rule(rules, "whisper")) == 8
    assert len(_by_rule(rules, "difference")) == 1
    assert len({c["id"] for c in rules["clues"]}) == 13


def test_cool_s_thermos_run_from_the_bulb_and_whispers_read_four(tmp_path):
    _, rules, _ = _run(COOL_S, tmp_path)

    # The bulbs sit at r5c9 and r6c7; each path starts there, seven cells long.
    starts = sorted(c["cells"][0] for c in _by_rule(rules, "slow_thermo"))
    assert starts == [[4, 8], [5, 6]]
    assert all(len(c["cells"]) == 7 for c in _by_rule(rules, "slow_thermo"))
    assert all(c["values"] == [4] for c in _by_rule(rules, "whisper"))
    # The whisper drawn r1c7, then a diagonal step to r2c6, then r1c6.
    row = [c for c in _by_rule(rules, "whisper") if c["cells"][0] == [0, 6]]
    assert [c["cells"] for c in row] == [[[0, 6], [1, 5], [0, 5]]]


@needs_app
def test_cool_s_link_decodes_to_its_committed_puzzle_json():
    assert sudokupad_codec.read_puzzle(str(COOL_S_LINK)) == json.loads(
        COOL_S.read_text()
    )


def _cool_s(tmp_path, change):
    puzzle = json.loads(COOL_S.read_text())
    change(puzzle)
    path = tmp_path / "changed.json"
    path.write_text(json.dumps(puzzle))
    return path


def test_a_thermo_without_the_word_slow_reads_as_a_strict_thermo(tmp_path):
    def strict(puzzle):
        text = puzzle["metadata"]["rules"].replace("Slow Thermometer", "Thermometer")
        puzzle["metadata"]["rules"] = text.replace("slow thermometer", "thermometer")

    # Read strict, the puzzle's own solution breaks them: the clue's rule moved.
    assert main([str(_cool_s(tmp_path, strict)), str(tmp_path)]) == 1
    rules = json.loads((tmp_path / "rules.json").read_text())
    assert len(_by_rule(rules, "thermo")) == 2
    assert _by_rule(rules, "slow_thermo") == []


def test_a_german_whispers_sentence_reads_its_own_minimum(tmp_path):
    def german(puzzle):
        text = puzzle["metadata"]["rules"]
        puzzle["metadata"]["rules"] = text.replace("at least 4", "at least 5")

    main([str(_cool_s(tmp_path, german)), str(tmp_path)])
    rules = json.loads((tmp_path / "rules.json").read_text())
    assert {tuple(c["values"]) for c in _by_rule(rules, "whisper")} == {(5,)}


def test_a_whispers_sentence_with_no_minimum_is_refused(tmp_path, capsys):
    def vague(puzzle):
        text = puzzle["metadata"]["rules"]
        puzzle["metadata"]["rules"] = text.replace("at least 4", "a lot")

    assert main([str(_cool_s(tmp_path, vague)), str(tmp_path)]) == 2
    assert "at least" in capsys.readouterr().err


def test_a_line_colour_the_rules_text_never_names_is_refused(tmp_path, capsys):
    def no_pink(puzzle):
        text = puzzle["metadata"]["rules"]
        puzzle["metadata"]["rules"] = text.replace("Pink", "Purple")

    assert main([str(_cool_s(tmp_path, no_pink)), str(tmp_path)]) == 2
    assert "pink" in capsys.readouterr().err


def test_a_thermo_line_with_no_bulb_underlay_is_refused(tmp_path, capsys):
    def bulbless(puzzle):
        puzzle["underlays"] = puzzle["underlays"][:1]

    assert main([str(_cool_s(tmp_path, bulbless)), str(tmp_path)]) == 2
    assert "no bulb" in capsys.readouterr().err


def test_an_underlay_that_is_no_thermo_bulb_is_refused(tmp_path, capsys):
    def extra(puzzle):
        puzzle["underlays"].append(
            {"center": [0.5, 4.5], "width": 0.8, "height": 0.8, "rounded": True}
        )

    assert main([str(_cool_s(tmp_path, extra)), str(tmp_path)]) == 2
    assert "bulb" in capsys.readouterr().err


def test_a_line_that_bends_between_cells_is_refused(tmp_path, capsys):
    def bent(puzzle):
        puzzle["lines"][0]["wayPoints"][1] = [3.5, 7.5]

    assert main([str(_cool_s(tmp_path, bent)), str(tmp_path)]) == 2
    assert "bending" in capsys.readouterr().err


DUTCH_DOTS = FIXTURES / "dutch-dots-000KVY.json"
DUTCH_DOTS_LINK = FIXTURES / "dutch-dots-000KVY.txt"


def test_dutch_dots_fills_in_the_cells_between_straight_waypoints(tmp_path):
    """Logic Masters 000KVY: sixteen straight whisper lines of three cells,
    each drawn with two waypoints, plus black dots."""
    code, rules, checks = _run(DUTCH_DOTS, tmp_path)

    assert code == 0
    assert checks["unique"]["status"] == "unique"
    assert checks["solution_fits"] == {"passed": True, "failing": []}
    whispers = _by_rule(rules, "whisper")
    assert len(whispers) == 16
    assert all(len(c["cells"]) == 3 and c["values"] == [4] for c in whispers)
    top_left = [c for c in whispers if c["cells"][0] == [0, 0]]
    assert [c["cells"] for c in top_left] == [[[0, 0], [1, 0], [2, 0]]]


@needs_app
def test_dutch_dots_link_decodes_to_its_committed_puzzle_json():
    assert sudokupad_codec.read_puzzle(str(DUTCH_DOTS_LINK)) == json.loads(
        DUTCH_DOTS.read_text()
    )


def test_a_thermo_drawn_from_its_tip_to_its_bulb_is_written_bulb_first(tmp_path):
    def reversed_lines(puzzle):
        for line in puzzle["lines"]:
            if line["color"] == "#aaaf":
                line["wayPoints"].reverse()

    assert main([str(_cool_s(tmp_path, reversed_lines)), str(tmp_path)]) == 0
    rules = json.loads((tmp_path / "rules.json").read_text())
    starts = sorted(c["cells"][0] for c in _by_rule(rules, "slow_thermo"))
    assert starts == [[4, 8], [5, 6]]


# Sums and outside clues: arrow, killer cage, little killer, skyscraper,
# numbered rooms, anti-knight.

ARROWS = FIXTURES / "arrow-and-whispers-000K2E.json"
SKYSCRAPER = FIXTURES / "skyscraper-nextdoor-000N2S.json"
ROOMS = FIXTURES / "numbered-rooms-berlin-hostel-000NQN.json"
POINTS = FIXTURES / "skyscraper-arrow-points-000MWP.json"


def _passes(code, checks):
    assert code == 0
    assert checks["unique"]["status"] == "unique"
    assert checks["solution_fits"] == {"passed": True, "failing": []}


def test_the_arrow_and_the_whispers_import_with_two_digit_pills(tmp_path):
    """Logic Masters 000K2E: five arrows from two-cell pills, Dutch whispers
    and white dots on a 9x9."""
    code, rules, checks = _run(ARROWS, tmp_path)

    _passes(code, checks)
    arrows = _by_rule(rules, "arrow")
    assert len(arrows) == 5
    assert all(c["values"] == [2] for c in arrows)
    # The pill at the top left is r1c1 over r2c1, read r1c1 first; the shaft
    # runs right along row 1 from r1c2 to r1c9.
    top = next(c for c in arrows if c["cells"][0] == [0, 0])
    assert top["cells"] == [[0, 0], [1, 0], *([0, k] for k in range(1, 9))]
    # The pill at the bottom, r9c7 then r9c8, leaves r9c7 upward to r7c7.
    bottom = next(c for c in arrows if c["cells"][0] == [8, 6])
    assert bottom["cells"][:2] == [[8, 6], [8, 7]]
    assert bottom["cells"][2:] == [[7, 6], [6, 6]]
    assert len(_by_rule(rules, "whisper")) == 6
    assert len(_by_rule(rules, "difference")) == 3


def test_nextdoor_imports_skyscrapers_whose_digits_are_outside_cells(tmp_path):
    """Logic Masters 000N2S, Nextdoor: a 4x4 inside a ring of clue cells, four
    skyscraper clues and four renbans."""
    code, rules, checks = _run(SKYSCRAPER, tmp_path)

    _passes(code, checks)
    assert rules["size"] == 4
    assert len(_by_rule(rules, "skyscraper")) == 4
    assert len(_by_rule(rules, "renban")) == 4
    # The top clue sits above column 4 and reads down it; the right-hand clues
    # sit beside rows 1 to 3 and read leftward.
    top = next(c for c in _by_rule(rules, "skyscraper") if c["cells"][0] == [-1, 3])
    assert top["cells"][1:] == [[r, 3] for r in range(4)]
    right = next(c for c in _by_rule(rules, "skyscraper") if c["cells"][0] == [1, 4])
    assert right["cells"][1:] == [[1, c] for c in (3, 2, 1, 0)]
    assert rules["solution_outside"] == [
        {"cell": [-1, 3], "digit": 2},
        {"cell": [0, 4], "digit": 3},
        {"cell": [1, 4], "digit": 1},
        {"cell": [2, 4], "digit": 3},
    ]
    # The pink renban from the top clue cell runs through it.
    assert any([-1, 3] in c["cells"] for c in _by_rule(rules, "renban"))


def test_berlin_hostel_imports_numbered_rooms_and_a_german_whisper(tmp_path):
    """Logic Masters 000NQN, Berlin Hostel: three numbered rooms and one German
    whisper (at least 2) that runs through two of the outside cells."""
    code, rules, checks = _run(ROOMS, tmp_path)

    _passes(code, checks)
    assert len(_by_rule(rules, "numbered_rooms")) == 3
    [whisper] = _by_rule(rules, "whisper")
    assert whisper["values"] == [2]
    assert whisper["cells"][0] == [2, -1]
    assert [-1, 0] in whisper["cells"]
    # The left clue sits beside row 3 and reads right from it.
    left = next(
        c for c in _by_rule(rules, "numbered_rooms") if c["cells"][0] == [2, -1]
    )
    assert left["cells"][1:] == [[2, c] for c in range(4)]


def test_points_of_interest_reads_an_arrow_whose_bulb_is_an_outside_cell(tmp_path):
    """Logic Masters 000MWP, Points of Interest: skyscrapers and arrows, one
    arrow's bulb being the skyscraper clue cell beside row 3."""
    code, rules, checks = _run(POINTS, tmp_path)

    _passes(code, checks)
    assert len(_by_rule(rules, "skyscraper")) == 4
    arrows = _by_rule(rules, "arrow")
    assert sorted(c["cells"][0] for c in arrows) == [[2, -1], [2, 2], [4, 2]]
    assert all(c["values"] == [1] for c in arrows)
    outside = next(c for c in arrows if c["cells"][0] == [2, -1])
    assert outside["cells"] == [[2, -1], [1, 0], [0, 1]]


@needs_app
def test_the_sum_and_outside_clue_links_decode_to_their_committed_json():
    for name in (
        "arrow-and-whispers-000K2E",
        "skyscraper-nextdoor-000N2S",
        "numbered-rooms-berlin-hostel-000NQN",
        "skyscraper-arrow-points-000MWP",
    ):
        decoded = sudokupad_codec.read_puzzle(str(FIXTURES / f"{name}.txt"))
        assert decoded == json.loads((FIXTURES / f"{name}.json").read_text()), name


def _changed(tmp_path, source, change, name="changed.json"):
    puzzle = json.loads(source.read_text())
    change(puzzle)
    path = tmp_path / name
    path.write_text(json.dumps(puzzle))
    return path


def _import(tmp_path, source, change):
    """Run the command line on `source` after `change(puzzle)`."""
    code = main([str(_changed(tmp_path, source, change)), str(tmp_path / "out")])
    out = tmp_path / "out" / "rules.json"
    return code, json.loads(out.read_text()) if out.exists() else None


def _say(puzzle, sentence):
    puzzle["metadata"]["rules"] += f" {sentence}"


def test_a_wrong_outside_digit_fails_the_check_naming_the_clue(tmp_path):
    _run(SKYSCRAPER, tmp_path / "first")
    rules = json.loads((tmp_path / "first" / "rules.json").read_text())
    rules["solution_outside"][0]["digit"] = 4
    source = tmp_path / "wrong.json"
    source.write_text(json.dumps(rules))

    code, _, checks = _run(source, tmp_path / "second")

    assert code == 1
    assert checks["solution_fits"]["failing"] == [
        "renban-r0c4-r1c5",
        "skyscraper-r0c4-r4c4",
    ]


def test_a_rules_file_with_a_solution_and_no_outside_digit_is_refused(tmp_path, capsys):
    _run(SKYSCRAPER, tmp_path / "first")
    rules = json.loads((tmp_path / "first" / "rules.json").read_text())
    del rules["solution_outside"]
    source = tmp_path / "missing.json"
    source.write_text(json.dumps(rules))

    assert main([str(source), str(tmp_path / "second")]) == 2
    assert "solution_outside" in capsys.readouterr().err


def test_a_clue_cell_two_steps_off_the_grid_is_refused(tmp_path, capsys):
    _run(SKYSCRAPER, tmp_path / "first")
    rules = json.loads((tmp_path / "first" / "rules.json").read_text())
    rules["clues"][-1]["cells"][0] = [-2, 3]
    source = tmp_path / "far.json"
    source.write_text(json.dumps(rules))

    assert main([str(source), str(tmp_path / "second")]) == 2
    assert "[-2, 3]" in capsys.readouterr().err


def _no_arrows(puzzle):
    puzzle["arrows"], puzzle["overlays"] = [], []


def test_outside_digits_no_rule_reads_are_refused(tmp_path, capsys):
    def renamed(puzzle):
        _no_arrows(puzzle)
        text = puzzle["metadata"]["rules"].replace("Skyscrapers", "Towers")
        puzzle["metadata"]["rules"] = text.replace("skyscraper", "tower")

    assert _import(tmp_path, POINTS, renamed)[0] == 2
    assert "no rule reads" in capsys.readouterr().err


def test_a_stored_digit_at_a_corner_of_the_sheet_is_refused(tmp_path, capsys):
    def corner(puzzle):
        solution = puzzle["metadata"]["solution"]
        puzzle["metadata"]["solution"] = "3" + solution[1:]

    assert _import(tmp_path, SKYSCRAPER, corner)[0] == 2
    assert "no row or column" in capsys.readouterr().err


def test_rules_text_naming_both_skyscrapers_and_numbered_rooms_reads_neither(
    tmp_path, capsys
):
    def both(puzzle):
        _no_arrows(puzzle)
        _say(puzzle, "Numbered rooms apply too.")

    assert _import(tmp_path, POINTS, both)[0] == 2
    assert "no rule reads" in capsys.readouterr().err


def test_an_arrow_the_rules_text_never_names_is_refused(tmp_path, capsys):
    def silent(puzzle):
        text = puzzle["metadata"]["rules"].replace("Arrows", "Pointers")
        puzzle["metadata"]["rules"] = text.replace("arrow", "pointer")

    assert _import(tmp_path, POINTS, silent)[0] == 2
    assert "never says arrow" in capsys.readouterr().err


def test_an_arrow_that_starts_outside_any_bulb_is_refused(tmp_path, capsys):
    def stray(puzzle):
        puzzle["arrows"][0]["wayPoints"][0] = [2.5, 2.5]

    assert _import(tmp_path, POINTS, stray)[0] == 2
    assert "start outside a bulb" in capsys.readouterr().err


def test_a_bulb_with_no_arrow_is_refused(tmp_path, capsys):
    def orphan(puzzle):
        puzzle["arrows"].pop(0)

    assert _import(tmp_path, POINTS, orphan)[0] == 2
    assert "overlays" in capsys.readouterr().err


def _first_cage(puzzle):
    puzzle["cages"] = [{"cells": [[0, 0], [0, 1]], "value": "8", "unique": True}]
    _say(puzzle, "Killer cages: digits in a cage differ and sum to its total.")


def test_a_cage_with_a_sum_is_a_killer_cage_when_the_text_says_so(tmp_path):
    # r1c1 and r1c2 hold 5 and 3 in the stored solution.
    code, rules = _import(tmp_path, DIAGONAL_DOTS, _first_cage)

    assert code == 0
    cage = _clue_by_id(rules, "killer-cage-r1c1-r1c2")
    assert cage["rule"] == "killer_cage"
    assert cage["cells"] == [[0, 0], [0, 1]]
    assert cage["values"] == [8]


def _clue_by_id(rules, clue_id):
    [found] = [c for c in rules["clues"] if c["id"] == clue_id]
    return found


def test_a_killer_cage_that_the_stored_solution_breaks_fails_its_check(tmp_path):
    def wrong_total(puzzle):
        _first_cage(puzzle)
        puzzle["cages"][0]["value"] = "9"

    code, _ = _import(tmp_path, DIAGONAL_DOTS, wrong_total)
    checks = json.loads((tmp_path / "out" / "checks.json").read_text())

    assert code == 1
    assert checks["solution_fits"]["failing"] == ["killer-cage-r1c1-r1c2"]


@pytest.mark.parametrize(
    "change",
    [
        lambda c: c.pop("unique"),
        lambda c: c.update(value="two"),
        lambda c: c.pop("value"),
    ],
    ids=["not unique", "no number", "no sum"],
)
def test_a_cage_that_is_not_a_unique_sum_is_refused(tmp_path, capsys, change):
    def edit(puzzle):
        _first_cage(puzzle)
        change(puzzle["cages"][0])

    assert _import(tmp_path, DIAGONAL_DOTS, edit)[0] == 2
    assert "cages" in capsys.readouterr().err


def _little_killer(puzzle):
    puzzle["overlays"].append(
        {"center": [6.5, 2.5], "width": 1, "height": 1, "text": "9", "rounded": True}
    )
    puzzle["arrows"] = [{"wayPoints": [[6.266, 2.266], [6.068, 2.068]]}]
    _say(puzzle, "Little killers: numbers outside the grid sum the diagonal.")


def test_a_number_beside_the_grid_with_an_arrow_is_a_little_killer(tmp_path):
    # The diagonal up and left from below r6c3 holds r6c2 = 6 and r5c1 = 3.
    code, rules = _import(tmp_path, DIAGONAL_DOTS, _little_killer)

    assert code == 0
    [clue] = _by_rule(rules, "little_killer")
    assert clue["cells"] == [[5, 1], [4, 0]]
    assert clue["values"] == [9]


def test_a_little_killer_arrow_that_is_not_diagonal_is_refused(tmp_path, capsys):
    def straight(puzzle):
        _little_killer(puzzle)
        puzzle["arrows"][0]["wayPoints"][1] = [6.068, 2.266]

    assert _import(tmp_path, DIAGONAL_DOTS, straight)[0] == 2
    assert "not diagonal" in capsys.readouterr().err


def test_a_clue_number_with_no_arrow_is_refused(tmp_path, capsys):
    def orphan(puzzle):
        _little_killer(puzzle)
        puzzle["arrows"] = []

    assert _import(tmp_path, DIAGONAL_DOTS, orphan)[0] == 2
    assert "overlays" in capsys.readouterr().err


def test_a_little_killer_the_rules_text_never_names_is_refused(tmp_path, capsys):
    def silent(puzzle):
        _little_killer(puzzle)
        puzzle["metadata"]["rules"] = puzzle["metadata"]["rules"].replace(
            "Little killers", "Sums"
        )

    assert _import(tmp_path, DIAGONAL_DOTS, silent)[0] == 2
    assert "never says little killer" in capsys.readouterr().err


def test_anti_knight_text_adds_every_knights_move_pair(tmp_path):
    code, rules = _import(
        tmp_path,
        DIAGONAL_DOTS,
        lambda p: _say(p, "Anti-knight: cells a knight's move apart may not match."),
    )

    pairs = _by_rule(rules, "anti_knight")
    assert code in (0, 1)  # the stored solution may or may not honour it
    assert len(pairs) == 80  # 4 * 5 * 4 unordered pairs on 6x6
    assert len({c["id"] for c in rules["clues"]}) == len(rules["clues"])
    assert {tuple(c["cells"][0]) for c in pairs} >= {(0, 0), (5, 4)}
    assert all(
        sorted((abs(a[0] - b[0]), abs(a[1] - b[1]))) == [1, 2]
        for a, b in (c["cells"] for c in pairs)
    )


def test_a_knight_sentence_that_forbids_nothing_is_refused(tmp_path, capsys):
    code, _ = _import(
        tmp_path, DIAGONAL_DOTS, lambda p: _say(p, "A knight sits on r1c1.")
    )
    assert code == 2
    assert "knight" in capsys.readouterr().err
