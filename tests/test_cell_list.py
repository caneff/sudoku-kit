"""Lists of cells in words: blocks of rows x columns in r12c34 notation."""

import pytest
from guide_helpers import TOY, make_record, make_step

from sudoku_kit import rules_file


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


def _deduction_lines(tmp_path, capsys, *steps):
    import json

    from sudoku_kit.deduction_lines import main

    (tmp_path / "rules.json").write_text(json.dumps(TOY))
    (tmp_path / "steps.json").write_text(json.dumps(make_record(*steps)))
    assert main([str(tmp_path)]) == 0
    return capsys.readouterr().out.splitlines()


def test_cells_of_one_deduction_with_the_same_change_share_a_block(tmp_path, capsys):
    steps = [make_step(["row 1"], cell, [3]) for cell in [(0, 2), (0, 3)]]
    steps += [make_step(["row 1"], cell, [1, 2]) for cell in [(0, 0), (0, 1)]]

    assert _deduction_lines(tmp_path, capsys, *steps) == [
        "D1 (steps 1, 2, 3, 4): r1c34 are 3; r1c12 lose 3 and 4 (left: 1 2), from row 1."
    ]


def test_a_chain_step_reads_as_its_chain(tmp_path, capsys):
    chain = {"claim": {"chain": [[0, 0], [0, 1]]}, "named": ["white-a"]}

    assert _deduction_lines(tmp_path, capsys, chain) == [
        "D1 (step 1): chain r1c1 < r1c2, from white dot r1c1-r1c2."
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
