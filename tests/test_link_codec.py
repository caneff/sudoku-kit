import base64
import http.client
import io
import json
import urllib.error
import zlib
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
    assert read_link(link) == link
    assert read_link(f"  {link}\n") == link
    commented = tmp_path / "link.txt"
    commented.write_text(f"# the house-gac board\n{link}\n")
    assert read_link(str(commented)) == link


def test_encode_takes_tuples_where_the_document_holds_lists():
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
        {"puzzle": {1: "a"}},
        {"puzzle": {1: "a", "1": "b"}},
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


def test_a_d_link_round_trips_through_an_n_link():
    doc = decode_puzzle(read_link(D_LINK))
    n_link = encode_link(doc)
    assert n_link.split("puzzle=")[1].startswith("N")
    assert decode_puzzle(n_link) == doc


def _d_payload(doc, *, pad=False):
    raw = zlib.compress(json.dumps(doc).encode(), wbits=-zlib.MAX_WBITS)
    payload = base64.urlsafe_b64encode(raw).decode()
    return "D" + (payload if pad else payload.rstrip("="))


PADDING_EXTRAS = ["", "a", "ab", "abc"]


@pytest.mark.parametrize("extra", PADDING_EXTRAS)
def test_a_d_payload_decodes_whatever_its_unpadded_length(extra):
    doc = {"puzzle": {"name": "p" + extra}}
    assert decode_puzzle(_d_payload(doc)) == doc
    assert decode_puzzle(_d_payload(doc, pad=True)) == doc


def test_the_unpadded_d_payloads_meet_every_padding_amount():
    # An unpadded base64 body is 0, 2 or 3 mod 4 long (1 cannot occur), which
    # asks for 0, 2 or 1 characters of padding.
    lengths = {
        len(_d_payload({"puzzle": {"name": "p" + extra}})[1:]) % 4
        for extra in PADDING_EXTRAS
    }
    assert lengths == {0, 2, 3}


@pytest.mark.parametrize("prefix", ["X", "d", "h"])
def test_decode_names_an_unknown_prefix(prefix):
    with pytest.raises(ValueError, match=f"unknown format prefix '{prefix}'"):
        decode_puzzle(f"https://sudokumaker.app/?puzzle={prefix}3Vpt")


_GOOD = _d_payload({"puzzle": {}})
_WITH_JUNK = zlib.compress(b'{"puzzle": {}}', wbits=-zlib.MAX_WBITS) + b"junk"


@pytest.mark.parametrize(
    "payload",
    [
        "D",
        "D!!not-base64!!",
        "DAAAA",
        _GOOD[:5] + "*" + _GOOD[5:],
        "D" + base64.urlsafe_b64encode(_WITH_JUNK).decode().rstrip("="),
    ],
)
def test_decode_refuses_a_d_payload_that_is_not_one_clean_deflate_stream(payload):
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        decode_puzzle(f"https://sudokumaker.app/?puzzle={payload}")


class _Network:
    def __init__(self, monkeypatch, body=None, error=None):
        self.requests = []
        self.timeouts = []
        self._body, self._error = body, error
        monkeypatch.setattr(link_codec.urllib.request, "urlopen", self)

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if self._error:
            raise self._error
        return io.BytesIO(self._body)

    @property
    def urls(self):
        return [request.full_url for request in self.requests]


def _answer(puzzle):
    return json.dumps({"puzzle": puzzle}).encode()


def test_read_link_resolves_a_short_link(monkeypatch):
    d_link = read_link(D_LINK)
    payload = d_link.split("puzzle=")[1]
    network = _Network(monkeypatch, body=_answer(payload))
    link = read_link("https://sudokumaker.app/p/bWgLDdqJLQ")
    assert network.urls == ["https://sudokumaker.app/api/puzzles/bWgLDdqJLQ"]
    assert link == "https://sudokumaker.app/?puzzle=" + payload
    assert decode_puzzle(link) == decode_puzzle(d_link)


def test_read_link_asks_the_api_as_sudoku_kit_not_as_urllib(monkeypatch):
    network = _Network(monkeypatch, body=_answer("Dx"))
    read_link("https://sudokumaker.app/p/abc123")
    assert network.requests[0].get_header("User-agent") == "sudoku-kit"
    assert network.timeouts == [link_codec.FETCH_TIMEOUT_SECONDS]


