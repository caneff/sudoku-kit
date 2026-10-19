"""`prove`, `irreducible` and `propagation` on a made-up 4x4 board, checkable
by hand.

Every case reaches them through a real CP-SAT solve. The board is 4x4 with
every cell open to 1..4 except the few a case narrows, so a witness that names
a cell no constraint or claim touches is visible as an extra key.
"""

import pytest
from ortools.sat.python import cp_model

from sudoku_kit import cpsat, step_prover
from sudoku_kit.step_prover import (
    Either,
    Elimination,
    IrreducibleResult,
    Order,
    Place,
    Poster,
    ProofResult,
    PropagationResult,
    house,
    irreducible,
    propagation,
    prove,
    table,
)

A, B, C, D = (0, 0), (0, 1), (0, 2), (0, 3)


def _board(narrowed=None):
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


def test_an_either_negation_tags_each_pattern_distinctly():
    m = cp_model.CpModel()
    x = {A: m.NewIntVar(1, 2, "a"), B: m.NewIntVar(1, 2, "b")}
    cells = len(m.Proto().variables)
    Either([{A: 1, B: 2}, {A: 2, B: 1}]).post_negation(m, x)
    names = [v.name for v in m.Proto().variables][cells:]
    assert len(names) == 4
    assert len(set(names)) == 4


def test_an_either_pattern_holds_only_when_all_its_equalities_do():
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
    # (0, 2) is on the board but in no constraint or claim, so the witness
    # must leave it out.
    cands = {(0, 0): {1, 2}, (0, 1): {2, 3}, (0, 2): {1, 2, 3}}
    result = prove(cands, {}, [], Order([(0, 0), (0, 1)]))
    assert result.status == "refuted"
    assert set(result.witness) == {(0, 0), (0, 1)}
    assert result.witness[(0, 0)] >= result.witness[(0, 1)]


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


def test_a_poster_bug_raising_keyerror_on_a_non_cell_key_surfaces_as_itself():
    def post(m, x):
        {}["missing"]

    registry = {"buggy": Poster([A], post)}
    with pytest.raises(KeyError, match="missing"):
        prove(_board(), registry, ["buggy"], Order([A, C]))


def test_a_poster_that_builds_an_invalid_model_raises_with_cpsats_reason():
    # MODEL_INVALID is a broken model, not a step with no grid.
    def post(m, x):
        m.NewIntVar(3, 1, "broken")

    registry = {"broken": Poster([A], post)}
    with pytest.raises(ValueError, match='name: "broken"'):
        prove(_board(), registry, ["broken"], Order([A, B]))


def test_a_claim_of_an_unknown_kind_raises_naming_it():
    with pytest.raises(ValueError, match="unknown claim 'A < B'"):
        prove(_board(), {}, [], "A < B")


def test_named_constraints_that_admit_no_grid_are_contradictory_not_proved():
    registry = {"none": table([A, B], [])}
    for claim in (Place(A, {1}), Order([A, B]), Either([{A: 1}])):
        result = prove(_board(), registry, ["none"], claim)
        assert result == ProofResult("contradictory", None)


def test_houses_the_candidates_cannot_satisfy_are_contradictory():
    cands = _board({A: {1}, B: {1}})
    result = prove(cands, {"ab": house([A, B])}, ["ab"], Place(C, {1}))
    assert result.status == "contradictory"


def test_a_given_chain_the_candidates_cannot_satisfy_is_contradictory():
    cands = _board({A: {3}, B: {2}})
    result = prove(cands, {}, [], Place(C, {1}), given=[Order([A, B])])
    assert result.status == "contradictory"


def test_a_spent_time_limit_on_the_contradiction_solve_is_timeout():
    # The claim removes nothing, so no probe runs: the only solve is the one
    # that asks whether any grid is left.
    cands = _board({C: {2, 3}})
    result = prove(cands, {}, [], Place(C, {2, 3}), time_limit=0.0)
    assert result == ProofResult("timeout", None)


def test_irreducible_drops_a_named_constraint_the_proof_does_not_need():
    cands, registry, claim = _pair_step()
    registry["cd"] = house([C, D])
    result = irreducible(cands, registry, ["ab", "cd", "bc"], claim)
    assert result == IrreducibleResult("proved", ("ab", "bc"), None, True)


def test_irreducible_tries_earlier_names_first_so_a_later_one_is_kept():
    cands = _board({A: {1}, B: {1}, C: {1, 2}})
    registry = {"ac": house([A, C]), "bc": house([B, C])}
    claim = Place(C, {2})
    assert irreducible(cands, registry, ["ac", "bc"], claim).irreducible_set == ("bc",)
    assert irreducible(cands, registry, ["bc", "ac"], claim).irreducible_set == ("ac",)


