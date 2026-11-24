"""The guide file end to end at the command line: a puzzle, its step
record from the search, a guide file built from that record, and the guide
page the command draws from it.

The board is invented (a published puzzle's guide file is a solution path,
AGENTS.md), and its guide file is built here from the record the search wrote,
the way the /solve-guide skill builds one after reading it.

Blind to: the consumers. grid-hunts and sudokumaker-custom-constraints both
track main and each lock a commit in `uv.lock`, so a change here never runs
against their code until one of them runs
`uv lock --upgrade-package sudoku-kit`. Blind also to the page as Chromium
draws and prints it, and to whether the skill's words read well: Chris reviews
the skill's Diagonal Dots render for both.
"""

import json
import re

from guide_helpers import cell_name

from sudoku_kit import deduction_lines, step_search
from sudoku_kit.solve_guide import main

BOARD = {
    "size": 4,
    "title": "Invented dots",
    "rules_text": "Normal 4x4 sudoku rules apply.\nWhite dots join consecutive digits.",
    "regions": [
        [[0, 0], [0, 1], [1, 0], [1, 1]],
        [[0, 2], [0, 3], [1, 2], [1, 3]],
        [[2, 0], [2, 1], [3, 0], [3, 1]],
        [[2, 2], [2, 3], [3, 2], [3, 3]],
    ],
    "givens": [
        {"cell": [1, 2], "digit": 1},
        {"cell": [2, 3], "digit": 3},
        {"cell": [3, 1], "digit": 3},
        {"cell": [0, 3], "digit": 4},
        {"cell": [3, 2], "digit": 2},
    ],
    "clues": [
        {
            "id": "white-top",
            "rule": "difference",
            "cells": [[0, 0], [0, 1]],
            "values": [1],
        },
        {"id": "black-left", "rule": "ratio", "cells": [[2, 0], [3, 0]], "values": [2]},
        {
            "id": "white-mid",
            "rule": "difference",
            "cells": [[2, 2], [2, 3]],
            "values": [1],
        },
    ],
    "solution": [[1, 2, 3, 4], [3, 4, 1, 2], [2, 1, 4, 3], [4, 3, 2, 1]],
}
CLUE_IDS = {clue["id"] for clue in BOARD["clues"]}


def _guide_for(record):
    """A guide file for `record` as the skill would write one: fill up to the
    first step naming a clue, a break-in idea there that explains only that
    step and argues it by supposition, a second idea, then fill to the end."""
    steps = record["steps"]
    k = next(i for i, s in enumerate(steps, 1) if CLUE_IDS & set(s["named"]))
    claim = steps[k - 1]["claim"]
    state = step_search.State(BOARD)
    for step in steps[: k - 1]:
        state.apply(step_search.claim_from_json(step["claim"]))
    assumed = min(state.candidates[tuple(claim["cell"])] - set(claim["digits"]))
    cell = cell_name(claim["cell"])
    return {
        "version": 1,
        "entries": [
            {"type": "fill", "first": 1, "last": k - 1, "sentence": "Singles open it."},
            {
                "type": "key",
                "first": k,
                "last": k + 1,
                "explains": [k],
                "break_in": True,
                "heading": "The black dot",
                "paragraphs": ["The first paragraph.", "The second paragraph."],
                "marks": [{"type": "highlight", "cell": cell}],
                "supposition": {
                    "assume": {"cell": cell, "digit": assumed},
                    "forces": [],
                    "breaks": [cell],
                },
            },
            {
                "type": "key",
                "first": k + 2,
                "last": k + 3,
                "heading": "The next idea",
                "paragraphs": ["Its paragraph."],
            },
            {
                "type": "fill",
                "first": k + 4,
                "last": len(steps),
                "sentence": "It ends.",
            },
        ],
    }


def _run(tmp_path, *extra):
    board = tmp_path / "board.json"
    board.write_text(json.dumps(BOARD))
    return main([str(board), str(tmp_path / "out"), *extra])


