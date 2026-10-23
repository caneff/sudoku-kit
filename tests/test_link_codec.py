import base64
import http.client
import io
import json
import random
import string
import urllib.error
import zlib
from pathlib import Path

import pytest

from sudoku_kit import link_codec
from sudoku_kit.link_codec import (
    decode_puzzle,
    encode_link,
    read_link,
    shorten_link,
)

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


class _ShortLinkApp:
    """The app's two endpoints: POST /api/puzzles mints, GET /api/puzzles/<id> reads."""

    def __init__(self, monkeypatch, *, minted=b'{"id": "AbCdEfGhIj"}', stored=None):
        self.posts, self.gets = [], []
        self._minted, self._stored = minted, stored
        monkeypatch.setattr(link_codec.urllib.request, "urlopen", self)

    def __call__(self, request, timeout=None):
        if request.data is None:
            self.gets.append(request)
            stored = self._stored
            if stored is None:
                stored = json.loads(self.posts[-1].data)["puzzle"]
            return io.BytesIO(_answer(stored))
        self.posts.append(request)
        if isinstance(self._minted, Exception):
            raise self._minted
        return io.BytesIO(self._minted)


@pytest.mark.parametrize(("name", "puzzle_name", "width"), REAL_LINKS)
def test_shorten_posts_the_raw_payload_and_returns_the_short_link(
    monkeypatch, name, puzzle_name, width
):
    app = _ShortLinkApp(monkeypatch)
    link = read_link(LINKS / name)
    assert shorten_link(LINKS / name) == "https://sudokumaker.app/p/AbCdEfGhIj"
    assert [post.full_url for post in app.posts] == [
        "https://sudokumaker.app/api/puzzles"
    ]
    # The payload goes up as it stands in the link: its `+` is not a space.
    assert json.loads(app.posts[0].data) == {"puzzle": link.split("puzzle=")[1]}
    assert [get.full_url for get in app.gets] == [
        "https://sudokumaker.app/api/puzzles/AbCdEfGhIj"
    ]


def test_shorten_takes_the_link_itself(monkeypatch):
    _ShortLinkApp(monkeypatch)
    link = read_link(LINKS / "fillomino.txt")
    assert shorten_link(link) == "https://sudokumaker.app/p/AbCdEfGhIj"


def test_shorten_posts_json_with_the_headers_the_cdn_wants(monkeypatch):
    app = _ShortLinkApp(monkeypatch)
    shorten_link(LINKS / "fillomino.txt")
    post = app.posts[0]
    assert post.get_header("Content-type") == "application/json"
    assert post.get_header("Origin") == "https://sudokumaker.app"
    assert post.get_header("Referer").startswith("https://sudokumaker.app/")
    assert post.get_header("User-agent").startswith("Mozilla/")


def test_shorten_refuses_when_the_minted_link_holds_another_payload(monkeypatch):
    _ShortLinkApp(monkeypatch, stored="Dother")
    with pytest.raises(ValueError, match=r"AbCdEfGhIj.*not the payload"):
        shorten_link(LINKS / "fillomino.txt")


def test_shorten_refuses_a_payload_the_app_would_refuse(monkeypatch):
    app = _ShortLinkApp(monkeypatch)
    noise = random.Random(0).choices(string.ascii_letters + string.digits, k=300_000)
    link = encode_link({"notes": "".join(noise)})
    assert len(link.split("puzzle=")[1]) > link_codec.MAX_PAYLOAD_CHARACTERS
    with pytest.raises(ValueError, match="200000"):
        shorten_link(link)
    assert app.posts == []


def test_shorten_accepts_a_payload_of_exactly_the_limit(monkeypatch):
    app = _ShortLinkApp(monkeypatch)
    link = read_link(LINKS / "fillomino.txt")
    limit = len(link.split("puzzle=")[1])
    monkeypatch.setattr(link_codec, "MAX_PAYLOAD_CHARACTERS", limit)
    shorten_link(link)
    assert len(app.posts) == 1
    monkeypatch.setattr(link_codec, "MAX_PAYLOAD_CHARACTERS", limit - 1)
    with pytest.raises(ValueError, match=str(limit - 1)):
        shorten_link(link)
    assert len(app.posts) == 1


@pytest.mark.parametrize("tail", ["&x=1", "#frag", "%0A"])
def test_shorten_refuses_a_link_whose_payload_is_not_clean(monkeypatch, tail):
    app = _ShortLinkApp(monkeypatch)
    with pytest.raises(ValueError, match="payload"):
        shorten_link(read_link(LINKS / "fillomino.txt") + tail)
    assert app.posts == []


