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
    read_puzzle,
    shorten_link,
)

LINKS = Path(__file__).parent / "links"

# Read off the app's own export, not derived here.
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
    ],
)
def test_encode_refuses_a_document_json_cannot_carry(doc):
    with pytest.raises(ValueError, match="round-trip"):
        encode_link(doc)


@pytest.mark.parametrize(
    ("doc", "cause"),
    [
        ({"puzzle": {"width": float("inf")}}, "Out of range"),
        ({"puzzle": {"width": float("-inf")}}, "Out of range"),
        ({"puzzle": {"width": float("nan")}}, "Out of range"),
        ({"puzzle": {(1, 2): "a"}}, "not tuple"),
        ({"puzzle": {"cells": {1, 2}}}, "set"),
    ],
)
def test_encode_names_the_cause_of_a_document_json_cannot_carry(doc, cause):
    with pytest.raises(ValueError, match=rf"JSON cannot carry .*\(.*{cause}"):
        encode_link(doc)


def _nested(depth, wrap):
    doc = {}
    for _ in range(depth):
        doc = wrap(doc)
    return doc


@pytest.mark.parametrize(
    ("depth", "wrap"),
    [(500, lambda doc: {"a": doc}), (100_000, lambda doc: [doc])],
    ids=["too-deep-to-compare", "too-deep-for-json"],
)
def test_encode_refuses_a_document_nested_too_deep(depth, wrap):
    with pytest.raises(ValueError, match=r"too deep|cannot carry"):
        encode_link({"puzzle": _nested(depth, wrap)})


def test_encode_refuses_a_document_with_no_repr():
    with pytest.raises(ValueError, match=r"JSON cannot carry .*with no repr"):
        encode_link({"puzzle": 10**5000})


def test_the_round_trip_refusal_names_its_document(monkeypatch):
    other = link_codec.LZString.compressToEncodedURIComponent("{}")
    monkeypatch.setattr(
        link_codec.LZString, "compressToEncodedURIComponent", lambda _: other
    )
    doc = {"puzzle": {"title": "x" * 100}}
    with pytest.raises(ValueError, match="round-trip") as refusal:
        encode_link(doc)
    assert repr(doc)[:60] in str(refusal.value)
    assert repr(doc)[:61] not in str(refusal.value)


@pytest.mark.parametrize("value", [5, [1, 2], "x", None])
def test_decode_refuses_a_payload_that_is_not_an_object(value):
    with pytest.raises(ValueError, match="not a JSON object"):
        decode_puzzle(_d_payload(value))


def test_shorten_refuses_a_payload_that_is_not_an_object_before_any_request(
    monkeypatch,
):
    network = _Network(monkeypatch)
    with pytest.raises(ValueError, match="not a JSON object"):
        shorten_link(_d_payload(5))
    assert network.requests == []


@pytest.mark.parametrize("depth", [1_000, 100_000])
def test_decode_refuses_a_payload_nested_too_deep_for_json(monkeypatch, capsys, depth):
    link = _d_payload_of_text("[" * depth)
    assert len(link) < 200
    # Which error json raises for this depth varies by interpreter build
    # (RecursionError, or a plain parse error); every one is a refusal.
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        decode_puzzle(link)
    network = _Network(monkeypatch)
    assert link_codec.main(["shorten", link]) == 1
    assert network.requests == []
    captured = capsys.readouterr()
    assert captured.out == ""
    assert len(captured.err.splitlines()) == 1


@pytest.mark.parametrize("entry_point", [read_link, shorten_link])
def test_a_link_reader_names_a_file_that_is_not_utf8(
    monkeypatch, tmp_path, entry_point
):
    network = _Network(monkeypatch)
    bad = tmp_path / "link.txt"
    bad.write_bytes(b"\xff\xfe link")
    with pytest.raises(ValueError, match=r"link\.txt is not UTF-8"):
        entry_point(str(bad))
    assert network.requests == []


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


def test_a_d_link_round_trips_through_an_n_link():
    doc = decode_puzzle(read_link(D_LINK))
    n_link = encode_link(doc)
    assert n_link.split("puzzle=")[1].startswith("N")
    assert decode_puzzle(n_link) == doc


def _d_payload(doc):
    return _d_payload_of_text(json.dumps(doc))


def _d_payload_of_text(text):
    return _d_payload_of_deflate(zlib.compress(text.encode(), wbits=-zlib.MAX_WBITS))


def _d_payload_of_deflate(raw, *, pad=False):
    payload = base64.urlsafe_b64encode(raw).decode()
    return "D" + (payload if pad else payload.rstrip("="))


def _stored_d_payload(doc, *, pad):
    # Stored blocks keep the deflate length exactly what the text makes it.
    deflate = zlib.compressobj(0, wbits=-zlib.MAX_WBITS)
    raw = deflate.compress(json.dumps(doc).encode()) + deflate.flush()
    return _d_payload_of_deflate(raw, pad=pad)


# Unpadded, these bodies run 0, 2 and 3 mod 4 long on zlib 1.3.1, which
# asks for 0, 2 and 1 characters of padding.
@pytest.mark.parametrize(
    "extra", ["", "a", "ab"], ids=["no-padding", "two-padding", "one-padding"]
)
def test_a_d_payload_decodes_whatever_its_unpadded_length(extra):
    doc = {"puzzle": {"name": "p" + extra}}
    assert decode_puzzle(_stored_d_payload(doc, pad=False)) == doc
    assert decode_puzzle(_stored_d_payload(doc, pad=True)) == doc


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


