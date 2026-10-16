"""The SudokuMaker link codec, on real links copied from the example link
files of sudokumaker-custom-constraints (`tests/links/`)."""

import io
import json
import urllib.error
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


@pytest.mark.parametrize(
    "doc",
    [
        # An int key comes back as the string "1".
        {"puzzle": {1: "a"}},
        # Two keys JSON writes alike: one field is lost outright.
        {"puzzle": {1: "a", "1": "b"}},
        # NaN is not JSON, and comes back unequal to itself.
        {"puzzle": {"width": float("nan")}},
    ],
)
def test_encode_refuses_a_document_json_cannot_carry(doc):
    with pytest.raises(ValueError, match="round-trip"):
        encode_link(doc)


def test_read_link_takes_a_path_object(tmp_path):
    link = read_link(str(LINKS / "house-gac.txt"))
    assert read_link(LINKS / "house-gac.txt") == link


def test_read_link_names_an_empty_file(tmp_path):
    empty = tmp_path / "link.txt"
    empty.write_text("\n")
    with pytest.raises(ValueError, match=r"link\.txt holds no link"):
        read_link(str(empty))


@pytest.mark.parametrize("source", ["examples/no-such/PUZZLE_LINK.txt", "", "N4Ig"])
def test_decode_names_what_is_not_a_link(source):
    # A mistyped path is not a file, so read_link hands it on as the link.
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        decode_puzzle(read_link(source))


# A real `D` link (base64url of deflate-raw JSON) fetched from
# https://sudokumaker.app/api/puzzles/bWgLDdqJLQ on 2026-10-16, and the
# document a stock zlib inflate of its payload gives.
D_LINK = LINKS / "numbered-rooms-6x6.txt"
D_DOC = LINKS / "numbered-rooms-6x6.json"


def test_a_d_link_decodes_to_its_document():
    expected = json.loads(D_DOC.read_text())
    assert decode_puzzle(read_link(D_LINK)) == expected
    assert expected["formatVersion"] == "1.6.0"


def test_a_d_payload_decodes_without_its_link_prefix():
    link = read_link(D_LINK)
    assert decode_puzzle(link.split("puzzle=")[1]) == decode_puzzle(link)


def test_a_d_link_round_trips_through_an_n_link():
    doc = decode_puzzle(read_link(D_LINK))
    n_link = encode_link(doc)
    assert n_link.split("puzzle=")[1].startswith("N")
    assert decode_puzzle(n_link) == doc


@pytest.mark.parametrize("payload", ["Xabc", "d3Vpt", "D", "D!!not-base64!!", "DAAAA"])
def test_decode_names_a_payload_it_cannot_read(payload):
    with pytest.raises(ValueError, match="not a SudokuMaker link") as error:
        decode_puzzle(f"https://sudokumaker.app/?puzzle={payload}")
    assert payload[:1] in str(error.value)


def test_decode_names_an_unknown_prefix():
    with pytest.raises(ValueError, match="unknown format prefix 'X'"):
        decode_puzzle("Xabc")


class _Response(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _serve(monkeypatch, body=None, error=None):
    """Replace the network: record the requested URL, answer `body` or raise."""
    asked = []

    def fake_urlopen(url, timeout=None):
        asked.append(url)
        if error:
            raise error
        return _Response(body)

    monkeypatch.setattr(link_codec.urllib.request, "urlopen", fake_urlopen)
    return asked


def test_read_link_resolves_a_short_link(monkeypatch):
    d_link = read_link(D_LINK)
    payload = d_link.split("puzzle=")[1]
    asked = _serve(monkeypatch, body=json.dumps({"puzzle": payload}).encode())
    link = read_link("https://sudokumaker.app/p/bWgLDdqJLQ")
    assert asked == ["https://sudokumaker.app/api/puzzles/bWgLDdqJLQ"]
    assert decode_puzzle(link) == decode_puzzle(d_link)


def test_read_link_names_a_short_link_with_no_puzzle(monkeypatch):
    _serve(
        monkeypatch,
        error=urllib.error.HTTPError("u", 404, "Not Found", {}, None),
    )
    with pytest.raises(ValueError, match="no-such-id"):
        read_link("https://sudokumaker.app/p/no-such-id")


def test_read_link_names_a_short_link_it_could_not_reach(monkeypatch):
    _serve(monkeypatch, error=urllib.error.URLError("offline"))
    with pytest.raises(ValueError, match=r"abc123.*offline"):
        read_link("https://sudokumaker.app/p/abc123")


def test_read_link_names_a_short_link_answer_with_no_payload(monkeypatch):
    _serve(monkeypatch, body=b'{"error": "gone"}')
    with pytest.raises(ValueError, match="abc123"):
        read_link("https://sudokumaker.app/p/abc123")


def test_read_link_does_not_touch_the_network_for_a_full_link(monkeypatch):
    asked = _serve(monkeypatch, error=AssertionError("network used"))
    link = read_link(LINKS / "house-gac.txt")
    assert read_link(link) == link
    assert asked == []
