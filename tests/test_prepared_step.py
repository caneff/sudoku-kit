"""Spec #12 end to end: one prepared step answers all three entry points,
each claim kind posts its own negation, and the results use the glossary's
words.

Blind to: outside callers -- no outside repo imports the step prover yet, so
the renamed result fields (`proves`, `irreducible_set`) break no caller this
run could miss. Also blind to the spec's static criteria: the seam's ruff
select has no PLR0913 and nothing checks for isinstance dispatch, so
`ruff check --select PLR0913 src/sudoku_kit/step_prover.py` flagging only the
three public functions is checked by hand, not here.
"""

from sudoku_kit.step_prover import (
    Either,
    Elimination,
    IrreducibleResult,
    Place,
    ProofResult,
    house,
    irreducible,
    propagation,
    prove,
)

A, B, C, D = (0, 0), (0, 1), (0, 2), (0, 3)


def test_the_step_prover_end_to_end():
    # A is 1, so house ab makes B 2, and house bc then rules 2 out of C.
    # D is on the board but in no constraint or claim.
    cands = {A: {1}, B: {1, 2}, C: {2, 3}, D: {1, 2, 3}}
    registry = {
        "ab": house([A, B]),
        "bc": house([B, C]),
        "cd": house([C, D]),
    }
    place = Place(C, {3})

    assert prove(cands, registry, ["ab", "bc"], place) == ProofResult("proved")
    assert prove(cands, registry, ["bc"], place) == ProofResult("refuted", {B: 1, C: 2})

    assert irreducible(cands, registry, ["cd", "ab", "bc"], place) == (
        IrreducibleResult("proved", ("ab", "bc"), None, True)
    )

    result = propagation(cands, registry, ["ab", "bc"], place)
    assert result.proves
    assert result.log[0] == Elimination("negated claim", C, (3,))

    either = Either([{B: 2, C: 3}, {B: 1, C: 2}])
    assert prove(cands, registry, ["ab", "bc"], either).status == "proved"
    assert prove(cands, registry, [], either).status == "refuted"
    assert prove(cands, registry, ["ab", "bc"], either, workers=2).status == "proved"