def test_irreducible_keeps_a_constraint_any_one_probe_of_a_place_needs():
    cands = _board({A: {1}, B: {2}, C: {1, 2, 3}})
    registry = {"ac": house([A, C]), "bc": house([B, C])}
    result = irreducible(cands, registry, ["ac", "bc"], Place(C, {3}))
    assert result == IrreducibleResult("proved", ("ac", "bc"), None, True)


def test_irreducible_on_contradictory_constraints_names_the_conflicting_ones():
    # Three cells open to 1 and 2 cannot all differ; house cd plays no part.
    cands = _board({A: {1, 2}, B: {1, 2}, C: {1, 2}})
    registry = {
        "cd": house([C, D]),
        "ab": house([A, B]),
        "bc": house([B, C]),
        "ac": house([A, C]),
    }
    result = irreducible(cands, registry, ["cd", "ab", "bc", "ac"], Place(D, {4}))
    assert result == IrreducibleResult("contradictory", ("ab", "bc", "ac"), None, True)


def test_irreducible_on_a_refuted_claim_gives_the_witness_and_no_set():
    cands, registry, claim = _pair_step()
    result = irreducible(cands, registry, ["bc"], claim)
    assert result.status == "refuted"
    assert result.irreducible_set is None
    assert result.witness[C] != 3


def test_irreducible_on_a_spent_time_limit_is_timeout_with_no_set():
    cands, registry, claim = _pair_step()
    result = irreducible(cands, registry, ["ab", "bc"], claim, time_limit=0.0)
    assert result == IrreducibleResult("timeout", None, None, False)


def _starve(monkeypatch, starved):
    """Give the k-th CP-SAT solve (counting from 1) no time at all when
    `starved(k)`."""
    calls = []

    def solver(limit, **kwargs):
        calls.append(limit)
        return cpsat.solver(0.0 if starved(len(calls)) else limit, **kwargs)

    monkeypatch.setattr(step_prover, "solver", solver)


def _solves_made(monkeypatch, run):
    """How many CP-SAT solves `run()` makes."""
    calls = []

    def solver(limit, **kwargs):
        calls.append(limit)
        return cpsat.solver(limit, **kwargs)

    monkeypatch.setattr(step_prover, "solver", solver)
    run()
    return len(calls)


def test_prove_runs_every_solve_on_the_workers_it_was_given(monkeypatch):
    threads = []

    def solver(limit, **kwargs):
        s = cpsat.solver(limit, **kwargs)
        threads.append(s.parameters.num_workers)
        return s

    monkeypatch.setattr(step_prover, "solver", solver)
    cands, registry, claim = _pair_step()
    prove(cands, registry, ["ab", "bc"], claim, workers=3)
    assert threads and set(threads) == {3}


def test_a_deletion_trial_that_times_out_keeps_its_constraint(monkeypatch):
    cands, registry, claim = _pair_step()
    registry["cd"] = house([C, D])
    names = ["ab", "cd", "bc"]
    n = _solves_made(monkeypatch, lambda: prove(cands, registry, names, claim))
    _starve(monkeypatch, lambda k: k > n)
    result = irreducible(cands, registry, names, claim)
    assert result == IrreducibleResult("proved", ("ab", "cd", "bc"), None, False)


def test_irreducible_on_contradictory_constraints_posts_no_negation():
    # Houses ab, bc and ac conflict; table a1 plays no part in that. Against
    # the claim's probe (A = 2) instead, a1 alone would do and ab would go.
    cands = _board({A: {1, 2}, B: {1, 2}, C: {1, 2}})
    registry = {
        "ab": house([A, B]),
        "bc": house([B, C]),
        "ac": house([A, C]),
        "a1": table([A], [(1,)]),
    }
    result = irreducible(cands, registry, ["ab", "bc", "ac", "a1"], Place(A, {1}))
    assert result == IrreducibleResult("contradictory", ("ab", "bc", "ac"), None, True)


def test_propagation_settles_a_step_one_constraint_at_a_time():
    cands, registry, claim = _pair_step()
    result = propagation(cands, registry, ["ab", "bc"], claim)
    assert result == PropagationResult(
        True,
        (
            Elimination("negated claim", C, (3,)),
            Elimination("ab", B, (1,)),
            Elimination("bc", B, (2,)),
            Elimination("bc", C, (2,)),
        ),
    )