def test_read_link_resolves_a_short_link_held_in_a_file(monkeypatch, tmp_path):
    network = _Network(monkeypatch, body=_answer("Dx"))
    saved = tmp_path / "link.txt"
    saved.write_text("# Renbanana\nhttps://sudokumaker.app/p/KkFHGqdkjd\n")
    assert read_link(saved) == "https://sudokumaker.app/?puzzle=Dx"
    assert network.urls == ["https://sudokumaker.app/api/puzzles/KkFHGqdkjd"]


@pytest.mark.parametrize(
    "short",
    [
        "http://sudokumaker.app/p/abc123",
        "https://www.sudokumaker.app/p/abc123/",
        "https://sudokumaker.app/p/abc123?utm=x",
    ],
)
def test_read_link_resolves_the_other_spellings_of_a_short_link(monkeypatch, short):
    network = _Network(monkeypatch, body=_answer("Dx"))
    assert read_link(short) == "https://sudokumaker.app/?puzzle=Dx"
    assert network.urls == ["https://sudokumaker.app/api/puzzles/abc123"]


def test_read_link_resolves_a_dev_short_link_on_the_dev_host(monkeypatch):
    network = _Network(monkeypatch, body=_answer("Dx"))
    read_link("https://dev.sudokumaker.app/p/abc123")
    assert network.urls == ["https://dev.sudokumaker.app/api/puzzles/abc123"]


@pytest.mark.parametrize(
    "short",
    [
        "https://sudokumaker.app/p/",
        "https://sudokumaker.app/p/?x=1",
        "https://sudokumaker.app/p/a%20b",
    ],
)
def test_read_link_names_a_short_link_with_no_usable_id(monkeypatch, short):
    network = _Network(monkeypatch, error=AssertionError("network used"))
    with pytest.raises(ValueError, match="no usable id") as error:
        read_link(short)
    assert short in str(error.value)
    assert network.urls == []


def test_read_link_names_a_short_link_the_app_does_not_know(monkeypatch):
    _Network(
        monkeypatch,
        error=urllib.error.HTTPError("u", 404, "Not Found", {}, None),
    )
    with pytest.raises(ValueError, match=r"no-such-id.*answered 404 Not Found"):
        read_link("https://sudokumaker.app/p/no-such-id")


def test_read_link_names_a_short_link_it_could_not_reach(monkeypatch):
    _Network(monkeypatch, error=urllib.error.URLError("offline"))
    with pytest.raises(ValueError, match=r"abc123.*offline"):
        read_link("https://sudokumaker.app/p/abc123")


@pytest.mark.parametrize(
    "error",
    [
        ConnectionResetError("reset by peer"),
        http.client.RemoteDisconnected("closed"),
        http.client.IncompleteRead(b"par", 10),
    ],
)
def test_read_link_names_a_short_link_whose_answer_broke_off(monkeypatch, error):
    _Network(monkeypatch, error=error)
    with pytest.raises(ValueError, match=r"abc123.*could not be read"):
        read_link("https://sudokumaker.app/p/abc123")


@pytest.mark.parametrize(
    "error", [TimeoutError("slow"), urllib.error.URLError(TimeoutError("slow"))]
)
def test_read_link_raises_timeout_error_when_the_request_times_out(monkeypatch, error):
    _Network(monkeypatch, error=error)
    with pytest.raises(TimeoutError, match="abc123"):
        read_link("https://sudokumaker.app/p/abc123")


@pytest.mark.parametrize(
    "body",
    [
        b'{"error": "gone"}',
        b"not json",
        b'{"puzzle": ""}',
        b'{"puzzle": 5}',
        b'{"puzzle": null}',
        b"[]",
    ],
)
def test_read_link_names_a_short_link_answer_with_no_payload(monkeypatch, body):
    _Network(monkeypatch, body=body)
    with pytest.raises(ValueError, match=r"abc123.*no puzzle payload"):
        read_link("https://sudokumaker.app/p/abc123")


def test_read_link_does_not_touch_the_network_for_a_full_link(monkeypatch):
    network = _Network(monkeypatch, error=AssertionError("network used"))
    link = read_link(LINKS / "house-gac.txt")
    assert read_link(link) == link
    assert network.urls == []
