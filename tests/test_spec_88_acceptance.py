"""Spec #88 end to end: a prepared `Step` built by hand refuses bad input with
the same `ValueError` `prove` raises, a poster's own `KeyError` reaches its
author as itself while an undeclared cell is named, and `forbid` rules out one
assignment with no `tag`, read off the public functions.

Blind to: the consumers. grid-hunts and sudokumaker-custom-constraints both
track main and each lock a commit in `uv.lock`, so none of this runs against
their code until one of them runs `uv lock --upgrade-package sudoku-kit`; a
changed second solution from `check_uniqueness` reaches them only then. Also
blind to the spec's static criteria, checked by reading the diff: the link
tests' one app fake, the cut test and comments, the solve-count floor, and the
AGENTS.md bullet.
"""

import pytest
from ortools.sat.python import cp_model

from sudoku_kit.cpsat import forbid
from sudoku_kit.step_prover import Chain, Poster, Step, house, prove
from sudoku_kit.uniqueness import check_uniqueness

A, B, C = (0, 0), (0, 1), (0, 2)


def _board():
    return {(r, c): {1, 2, 3, 4} for r in range(4) for c in range(4)}


@pytest.mark.parametrize(
    ("registry", "names", "claim", "message"),
    [
        ({}, [], "A < B", "unknown claim 'A < B'"),
        ({"off": house([A, (9, 9)])}, ["off"], Chain([A, B]), r"'off'.*\(9, 9\)"),
        ({}, [], Chain([A, (9, 9)]), r"claim.*\(9, 9\)"),
    ],
    ids=["claim kind", "named cell off board", "claim cell off board"],
)
def test_a_step_built_by_hand_refuses_what_prove_refuses(
    registry, names, claim, message
):
    named = tuple((n, registry[n]) for n in names)
    for build in (
        lambda: prove(_board(), registry, names, claim),
        lambda: Step(_board(), named, (), claim, 10.0, 1),
    ):
        with pytest.raises(ValueError, match=message):
            build()


def test_a_posters_own_keyerror_is_its_own_and_an_undeclared_cell_is_named():
    def own_bug(m, x):
        {}[B]

    def reaches(m, x):
        m.Add(x[A] != x[B])

    with pytest.raises(KeyError) as raised:
        prove(_board(), {"buggy": Poster([A], own_bug)}, ["buggy"], Chain([A, C]))
    assert raised.value.args == (B,)
    with pytest.raises(ValueError, match=r"'sneaky' uses cell \(0, 1\)"):
        prove(_board(), {"sneaky": Poster([A], reaches)}, ["sneaky"], Chain([A, C]))


def test_forbid_rules_out_one_assignment_and_takes_no_tag():
    m = cp_model.CpModel()
    x = {"x": m.NewIntVar(1, 2, "x"), "y": m.NewIntVar(1, 2, "y")}
    forbid(m, x, {"x": 1, "y": 1})
    forbid(m, x, {"x": 2, "y": 2})
    result = check_uniqueness(m, x)
    assert result.status == "not_unique"
    assert {tuple(sorted(s.items())) for s in (result.first, result.second)} == {
        (("x", 1), ("y", 2)),
        (("x", 2), ("y", 1)),
    }
    with pytest.raises(TypeError):
        forbid(m, x, {"x": 1}, tag="t")
