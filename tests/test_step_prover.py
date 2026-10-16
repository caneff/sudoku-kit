"""`prove` on a made-up 4x4 board, checkable by hand.

Every case reaches `prove` through a real CP-SAT solve. The board is 4x4 with
every cell open to 1..4 except the few a case narrows, so a witness that names
a cell no constraint or claim touches is visible as an extra key.
"""

import pytest

from sudoku_kit.step_prover import (
    Either,
    Order,
    Place,
    Poster,
    ProofResult,
    house,
    prove,
    table,
)

A, B, C, D = (0, 0), (0, 1), (0, 2), (0, 3)


def _board(narrowed=None):
    """Every cell of a 4x4 open to 1..4, except the cells in `narrowed`
    ({cell: digits})."""
    cands = {(r, c): {1, 2, 3, 4} for r in range(4) for c in range(4)}
    for cell, digits in (narrowed or {}).items():
        cands[cell] = set(digits)
    return cands


def _pair_step():
    """A is {1}, B is {1, 2}, C is {2, 3}. House ab forces B to 2; house bc
    then forces C to 3. The claim "C keeps only 3" needs both houses."""
    cands = _board({A: {1}, B: {1, 2}, C: {2, 3}})
    registry = {"ab": house([A, B]), "bc": house([B, C])}
    return cands, registry, Place(C, {3})


def test_a_step_that_follows_from_its_named_houses_is_proved():
    cands, registry, claim = _pair_step()
    result = prove(cands, registry, ["ab", "bc"], claim)
    assert result == ProofResult("proved", None)


def test_the_same_step_naming_one_house_too_few_is_refuted_with_a_witness():
    cands, registry, claim = _pair_step()
    result = prove(cands, registry, ["bc"], claim)
    assert result.status == "refuted"
    # The witness breaks the claim: C is not 3. It obeys the named house and
    # the candidates, and it covers only the cells house bc and the claim touch.
    assert result.witness[C] != 3
    assert result.witness[B] != result.witness[C]
    assert set(result.witness) == {B, C}


def test_a_spent_time_limit_is_timeout_never_proved():
    cands, registry, claim = _pair_step()
    result = prove(cands, registry, ["ab", "bc"], claim, time_limit=0.0)
    assert result == ProofResult("timeout", None)


def test_an_order_claim_proved_and_refuted():
    cands = _board({A: {1, 2}, B: {3, 4}})
    assert prove(cands, {}, [], Order([A, B])).status == "proved"
    cands = _board({A: {1, 3}, B: {2, 4}})
    result = prove(cands, {}, [], Order([A, B]))
    assert result.status == "refuted"
    assert result.witness == {A: 3, B: 2}


def test_a_three_cell_order_breaks_on_its_second_link():
    cands = _board({A: {1}, B: {3}, C: {2, 4}})
    result = prove(cands, {}, [], Order([A, B, C]))
    assert result.status == "refuted"
    assert result.witness == {A: 1, B: 3, C: 2}


def test_a_place_claim_proved_and_refuted():
    # Two cells open to {1, 2} take 1 and 2 between them, so C cannot.
    cands = _board({A: {1, 2}, B: {1, 2}, C: {1, 2, 3}})
    registry = {"abc": house([A, B, C]), "ac": house([A, C])}
    assert prove(cands, registry, ["abc"], Place(C, {3})).status == "proved"
    # House ac alone leaves B out of it, so C may still be 1 or 2.
    result = prove(cands, registry, ["ac"], Place(C, {3}))
    assert result.status == "refuted"
    assert result.witness[C] != 3
    assert result.witness[A] != result.witness[C]


def test_a_place_claim_checks_every_candidate_it_removes():
    # House ac leaves C open to 2 and 3. Removing 1 is infeasible, removing 2
    # is not: the refutation comes from the second solve, not the first.
    cands = _board({A: {1}, C: {1, 2, 3}})
    registry = {"ac": house([A, C])}
    result = prove(cands, registry, ["ac"], Place(C, {3}))
    assert result.status == "refuted"
    assert result.witness == {A: 1, C: 2}
    assert prove(cands, registry, ["ac"], Place(C, {2, 3})).status == "proved"


def test_a_place_claim_that_removes_nothing_is_proved():
    cands = _board({C: {2, 3}})
    assert prove(cands, {}, [], Place(C, {2, 3, 4})).status == "proved"


