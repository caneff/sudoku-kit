"""Spec #57 end to end: one reading of a link for the checks and the upload,
every link refusal a ValueError naming its input, and one list of negations
for every claim, read off the public functions.

Blind to: the consumers. grid-hunts and sudokumaker-custom-constraints each
lock a commit in `uv.lock`, so none of this runs against their code until one
moves its lock, and both still pin `tag = "v0.1.0"`. Blind to the live app too:
the upload runs against a fake, as the spec rules. Also blind to the spec's
static and docs criteria, checked by reading the diff: the private `Step`
shape (#61), the renames beyond `eliminations` (#62), the test audit (#63), and
the docs and CI (#64).
"""

import json

import pytest
from link_helpers import ShortLinkApp, d_payload_of_text

from sudoku_kit import link_codec
from sudoku_kit.link_codec import decode_puzzle, encode_link, read_link, shorten_link
from sudoku_kit.step_prover import Chain, Either, Place, house, propagation, prove

A, B = (0, 0), (0, 1)
REGISTRY = {"pair": house([A, B])}


def test_the_checks_and_the_upload_read_one_payload(monkeypatch, tmp_path):
    app = ShortLinkApp(monkeypatch)
    doc = {"puzzle": {"title": "spec 57"}}
    link = encode_link(doc)

    assert decode_puzzle(link) == doc
    assert shorten_link(link) == "https://sudokumaker.app/p/AbCdEfGhIj"
    assert json.loads(app.posts[0].data) == {"puzzle": link.split("puzzle=", 1)[1]}

    doubled = f"{link}&puzzle={link.split('puzzle=', 1)[1]}"
    holder = tmp_path / "holder.txt"
    holder.write_text(f"{tmp_path / 'other.txt'}\n")
    (tmp_path / "other.txt").write_text(f"{link}\n")
    app.posts.clear()
    with pytest.raises(ValueError, match=r"holds a puzzle="):
        shorten_link(doubled)
    with pytest.raises(ValueError, match="unknown format prefix"):
        shorten_link(holder)
    assert app.posts == []
    assert read_link(holder) == str(tmp_path / "other.txt")


def test_every_link_refusal_is_a_value_error(monkeypatch, tmp_path, capsys):
    app = ShortLinkApp(monkeypatch)
    with pytest.raises(ValueError, match="JSON cannot carry"):
        encode_link({"puzzle": {"width": float("inf")}})
    with pytest.raises(ValueError, match="not a JSON object"):
        shorten_link(d_payload_of_text("5"))
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        shorten_link(d_payload_of_text("[" * 1_000))
    binary = tmp_path / "binary.txt"
    binary.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match=r"binary\.txt"):
        read_link(binary)
    assert link_codec.main(["shorten", str(binary)]) == 1
    assert len(capsys.readouterr().err.splitlines()) == 1
    assert app.posts == []


@pytest.mark.parametrize(
    "claim", [Chain((A, B)), Either(({A: 1, B: 2},))], ids=["chain", "either"]
)
def test_a_one_solve_claim_propagates_its_negation_first(claim):
    candidates = {A: {1}, B: {2}}
    assert prove(candidates, REGISTRY, ["pair"], claim).status == "proved"
    result = propagation(candidates, REGISTRY, ["pair"], claim)
    assert result.proves
    assert result.eliminations[0].by == "negated claim"


def test_a_place_runs_its_negation_once_per_removed_digit():
    candidates = {A: {1, 2}, B: {2}}
    claim = Place(A, [1])
    assert prove(candidates, REGISTRY, ["pair"], claim).status == "proved"
    result = propagation(candidates, REGISTRY, ["pair"], claim)
    assert result.proves
    assert result.eliminations[0] == ("negated claim", A, (1,))


def test_a_place_with_nothing_to_remove_logs_no_negated_claim():
    claim = Place(A, [1])
    result = propagation({A: {1}, B: {2}}, REGISTRY, ["pair"], claim)
    assert result.proves
    assert result.eliminations == ()
