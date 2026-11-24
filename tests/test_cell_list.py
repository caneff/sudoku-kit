"""Lists of cells in words: blocks of rows x columns in r12c34 notation."""

import pytest
from guide_helpers import TOY, make_record, make_step

from sudoku_kit import guide_html, rules_file


@pytest.mark.parametrize(
    ("cells", "words"),
    [
        ([(0, 4)], "r1c5"),
        ([(0, 4), (0, 5)], "r1c56"),
        ([(0, 2), (0, 3), (1, 2), (1, 3)], "r12c34"),
        ([(1, 0), (0, 0)], "r12c1"),
        ([(0, 0), (0, 2)], "r1c13"),
        # not a block: one block per run of identical column sets, reading order
        ([(0, 0), (0, 1), (1, 0)], "r1c12, r2c1"),
        ([(2, 2), (0, 0)], "r1c1, r3c3"),
        ([(0, 0), (0, 0)], "r1c1"),
        ([(0, 8), (0, 9)], "r1c9,10"),
    ],
)
def test_cells_form_the_fewest_blocks_in_reading_order(cells, words):
    assert rules_file.cell_list(cells) == words


def test_a_single_cell_keeps_its_name():
    assert rules_file.cell_list([(2, 3)]) == rules_file.cell_name((2, 3))


def test_claims_of_one_deduction_on_cells_with_the_same_digits_share_a_block():
    claims = [
        {"cell": [0, 2], "digits": [3]},
        {"cell": [0, 3], "digits": [3]},
        {"cell": [1, 2], "digits": [3]},
        {"cell": [1, 3], "digits": [3]},
        {"cell": [2, 0], "digits": [1, 2]},
        {"cell": [2, 1], "digits": [1, 2]},
    ]
    assert guide_html.describe_claims(claims) == "r12c34 = 3; r3c12 keep 1 2"


def test_a_lone_claim_reads_as_describe_claim_does():
    claim = {"cell": [0, 0], "digits": [1, 2]}
    assert guide_html.describe_claims([claim]) == guide_html.describe_claim(claim)
    chain = {"chain": [[0, 0], [0, 1]]}
    assert guide_html.describe_claims([chain]) == "chain r1c1 < r1c2"


def test_a_deduction_line_groups_cells(tmp_path, capsys):
    import json

    from sudoku_kit.deduction_lines import main

    (tmp_path / "rules.json").write_text(json.dumps(TOY))
    record = make_record(
        make_step(["row 1"], (0, 0), [3]), make_step(["row 1"], (0, 1), [3])
    )
    (tmp_path / "steps.json").write_text(json.dumps(record))
    assert main([str(tmp_path)]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "D1 (steps 1, 2): r1c12 = 3, from row 1."
    ]


def test_a_witness_groups_the_cells_that_take_one_digit():
    witness = {(0, 2): 3, (0, 3): 3, (1, 2): 3, (1, 3): 3, (2, 0): 1}
    assert rules_file.witness_words(witness) == "r12c34=3 r3c1=1"


def test_a_hint_naming_cells_off_the_board_lists_them_in_blocks(tmp_path):
    from sudoku_kit import step_search

    search = step_search.Search(
        TOY | {"size": 4}, make_record(), tmp_path / "steps.json", proof_limit=1
    )
    claim = step_search.claim_from_json({"chain": [[0, 8], [0, 9], [1, 8], [1, 9]]})
    with pytest.raises(ValueError, match=r"cells r12c9,10, not on the board"):
        search.check_hint(claim, ["row 1"])
