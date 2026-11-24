"""The `solve-deductions` command: the step record as one line per deduction.

Structure only, never content: the Diagonal Dots record is built at test time
(`diagonal_dots_run` in `conftest.py`) and nothing of it is committed."""

import json
import re

import pytest
from guide_helpers import TOY, make_record, make_step

from sudoku_kit.deduction_lines import main

LINE = re.compile(r"D(\d+) \(steps? ([\d, ]+)\): (.+), from (.+)\.")


def _run(directory, capsys):
    code = main([str(directory)])
    out = capsys.readouterr()
    return code, out.out.splitlines(), out.err


def _write(directory, rules, record):
    (directory / "rules.json").write_text(json.dumps(rules))
    (directory / "steps.json").write_text(json.dumps(record))


def _numbers(text):
    return [int(n) for n in text.split(",")]


def test_an_invented_board_lists_every_step_once_merging_across_a_step_elsewhere(
    tmp_path, capsys
):
    record = make_record(
        make_step(["white-a"], (0, 0), [1, 2, 3]),
        make_step(["row 4"], (3, 3), [1, 2, 3]),
        make_step(["white-a"], (0, 1), [1, 2, 3]),
        make_step(["row 1"], (0, 0), [1, 2]),
    )
    _write(tmp_path, TOY, record)

    code, lines, _ = _run(tmp_path, capsys)

    assert code == 0
    assert lines == [
        "D1 (step 2): r4c4 loses 4, from row 4.",
        "D2 (steps 1, 3): r1c12 lose 4, from white dot r1c1-r1c2.",
        "D3 (step 4): r1c1 loses 3, from row 1.",
    ]


def test_a_deduction_line_gives_its_claims_and_names_its_constraints_in_words(
    tmp_path, capsys
):
    _write(tmp_path, TOY, make_record(make_step(["white-a", "row 1"], (0, 0), [3])))

    _, lines, _ = _run(tmp_path, capsys)

    assert lines == ["D1 (step 1): r1c1 is 3, from white dot r1c1-r1c2 and row 1."]


def test_a_deduction_of_several_steps_joins_its_claims(tmp_path, capsys):
    _write(
        tmp_path,
        TOY,
        make_record(
            make_step(["white-a"], (0, 0), [1, 2, 3]),
            make_step(["white-a"], (0, 1), [4]),
        ),
    )

    _, lines, _ = _run(tmp_path, capsys)

    assert lines == [
        "D1 (steps 1, 2): r1c1 loses 4; r1c2 is 4, from white dot r1c1-r1c2."
    ]


GOOD = make_step(["white-a"], (0, 0), [1, 2, 3])


@pytest.mark.parametrize(
    ("rules", "record", "cause"),
    [
        (TOY, {"step": []}, r"steps\.json has no steps list"),
        (TOY, make_record({"claim": GOOD["claim"]}), r"steps\.json step 1.*named"),
        (TOY, make_record({"named": ["row 1"]}), r"steps\.json step 1.*claim"),
        (TOY, make_record(GOOD, make_step(["dot-z"], (0, 1), [1])), r"step 2.*dot-z"),
        ([TOY], make_record(GOOD), r"rules\.json"),
    ],
    ids=["no-steps-list", "no-named", "no-claim", "unknown-constraint", "rules-list"],
)
def test_a_malformed_record_or_rules_file_is_refused_naming_it(
    tmp_path, capsys, rules, record, cause
):
    _write(tmp_path, rules, record)

    code, lines, err = _run(tmp_path, capsys)

    assert (code, lines) == (2, [])
    assert re.search(cause, err)


def test_a_directory_with_no_step_record_is_refused_naming_the_file(tmp_path, capsys):
    (tmp_path / "rules.json").write_text(json.dumps(TOY))

    code, lines, err = _run(tmp_path, capsys)

    assert (code, lines) == (2, [])
    assert "steps.json" in err


@pytest.fixture(scope="module")
def dots(diagonal_dots_run):
    out = diagonal_dots_run[0]
    return (
        out,
        json.loads((out / "rules.json").read_text()),
        json.loads((out / "steps.json").read_text()),
    )


def test_on_diagonal_dots_every_line_names_its_constraints_in_words(dots, capsys):
    out, rules, record = dots

    code, lines, _ = _run(out, capsys)

    ids = [c["id"] for c in rules["clues"]]
    parsed = [LINE.fullmatch(line) for line in lines]
    assert code == 0
    assert lines
    assert all(parsed)
    assert sorted(n for m in parsed for n in _numbers(m[2])) == list(
        range(1, len(record["steps"]) + 1)
    )
    assert not [line for line in lines for clue_id in ids if clue_id in line]


def test_a_deduction_line_says_box_and_names_a_corner_dot_once(tmp_path, capsys):
    rules = dict(
        TOY,
        clues=[
            {"id": "x1", "rule": "ratio", "cells": [[0, 0], [1, 1]], "values": [2]},
            {"id": "x2", "rule": "ratio", "cells": [[0, 1], [1, 0]], "values": [2]},
        ],
    )
    record = make_record(
        make_step(["region 4"], (2, 2), [1, 2, 3]),
        make_step(["x1", "x2"], (0, 0), [1, 2, 4]),
    )
    _write(tmp_path, rules, record)

    _, lines, _ = _run(tmp_path, capsys)

    assert lines == [
        "D1 (step 1): r3c3 loses 4, from box 4.",
        "D2 (step 2): r1c1 loses 3, from black dot at r12c12.",
    ]