def test_read_link_does_not_ask_the_api_as_urllib(monkeypatch):
    network = _Network(monkeypatch, body=_answer("Dx"))
    read_link("https://sudokumaker.app/p/abc123")
    agent = network.requests[0].get_header("User-agent")
    assert agent and not agent.startswith("Python-urllib")


def test_read_link_gives_the_api_a_timeout(monkeypatch):
    network = _Network(monkeypatch, body=_answer("Dx"))
    read_link("https://sudokumaker.app/p/abc123")
    assert network.timeouts == [link_codec.FETCH_TIMEOUT_SECONDS]


def test_a_deeply_nested_answer_is_a_refusal_not_a_crash(monkeypatch, capsys):
    _Network(monkeypatch, body=b"[" * 100_000)
    with pytest.raises(ValueError, match="answered no puzzle payload"):
        read_link("https://sudokumaker.app/p/abc123")
    assert link_codec.main(["shorten", "https://sudokumaker.app/p/abc123"]) == 1
    assert len(capsys.readouterr().err.splitlines()) == 1


def test_an_escaped_marker_is_refused_for_what_it_is():
    with pytest.raises(ValueError, match="payload holds a puzzle="):
        decode_puzzle("https://sudokumaker.app/?puzzle%3DN4Ig")


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


@pytest.mark.parametrize(
    "short",
    [
        "http://sudokumaker.app/p/KkFHGqdkjd",
        "https://www.sudokumaker.app/p/KkFHGqdkjd",
        "https://sudokumaker.app/p/KkFHGqdkjd/",
        "https://sudokumaker.app/p/KkFHGqdkjd?utm=x",
    ],
)
def test_shorten_normalizes_a_short_link_once_it_resolves(monkeypatch, short):
    _ShortLinkApp(monkeypatch, stored="Dx")
    assert shorten_link(short) == "https://sudokumaker.app/p/KkFHGqdkjd"


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

    def unreadable(self, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(link_codec.Path, "read_text", unreadable)
    assert link_codec.main(["shorten", str(LINKS / "fillomino.txt")]) == 1
    assert "Permission denied" in capsys.readouterr().err


def test_a_doubled_puzzle_marker_is_refused_before_any_request(monkeypatch):
    app = _ShortLinkApp(monkeypatch, minted=AssertionError("network used"))
    link = read_link(LINKS / "fillomino.txt")
    doubled = link + "puzzle=" + link.split("puzzle=")[1]
    with pytest.raises(ValueError, match="puzzle="):
        decode_puzzle(doubled)
    with pytest.raises(ValueError, match="puzzle="):
        shorten_link(doubled)
    assert app.posts == [] and app.gets == []


def test_a_file_holding_another_files_path_reads_the_same_in_both(
    monkeypatch, tmp_path
):
    app = _ShortLinkApp(monkeypatch, minted=AssertionError("network used"))
    inner = tmp_path / "inner.txt"
    inner.write_text(read_link(LINKS / "fillomino.txt"))
    outer = tmp_path / "outer.txt"
    outer.write_text(f"{inner}\n")
    assert read_link(outer) == str(inner)
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        shorten_link(outer)
    assert app.posts == [] and app.gets == []


def test_the_size_cap_measures_the_unescaped_payload(monkeypatch):
    app = _ShortLinkApp(monkeypatch)
    link = read_link(LINKS / "fillomino.txt")
    payload = link.split("puzzle=")[1]
    assert "+" in payload
    monkeypatch.setattr(link_codec, "MAX_PAYLOAD_CHARACTERS", len(payload))
    shorten_link(link.replace("+", "%2B"))
    assert len(app.posts) == 1


def test_read_puzzle_reads_a_file_a_commented_file_a_link_and_a_payload(tmp_path):
    link = read_link(str(LINKS / "house-gac.txt"))
    expected = decode_puzzle(link)
    commented = tmp_path / "commented.txt"
    commented.write_text(f"# the puzzle\n{link}\n")
    payload = link.split("puzzle=")[1]
    for source in (str(LINKS / "house-gac.txt"), commented, link, payload):
        assert read_puzzle(source) == expected


def test_read_puzzle_resolves_a_short_link(monkeypatch):
    d_link = read_link(D_LINK)
    payload = d_link.split("puzzle=")[1]
    network = _Network(monkeypatch, body=_answer(payload))
    doc = read_puzzle("https://sudokumaker.app/p/bWgLDdqJLQ")
    assert network.urls == ["https://sudokumaker.app/api/puzzles/bWgLDdqJLQ"]
    assert doc == decode_puzzle(d_link)


def test_read_puzzle_names_an_empty_file(tmp_path):
    empty = tmp_path / "link.txt"
    empty.write_text("\n")
    with pytest.raises(ValueError, match=r"link\.txt holds no link"):
        read_puzzle(empty)


def test_read_puzzle_names_a_non_utf8_file(tmp_path):
    binary = tmp_path / "link.bin"
    binary.write_bytes(b"\xff\xfe\x00")
    with pytest.raises(ValueError, match=r"link\.bin is not UTF-8 text"):
        read_puzzle(binary)


def test_read_puzzle_names_what_is_not_a_link():
    with pytest.raises(ValueError, match="not a SudokuMaker link"):
        read_puzzle("examples/no-such/PUZZLE_LINK.txt")