def _three_pairs_step():
    """A, B, C open to 1..3, D to 3 and 4. Assuming D = 3, houses ad, bd and
    cd take 3 from A, B and C, and three cells open to 1 and 2 cannot all
    differ -- but each pairwise house alone is satisfied by {1, 2}. The claim
    "D keeps only 4" is proved, and only the three pairwise houses reasoned
    together refute D = 3."""
    cands = _board({A: {1, 2, 3}, B: {1, 2, 3}, C: {1, 2, 3}, D: {3, 4}})
    pairs = ["ab", "bc", "ac", "ad", "bd", "cd"]
    registry = {
        name: house([{"a": A, "b": B, "c": C, "d": D}[ch] for ch in name])
        for name in pairs
    }
    return cands, registry, pairs, Place(D, {4})


def test_propagation_does_not_settle_a_step_that_needs_constraints_together():
    cands, registry, names, claim = _three_pairs_step()
    assert prove(cands, registry, names, claim).status == "proved"
    result = propagation(cands, registry, names, claim)
    assert result == PropagationResult(
        False,
        (
            Elimination("negated claim", D, (4,)),
            Elimination("ad", A, (3,)),
            Elimination("bd", B, (3,)),
            Elimination("cd", C, (3,)),
        ),
    )


def test_propagation_takes_the_negated_order_as_one_constraint():
    cands = _board({A: {1, 2}, B: {2, 3}})
    result = propagation(cands, {"ab": house([A, B])}, ["ab"], Order([A, B]))
    assert result == PropagationResult(
        True,
        (
            Elimination("negated claim", A, (1,)),
            Elimination("negated claim", B, (3,)),
            Elimination("ab", A, (2,)),
            Elimination("ab", B, (2,)),
        ),
    )


def test_propagation_takes_each_given_chain_as_one_constraint():
    cands = _board({A: {1, 2, 3}, B: {1, 2, 3}})
    result = propagation(cands, {}, [], Place(A, {1, 2}), given=[Order([A, B])])
    assert result == PropagationResult(
        True,
        (
            Elimination("negated claim", A, (1, 2)),
            Elimination("given chain 1", A, (3,)),
            Elimination("given chain 1", B, (1, 2, 3)),
        ),
    )


def test_propagation_of_a_place_needs_every_run_to_empty_a_cell():
    cands = _board({A: {1}, C: {1, 2, 3}})
    result = propagation(cands, {"ac": house([A, C])}, ["ac"], Place(C, {3}))
    assert result == PropagationResult(
        False,
        (
            Elimination("negated claim", C, (2, 3)),
            Elimination("ac", A, (1,)),
            Elimination("ac", C, (1,)),
            Elimination("negated claim", C, (1, 3)),
        ),
    )


def test_propagation_leaves_the_candidates_alone():
    cands, registry, claim = _pair_step()
    before = {cell: set(digits) for cell, digits in cands.items()}
    propagation(cands, registry, ["ab", "bc"], claim)
    assert cands == before


def test_a_contradiction_check_that_times_out_raises_timeout_error(monkeypatch):
    # Only the first solve, which checks that some grid is left, is starved;
    # the support solves after it would settle the step.
    cands, registry, claim = _pair_step()
    _starve(monkeypatch, lambda k: k == 1)
    with pytest.raises(TimeoutError, match="no verdict"):
        propagation(cands, registry, ["ab", "bc"], claim)


def test_a_support_solve_that_times_out_raises_naming_its_constraint(monkeypatch):
    cands, registry, claim = _pair_step()
    _starve(monkeypatch, lambda k: k > 1)
    with pytest.raises(TimeoutError, match=r"'ab'"):
        propagation(cands, registry, ["ab", "bc"], claim)


def test_propagation_on_contradictory_constraints_raises_instead_of_answering():
    registry = {"none": table([A, B], [])}
    with pytest.raises(ValueError, match=r"'none'.*contradictory"):
        propagation(_board(), registry, ["none"], Place(A, {1}))


def test_a_place_run_opens_with_its_negated_claim_even_when_nothing_is_removed():
    cands = _board({C: {2}})
    result = propagation(cands, {}, [], Place(C, {3}))
    assert result == PropagationResult(False, (Elimination("negated claim", C, ()),))


def test_irreducible_and_propagation_check_their_input_as_prove_does():
    def post(m, x):
        m.Add(x[A] != x[B])

    registry = {"sneaky": Poster([A], post)}
    for helper in (irreducible, propagation):
        with pytest.raises(ValueError, match="no-such-house"):
            helper(_board(), {}, ["no-such-house"], Order([A, B]))
        with pytest.raises(ValueError, match=r"'sneaky'.*\(0, 1\)"):
            helper(_board(), registry, ["sneaky"], Order([A, C]))