def test_the_command_draws_a_guide_file_built_from_its_own_step_record(
    tmp_path, capsys
):
    out = tmp_path / "out"

    assert _run(tmp_path) == 0
    assert not (out / "guide.html").exists()
    assert "/solve-guide" in capsys.readouterr().err

    record = json.loads((out / "steps.json").read_text())
    guide = tmp_path / "guide.json"
    guide.write_text(json.dumps(_guide_for(record)))
    assert _run(tmp_path, "--guide", str(guide)) == 0
    page = (out / "guide.html").read_text()

    top = page.index('<section class="key"')
    assert page.index("<h1>Invented dots</h1>") < page.index('class="rules"') < top
    assert re.findall(r'<span class="num">(\d+)</span>', page) == ["1", "2"]
    assert page.count('class="breakin"') == 1
    assert "Singles open it." in page and "It ends." in page
    items = re.findall(r'<li class="step" data-steps="([\d ]+)">([^<]*)</li>', page)
    lines = [text for _, text in items]
    covered = sorted(int(n) for steps, _ in items for n in steps.split())
    assert len(covered) == len(record["steps"]) - 3
    assert len(lines) < len(covered)
    assert "r1c123 lose 4, from row 1." in lines
    assert not [line for line in lines for clue in CLUE_IDS if clue in line]
    assert "Also in this stretch" in page
    assert page.count('data-supposition="1"') == 1
    assert "@page { size: A4; margin: 15mm; }" in page

    skipping = _guide_for(record)
    skipping["entries"][-1]["first"] += 1
    guide.write_text(json.dumps(skipping))
    assert _run(tmp_path, "--guide", str(guide)) == 2
    assert not (out / "guide.html").exists()

    guide.write_text(json.dumps(_guide_for(record)))
    assert _run(tmp_path, "--guide", str(guide)) == 0
    assert _run(tmp_path) == 0
    assert not (out / "guide.html").exists()


def test_the_command_refuses_an_early_removal_that_does_not_hold(tmp_path, capsys):
    out = tmp_path / "out"
    assert _run(tmp_path) == 0
    record = json.loads((out / "steps.json").read_text())
    guide = tmp_path / "guide.json"

    # r2c3 is given 1: 1 is its solution digit and 2 was never a candidate.
    for digit, cause in [
        (1, r"key idea 1 \(entry 2\) removes 1 from r2c3 early.*solution digit"),
        (2, r"key idea 1 \(entry 2\) removes 2 from r2c3 early.*not a candidate"),
    ]:
        early = _guide_for(record)
        early["entries"][1]["early_removals"] = [{"cell": "r2c3", "digits": [digit]}]
        guide.write_text(json.dumps(early))
        capsys.readouterr()
        assert _run(tmp_path, "--guide", str(guide)) == 2
        assert re.search(cause, capsys.readouterr().err)
        assert not (out / "guide.html").exists()


# A corner white dot at r34c23 the solution keeps: r3c2=1, r4c3=2 and r3c3=4,
# r4c2=3. Its two clues are one dot to a reader (#153).
CORNER_BOARD = dict(
    BOARD,
    clues=[
        *BOARD["clues"],
        {"id": "w-a", "rule": "difference", "cells": [[2, 1], [3, 2]], "values": [1]},
        {"id": "w-b", "rule": "difference", "cells": [[2, 2], [3, 1]], "values": [1]},
    ],
)


def _hint(tmp_path, claim, *named):
    board = tmp_path / "corner.json"
    board.write_text(json.dumps(CORNER_BOARD))
    flags = [f for name in named for f in ("--named", name)]
    out = tmp_path / "out"
    return main([str(board), str(out), "--hint", json.dumps(claim), *flags])


def test_named_takes_the_display_names_solve_deductions_prints(tmp_path, capsys):
    out = tmp_path / "out"
    # r2c3 is given 1 and r1c4 given 4, so box 2 keeps both out of r1c3.
    assert _hint(tmp_path, {"cell": [0, 2], "digits": [2, 3]}, "box 2") == 0
    assert json.loads((out / "steps.json").read_text())["steps"][0]["named"] == [
        "region 2"
    ]
    (out / "steps.json").unlink()
    # r4c3 is given 2, so the dot's r3c2-r4c3 clue keeps r3c2 to 1 or 3.
    claim = {"cell": [2, 1], "digits": [1, 3]}
    assert _hint(tmp_path, claim, "white dot at r34c23") == 0
    first = json.loads((out / "steps.json").read_text())["steps"][0]
    assert first["named"] == ["w-a", "w-b"]

    capsys.readouterr()
    assert deduction_lines.main([str(out)]) == 0
    lines = capsys.readouterr().out.splitlines()
    dot = next(line for line in lines if line.startswith("D1 (step"))
    assert "r3c2 loses 2 and 4 (left: 1 3)" in dot
    assert dot.endswith(", from white dot at r34c23.")
    assert all("(left: " in line for line in lines if " loses " in line)


def test_named_refuses_a_name_that_is_neither_a_constraint_nor_its_words(
    tmp_path, capsys
):
    claim = {"cell": [2, 1], "digits": [1, 3]}
    assert _hint(tmp_path, claim, "white dot at r12c34") == 2
    assert "white dot at r12c34" in capsys.readouterr().err
    assert not (tmp_path / "out").exists()
