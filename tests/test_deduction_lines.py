"""The `solve-deductions` command: the step record as one line per deduction.

Structure only, never content: the Diagonal Dots record is built at test time
(`diagonal_dots_run` in `conftest.py`) and nothing of it is committed."""

import json
import re

import pytest
from test_solve_guide_html import TOY, _record, _step

from sudoku_kit import guide_html
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


def test_an_invented_board_lists_every_step_once_grouped_as_the_guide_groups(
    tmp_path, capsys
):
    record = _record(
        _step(["white-a"], (0, 0), [1, 2, 3]),
        _step(["row 4"], (3, 3), [1, 2, 3]),
        _step(["white-a"], (0, 1), [1, 2, 3]),
        _step(["row 1"], (0, 0), [1, 2]),
    )
    _write(tmp_path, TOY, record)

    code, lines, _ = _run(tmp_path, capsys)

    groups = [g["steps"] for g in guide_html.deductions(TOY, record)]
    parsed = [LINE.fullmatch(line) for line in lines]
    assert code == 0
    assert all(parsed)
    assert [_numbers(m[2]) for m in parsed] == groups
    assert sorted(n for g in groups for n in g) == [1, 2, 3, 4]
    assert [int(m[1]) for m in parsed] == list(range(1, len(groups) + 1))


def test_a_deduction_line_gives_its_claims_and_names_its_constraints_in_words(
    tmp_path, capsys
):
    _write(tmp_path, TOY, _record(_step(["white-a", "row 1"], (0, 0), [3])))

    _, lines, _ = _run(tmp_path, capsys)

    assert lines == ["D1 (step 1): r1c1 = 3, from white dot r1c1-r1c2 and row 1."]


def test_a_deduction_of_several_steps_joins_its_claims(tmp_path, capsys):
    _write(
        tmp_path,
        TOY,
        _record(
            _step(["white-a"], (0, 0), [1, 2, 3]),
            _step(["white-a"], (0, 1), [4]),
        ),
    )

    _, lines, _ = _run(tmp_path, capsys)

    assert lines == [
        "D1 (steps 1, 2): r1c1 keeps 1 2 3; r1c2 = 4, from white dot r1c1-r1c2."
    ]


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