def test_an_either_claim_proved_and_refuted():
    cands = _board({A: {1, 2}, B: {1, 2}})
    registry = {"ab": house([A, B])}
    claim = Either([{A: 1, B: 2}, {A: 2, B: 1}])
    assert prove(cands, registry, ["ab"], claim).status == "proved"
    result = prove(cands, {}, [], claim)
    assert result.status == "refuted"
    assert result.witness in ({A: 1, B: 1}, {A: 2, B: 2})


def test_an_either_pattern_holds_only_when_all_its_equalities_do():
    # Each pattern needs both cells; A = 1 with B = 1 matches neither.
    cands = _board({A: {1}, B: {1, 2}})
    claim = Either([{A: 1, B: 2}, {A: 2, B: 1}])
    result = prove(cands, {}, [], claim)
    assert result.status == "refuted"
    assert result.witness == {A: 1, B: 1}


def test_a_claim_that_holds_only_under_a_given_chain():
    cands = _board({A: {1, 2, 3}, B: {1, 2, 3}})
    claim = Place(A, {1, 2})
    assert prove(cands, {}, [], claim).status == "refuted"
    result = prove(cands, {}, [], claim, given=[Order([A, B])])
    assert result == ProofResult("proved", None)


def test_a_given_chain_is_in_the_witness_cells():
    cands = _board({A: {1, 2, 3}, B: {1, 2, 3}})
    result = prove(cands, {}, [], Place(A, {1}), given=[Order([A, B])])
    assert result.status == "refuted"
    assert result.witness == {A: 2, B: 3}


def test_a_table_constraint_limits_the_assignments():
    cands = _board({A: {1, 2, 3}, B: {1, 2, 3}})
    registry = {"pairs": table([A, B], [(1, 2), (2, 3)])}
    assert prove(cands, registry, ["pairs"], Place(B, {2, 3})).status == "proved"
    result = prove(cands, registry, ["pairs"], Place(A, {1}))
    assert result.status == "refuted"
    assert result.witness == {A: 2, B: 3}


def test_a_caller_registered_poster_is_named_like_any_other():
    def post(m, x):
        m.Add(x[A] + x[B] == 3)

    cands = _board({A: {1, 2, 3}, B: {1, 2, 3}})
    registry = {"sum3": Poster([A, B], post)}
    assert prove(cands, registry, ["sum3"], Place(A, {1, 2})).status == "proved"


def test_an_unnamed_constraint_is_not_used():
    cands, registry, claim = _pair_step()
    assert prove(cands, registry, [], claim).status == "refuted"


def test_prove_leaves_the_candidates_alone():
    cands, registry, claim = _pair_step()
    before = {cell: set(digits) for cell, digits in cands.items()}
    prove(cands, registry, ["ab", "bc"], claim)
    assert cands == before


def test_an_empty_candidate_set_raises_naming_the_cell():
    cands = _board({(2, 1): set()})
    with pytest.raises(ValueError, match=r"\(2, 1\)"):
        prove(cands, {}, [], Order([A, B]))


def test_an_unknown_constraint_name_raises_naming_it():
    cands = _board()
    with pytest.raises(ValueError, match="no-such-house"):
        prove(cands, {"ab": house([A, B])}, ["no-such-house"], Order([A, B]))


def test_a_claim_cell_off_the_board_raises_naming_it():
    with pytest.raises(ValueError, match=r"\(9, 9\)"):
        prove(_board(), {}, [], Order([A, (9, 9)]))


def test_any_board_size_works():
    cands = {(0, 0): {1, 2}, (0, 1): {2, 3}}
    assert prove(cands, {}, [], Order([(0, 0), (0, 1)])).status == "refuted"


def test_a_named_constraint_cell_off_the_board_raises_naming_it():
    registry = {"off": house([A, (9, 9)])}
    with pytest.raises(ValueError, match=r"'off'.*\(9, 9\)"):
        prove(_board(), registry, ["off"], Order([A, B]))


def test_a_given_chain_cell_off_the_board_raises_naming_it():
    with pytest.raises(ValueError, match=r"given.*\(9, 9\)"):
        prove(_board(), {}, [], Order([A, B]), given=[Order([A, (9, 9)])])


def test_a_poster_reaching_past_its_declared_cells_raises_naming_both():
    def post(m, x):
        m.Add(x[A] != x[B])

    registry = {"sneaky": Poster([A], post)}
    with pytest.raises(ValueError, match=r"'sneaky'.*\(0, 1\)"):
        prove(_board(), registry, ["sneaky"], Order([A, C]))


def test_a_claim_of_an_unknown_kind_raises_naming_it():
    with pytest.raises(ValueError, match="unknown claim 'A < B'"):
        prove(_board(), {}, [], "A < B")
