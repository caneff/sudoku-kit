"""The SudokuMaker link codec, on real links copied from the example link
files of sudokumaker-custom-constraints (`tests/links/`)."""

import json
from pathlib import Path

import pytest

from sudoku_kit import link_codec
from sudoku_kit.link_codec import decode_puzzle, encode_link, read_link

LINKS = Path(__file__).parent / "links"

# Each real link and the puzzle name and board width its document carries,
# read off the app's own export rather than derived here.
REAL_LINKS = [
    ("hit-counts-4x4.txt", "Hit Counts 4x4", 6),
    ("house-gac.txt", "Standalone House GAC", 9),
    ("fillomino.txt", "Fillomino", 9),
    ("isofill.txt", "ISOFILL", 10),
    ("dutch-flatmates.txt", "Dutch Flatmates", 9),
]


@pytest.mark.parametrize(("name", "puzzle_name", "width"), REAL_LINKS)
def test_a_real_link_decodes_to_its_document(name, puzzle_name, width):
    doc = decode_puzzle(read_link(str(LINKS / name)))
    assert doc["puzzle"]["name"] == puzzle_name
    assert doc["puzzle"]["width"] == width


@pytest.mark.parametrize("name", [name for name, _, _ in REAL_LINKS])
def test_a_real_link_survives_encode_then_decode(name):
    doc = decode_puzzle(read_link(str(LINKS / name)))
    link = encode_link(doc)
    assert link.startswith("https://sudokumaker.app/?puzzle=")
    assert decode_puzzle(link) == doc


def test_decode_reads_a_bare_payload_as_well_as_a_full_link():
    link = read_link(str(LINKS / "house-gac.txt"))
    payload = link.split("puzzle=")[1]
    assert decode_puzzle(payload) == decode_puzzle(link)


def test_read_link_accepts_a_file_or_the_link_itself(tmp_path):
    link = read_link(str(LINKS / "house-gac.txt"))
    assert link.startswith("https://sudokumaker.app/?puzzle=")
    # A real link is far longer than a file name may be; it is the link.
    assert read_link(link) == link
    assert read_link(f"  {link}\n") == link
    commented = tmp_path / "link.txt"
    commented.write_text(f"# the house-gac board\n{link}\n")
    assert read_link(str(commented)) == link


def test_encode_takes_tuples_where_the_document_holds_lists():
    # A builder writes cells as tuples; JSON has only lists, and the link
    # carries the JSON. That is not a lost field.
    link = encode_link({"puzzle": {"cells": [(0, 1), (2, 3)]}})
    assert decode_puzzle(link) == {"puzzle": {"cells": [[0, 1], [2, 3]]}}


def test_encode_refuses_a_document_whose_link_does_not_decode_back(monkeypatch):
    # No document reachable from JSON breaks the compression boundary today,
    # so the loss is injected there: the compressor answers with the link of
    # a different document.
    other = link_codec.LZString.compressToEncodedURIComponent(
        json.dumps({"puzzle": {}})
    )
    monkeypatch.setattr(
        link_codec.LZString, "compressToEncodedURIComponent", lambda _: other
    )
    with pytest.raises(ValueError, match="round-trip"):
        encode_link({"formatVersion": "1.5.0", "puzzle": {"width": 9}})
