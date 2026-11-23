"""The plain reason sentence under each deduction of the solve guide (#129).

Templates are pinned on a made-up clue, never on a step of a published puzzle.
"""

import json
import re

import pytest
from test_solve_guide_html import TOY, _guide, _step, _toy

from sudoku_kit import clue_rules, reasons, rules_file

PAIRS = {"difference", "ratio", "anti_knight", "tessellation"}


def _clue(rule):
    cells = [[0, 0], [0, 1]] if rule in PAIRS else [[0, 0], [0, 1], [0, 2]]
    return {"id": "zz-secret-id", "rule": rule, "cells": cells, "values": [1]}


def test_every_rule_type_in_the_clue_rule_registry_has_a_reason_template():
    assert set(clue_rules.RULES) - set(reasons.TEMPLATES) == set()


@pytest.mark.parametrize("rule", sorted(clue_rules.RULES))
def test_a_rule_types_reason_names_its_cells_and_never_its_id(rule):
    clue = _clue(rule)
    clause = reasons.TEMPLATES[rule](clue)

    assert rules_file.cell_name(clue["cells"][0]) in clause
    assert "zz-secret-id" not in clause


def test_a_deductions_reason_is_one_sentence_joining_its_constraints():
    sentence = reasons.reason(TOY, ["row 1", "white-a"])

    assert sentence == (
        "This holds because row 1 holds each digit once and r1c1 and r1c2 differ by 1."
    )


def test_a_key_ideas_reason_replaces_the_uses_line_and_the_text_stays():
    page = _toy(_step(["white-a"], (0, 0), [1, 2, 3], text="The dot pins it."))

    paragraphs = [e[2] for e in page.find("p")]
    assert [e[2] for e in page.find("p", "reason")] == [
        "This holds because r1c1 and r1c2 differ by 1."
    ]
    assert "The dot pins it." in paragraphs
    assert not any(p.startswith("Uses") for p in paragraphs)


def test_a_fill_deduction_gives_its_reason_too():
    page = _toy(
        _step(["row 1"], (0, 2), [1, 2, 3]),
        _step(["row 2", "column 3"], (1, 2), [1, 2]),
    )

    assert [e[2] for e in page.find("span", "reason")] == [
        "This holds because row 1 holds each digit once."
    ]


@pytest.fixture(scope="module")
def dots_guide(tmp_path_factory, diagonal_dots_steps):
    out = tmp_path_factory.mktemp("reasons-guide")
    code, page = _guide(out, seed=diagonal_dots_steps)
    assert code == 0
    return out, page


def test_no_deduction_of_the_diagonal_dots_guide_shows_a_bare_clue_id(dots_guide):
    out, page = dots_guide
    rules = json.loads((out / "rules.json").read_text())
    shown = [e[2] for e in page.find("p", "reason") + page.find("span", "reason")]
    ids = [c["id"] for c in rules["clues"]]

    assert len(shown) == len(page.find("section", "key")) + len(
        page.find("li", "deduction")
    )
    assert all(re.fullmatch(r"This holds because .+\.", s) for s in shown)
    assert not [s for s in shown for clue_id in ids if clue_id in s]
