"""Spec #37 end to end: every unit the step prover posts is a named Poster,
given chains included; the prepared step answers all three entry points; an
invalid model raises with CP-SAT's reason; and only an undeclared board cell
is relabelled.

Blind to: outside callers. grid-hunts and sudokumaker-custom-constraints pin
v0.1.0 and import no step prover, so the `Order` -> `Chain` rename reaches
them only when they bump their tag. Also blind to the spec's static and docs
criteria, checked by hand: `radon cc --min C src/sudoku_kit/step_prover.py`
reporting nothing, the `rg` checks on `docs/agents` (#42) and for the old
names `Order` and `posters` (#44). The Either tag criterion (#41) is
`tests/test_step_prover.py`'s, not driven here.
"""

import pytest

from sudoku_kit.step_prover import (
    Chain,
    Elimination,
    IrreducibleResult,
    Place,
    Poster,
    ProofResult,
    house,
    irreducible,
    propagation,
    prove,
)

A, B, C = (0, 0), (0, 1), (0, 2)


def test_the_step_prover_end_to_end():
    # Only the given chain A < B makes A 1; house ab is never needed.
    cands = {A: {1, 2}, B: {1, 2}, C: {1, 2, 3}}
    registry = {"ab": house([A, B])}
    given = [Chain([A, B])]
    place = Place(A, {1})

    assert prove(cands, registry, ["ab"], place, given=given) == ProofResult("proved")
    assert irreducible(cands, registry, ["ab"], place, given=given) == (
        IrreducibleResult("proved", (), None, True)
    )
    result = propagation(cands, registry, [], place, given=given)
    assert result.proves
    assert result.log[0] == Elimination("negated claim", A, (1,))
    assert {e.by for e in result.log[1:]} == {"given chain 1"}

    def broken(m, x):
        m.NewIntVar(3, 1, "broken")

    def buggy(m, x):
        {}["missing"]

    def sneaky(m, x):
        m.Add(x[B] == 1)

    registry = {
        "broken": Poster([A], broken),
        "buggy": Poster([A], buggy),
        "sneaky": Poster([A], sneaky),
    }
    for entry in (prove, irreducible, propagation):
        with pytest.raises(ValueError, match='name: "broken"'):
            entry(cands, registry, ["broken"], Chain([A, B]))
        with pytest.raises(KeyError, match="missing"):
            entry(cands, registry, ["buggy"], Chain([A, B]))
        with pytest.raises(ValueError, match="does not declare"):
            entry(cands, registry, ["sneaky"], Chain([A, B]))