def test_shorten_sends_a_percent_encoded_plus_as_a_plus(monkeypatch):
    app = _ShortLinkApp(monkeypatch)
    link = read_link(LINKS / "fillomino.txt")
    assert "+" in link
    shorten_link(link.replace("+", "%2B"))
    assert json.loads(app.posts[0].data) == {"puzzle": link.split("puzzle=")[1]}


def test_shorten_leaves_a_short_link_as_it_is(monkeypatch, tmp_path):
    app = _ShortLinkApp(
        monkeypatch, stored=read_link(LINKS / "fillomino.txt").split("puzzle=")[1]
    )
    saved = tmp_path / "short.txt"
    saved.write_text("https://sudokumaker.app/p/KkFHGqdkjd\n")
    assert shorten_link(saved) == "https://sudokumaker.app/p/KkFHGqdkjd"
    assert shorten_link("https://sudokumaker.app/p/KkFHGqdkjd") == (
        "https://sudokumaker.app/p/KkFHGqdkjd"
    )
    assert app.posts == []


def test_shorten_errors_name_the_link_being_shortened(monkeypatch):
    error = urllib.error.HTTPError("u", 403, "Forbidden", {}, None)
    _ShortLinkApp(monkeypatch, minted=error)
    link = read_link(LINKS / "fillomino.txt")
    with pytest.raises(ValueError, match="403 Forbidden") as raised:
        shorten_link(link)
    assert link[:60] in str(raised.value)


def test_shorten_refuses_what_is_not_a_link_before_the_network(monkeypatch):
    app = _ShortLinkApp(monkeypatch, minted=AssertionError("network used"))
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        shorten_link("no-such-file.txt")
    assert app.posts == []


@pytest.mark.parametrize(
    "minted", [b'{"id": ""}', b'{"id": 5}', b'{"id": "a/b"}', b"[]", b"no"]
)
def test_shorten_names_an_answer_with_no_usable_id(monkeypatch, minted):
    _ShortLinkApp(monkeypatch, minted=minted)
    with pytest.raises(ValueError, match="no usable id"):
        shorten_link(LINKS / "fillomino.txt")


def test_shorten_names_the_status_the_app_refused_with(monkeypatch):
    error = urllib.error.HTTPError("u", 400, "invalid_request", {}, None)
    _ShortLinkApp(monkeypatch, minted=error)
    with pytest.raises(ValueError, match=r"answered 400 invalid_request"):
        shorten_link(LINKS / "fillomino.txt")


def test_shorten_raises_timeout_error_when_the_post_times_out(monkeypatch):
    _ShortLinkApp(monkeypatch, minted=TimeoutError())
    with pytest.raises(TimeoutError, match="timed out"):
        shorten_link(LINKS / "fillomino.txt")


def test_the_shorten_command_prints_each_short_link_bare(monkeypatch, capsys):
    _ShortLinkApp(monkeypatch)
    sources = [str(LINKS / "fillomino.txt"), str(LINKS / "isofill.txt")]
    assert link_codec.main(["shorten", *sources]) == 0
    out = capsys.readouterr().out
    assert out == "https://sudokumaker.app/p/AbCdEfGhIj\n" * 2


def test_the_shorten_command_reports_a_refusal_and_fails(monkeypatch, capsys):
    _ShortLinkApp(monkeypatch, minted=AssertionError("network used"))
    assert link_codec.main(["shorten", "no-such-file.txt"]) == 1
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "not a SudokuMaker link" in captured.err


def test_the_shorten_command_stops_at_the_first_refusal(monkeypatch, capsys):
    app = _ShortLinkApp(monkeypatch)
    fillomino = str(LINKS / "fillomino.txt")
    assert link_codec.main(["shorten", fillomino, "no-such-file.txt", fillomino]) == 1
    captured = capsys.readouterr()
    assert captured.out == "https://sudokumaker.app/p/AbCdEfGhIj\n"
    assert "no-such-file.txt" in captured.err
    assert len(app.posts) == 1


def test_the_shorten_command_reports_a_file_it_cannot_read(monkeypatch, capsys):
    _ShortLinkApp(monkeypatch)

    def unreadable(self):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(link_codec.Path, "read_text", unreadable)
    assert link_codec.main(["shorten", str(LINKS / "fillomino.txt")]) == 1
    assert "Permission denied" in capsys.readouterr().err
