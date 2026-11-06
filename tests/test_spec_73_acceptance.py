"""Spec #73 end to end: one call from any puzzle source to its document, the
uniqueness check answering in the caller's keys and naming its no-verdict
statuses, the claim kinds named once, and the `shorten` command's exit
contract, read off the public functions.

Blind to: the consumers. grid-hunts and sudokumaker-custom-constraints each
lock a commit in `uv.lock`, so none of this runs against their code until one
moves its lock, and grid-hunts still pins `tag = "v0.1.0"`. Blind to the live
app too: the short link resolves and the upload runs against the shared fake.
Also blind to the spec's static criteria, checked by reading the diff: one
preview-width constant, the cut comments and docstrings, `main`'s docstring,
and the shared test helpers.
"""

import random

import pytest
from link_helpers import ShortLinkApp
from ortools.sat.python import cp_model

from sudoku_kit import link_codec
from sudoku_kit.link_codec import encode_link, read_puzzle
from sudoku_kit.step_prover import house, prove
from sudoku_kit.uniqueness import check_uniqueness

DOC = {"puzzle": {"title": "spec 73"}}


def test_every_kind_of_source_reads_to_one_document(monkeypatch, tmp_path):
    link = encode_link(DOC)
    payload = link.split("puzzle=", 1)[1]
    ShortLinkApp(monkeypatch, stored=payload)
    commented = tmp_path / "puzzle.txt"
    commented.write_text(f"# a comment line\n{link}\n")
    short = "https://sudokumaker.app/p/AbCdEfGhIj"
    for source in (commented, link, payload, short):
        assert read_puzzle(source) == DOC

    empty = tmp_path / "empty.txt"
    empty.write_text("\n")
    with pytest.raises(ValueError, match=r"empty\.txt holds no link"):
        read_puzzle(empty)


def test_uniqueness_answers_in_the_callers_keys_and_names_no_verdict():
    m = cp_model.CpModel()
    x = m.NewIntVar(2, 2, "x")
    y = m.NewBoolVar("y")
    by_name = check_uniqueness(m, {"x": x, "y": y})
    assert by_name.status == "not_unique"
    assert sorted([by_name.first, by_name.second], key=lambda s: s["y"]) == [
        {"x": 2, "y": 0},
        {"x": 2, "y": 1},
    ]
    assert isinstance(check_uniqueness(m, [x, y]).first, tuple)

    broken = cp_model.CpModel()
    assert check_uniqueness(broken, {"bad": broken.NewIntVar(5, 2, "bad")}).status == (
        "invalid"
    )

    slow = cp_model.CpModel()
    rng = random.Random(1)
    xs = [slow.NewBoolVar(f"x{i}") for i in range(60)]
    weights = [rng.randint(1, 1000) for _ in xs]
    slow.Add(sum(w * v for w, v in zip(weights, xs, strict=True)) == sum(weights) // 2)
    result = check_uniqueness(slow, dict(enumerate(xs)), time_limit=0.0)
    assert result.status == "timeout"
    assert not result.unique


def test_an_unknown_claim_is_refused_naming_the_three_kinds():
    a, b = (0, 0), (0, 1)
    with pytest.raises(ValueError, match="expected Chain, Place or Either"):
        prove({a: {1}, b: {2}}, {"pair": house([a, b])}, ["pair"], "A < B")


def test_shorten_stops_at_the_first_failure_after_printing_earlier_links(
    monkeypatch, tmp_path, capsys
):
    app = ShortLinkApp(monkeypatch)
    empty = tmp_path / "empty.txt"
    empty.write_text("\n")
    good = encode_link(DOC)
    assert link_codec.main(["shorten", good, str(empty), good]) == 1
    captured = capsys.readouterr()
    assert captured.out.splitlines() == ["https://sudokumaker.app/p/AbCdEfGhIj"]
    assert len(captured.err.splitlines()) == 1
    assert len(app.posts) == 1
    assert link_codec.main(["shorten", good]) == 0
