"""The SudokuPad link reader: every link form decodes to the puzzle JSON that
sudokupad-art's codec produced for the same link (`tests/sudokupad/*.json`, one
golden per fixture link, copied from there once)."""

import contextlib
import hashlib
import io
import json
import shutil
import subprocess
from pathlib import Path

import pytest
from lzstring import LZString

from sudoku_kit import sudokupad_codec

FIXTURES = Path(__file__).parent / "sudokupad"
HAR = Path(sudokupad_codec.default_har())
needs_node = pytest.mark.skipif(not shutil.which("node"), reason="node not installed")
needs_app = pytest.mark.skipif(
    not shutil.which("node") or not HAR.exists(),
    reason="node, or the recording of SudokuPad's app, is missing",
)
GOLDEN = ["scl-with-solution", "ctc-link", "fpuz-link", "compact-position-sums"]
# The forms that need no loader: SudokuPad's own scl body is plain JSON.
PLAIN = {"lines": [{"color": "#000f", "thickness": 1, "d": "M0 0 L1 1"}]}


def link(name):
    return (FIXTURES / f"{name}.txt").read_text().strip()


def golden(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def scl(puzzle):
    return "scl" + LZString().compressToBase64(
        json.dumps(puzzle, separators=(",", ":"))
    )


def serve(monkeypatch, payload):
    seen = []

    def fake(url, timeout=None):
        seen.append((url, timeout))
        return contextlib.closing(io.BytesIO(payload.encode()))

    monkeypatch.setattr("urllib.request.urlopen", fake)
    return seen


def test_a_scl_link_with_a_stored_solution_decodes_without_node(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("node was started")

    monkeypatch.setattr(subprocess, "run", refuse)
    want = golden("scl-with-solution")

    got = sudokupad_codec.decode(link("scl-with-solution"), "src")

    assert got == (want["puzzle"], want["form"])
    assert got.puzzle["metadata"]["solution"].startswith("6712")


@needs_app
@pytest.mark.parametrize("name", GOLDEN)
def test_every_fixture_link_decodes_to_its_golden_json(name):
    want = golden(name)

    got = sudokupad_codec.decode(link(name), name)

    assert got.puzzle == want["puzzle"] and got.form == want["form"]


@needs_app
@pytest.mark.parametrize("name", GOLDEN)
def test_read_puzzle_takes_a_url_a_query_url_a_bare_string_and_a_file(name, tmp_path):
    want = golden(name)["puzzle"]
    text = link(name)
    (tmp_path / "p.scl.txt").write_text(text + "\n")
    (tmp_path / "p.txt").write_text(text + "\n")
    (tmp_path / "p.scl").write_text(text + "\n")

    for source in (
        text,
        f"https://sudokupad.app/{text}",
        f"https://sudokupad.app/?puzzle={text}",
        str(tmp_path / "p.scl.txt"),
        str(tmp_path / "p.txt"),
        str(tmp_path / "p.scl"),
    ):
        assert sudokupad_codec.read_puzzle(source) == want, source


@pytest.mark.parametrize(
    "src, token",
    [
        ("AbC123xyZ", "AbC123xyZ"),
        ("og8j5c3tiw/", "og8j5c3tiw"),
        ("a_b-c9", "a_b-c9"),
        ("https://sudokupad.app/AbC123xyZ", "AbC123xyZ"),
        ("https://www.sudokupad.app/some/path/og8j5c3tiw", "og8j5c3tiw"),
        ("https://sudokupad.app/og8j5c3tiw?setting-nogrid=true", "og8j5c3tiw"),
    ],
)
def test_a_short_link_is_resolved_with_one_get_of_the_api(monkeypatch, src, token):
    seen = serve(monkeypatch, scl(PLAIN))

    assert sudokupad_codec.read_puzzle(src) == PLAIN
    assert seen == [
        (
            f"https://sudokupad.app/api/puzzle/{token}",
            sudokupad_codec.FETCH_TIMEOUT_SECONDS,
        )
    ]


def test_a_stored_short_link_payload_with_a_solution_reads_back_whole(monkeypatch):
    puzzle = golden("scl-with-solution")["puzzle"]
    serve(monkeypatch, scl(puzzle))

    assert sudokupad_codec.read_puzzle("og8j5c3tiw") == puzzle


def test_an_api_payload_that_is_not_scl_names_the_id(monkeypatch):
    serve(monkeypatch, "<html>nope</html>")

    with pytest.raises(ValueError, match="og8j5c3tiw"):
        sudokupad_codec.read_puzzle("og8j5c3tiw")


def test_an_encoded_link_never_fetches(monkeypatch):
    def refuse(*a, **k):
        raise AssertionError("fetched")

    monkeypatch.setattr("urllib.request.urlopen", refuse)

    assert (
        sudokupad_codec.read_puzzle(f"https://sudokupad.app/?puzzle={scl(PLAIN)}")
        == PLAIN
    )


def test_a_scl_query_url_keeps_a_plus_in_its_base64():
    puzzle = next(
        p
        for p in ({"lines": [{"d": f"M0 0 L{i} 1"}]} for i in range(200))
        if "+" in scl(p)
    )

    assert (
        sudokupad_codec.read_puzzle(f"https://sudokupad.app/?puzzle={scl(puzzle)}")
        == puzzle
    )


def test_a_foreign_host_is_refused_without_a_fetch(monkeypatch):
    seen = serve(monkeypatch, scl(PLAIN))

    with pytest.raises(ValueError, match=r"evil\.example"):
        sudokupad_codec.read_puzzle("https://evil.example/og8j5c3tiw")
    assert seen == []


def test_a_form_that_is_no_id_is_refused_naming_it():
    with pytest.raises(ValueError, match="not a link"):
        sudokupad_codec.read_puzzle("not a link!")


def test_a_file_that_holds_no_scl_is_refused_naming_the_file(tmp_path):
    path = tmp_path / "p.txt"
    path.write_text("hello\n")

    with pytest.raises(ValueError, match=r"p\.txt"):
        sudokupad_codec.read_puzzle(str(path))


@pytest.mark.parametrize(
    "body",
    [
        LZString().compressToBase64("[1]"),
        # Not JSON, so it falls through to the loader, which needs the recording.
        pytest.param(LZString().compressToBase64("{oops"), marks=needs_app),
    ],
)
def test_a_body_that_is_not_a_puzzle_object_names_the_input(body):
    with pytest.raises(ValueError, match="the-link"):
        sudokupad_codec.decode("scl" + body, "the-link")


def test_a_body_with_no_known_prefix_names_the_input():
    with pytest.raises(ValueError, match="the-link"):
        sudokupad_codec.decode("zzzABC", "the-link")


def test_an_emoji_stored_as_two_utf16_units_is_joined(monkeypatch):
    def no_loader(*args, **kwargs):
        raise AssertionError("fell through to SudokuPad's loader")

    monkeypatch.setattr(subprocess, "run", no_loader)
    # SudokuPad compresses UTF-16 units, so the emoji arrives as a surrogate pair.
    body = LZString().compressToBase64('{"metadata":{"title":"U\ud83e\udedb to N"}}')

    assert sudokupad_codec.decode("scl" + body, "src").puzzle == {
        "metadata": {"title": "U\U0001fadb to N"}
    }


# The loader bridge, run over a stand-in app in a synthetic recording: these
# check the harness and need only node. The real loader is the golden tests'.
BUNDLE = "const loadFPuzzle = {}; const PuzzleZipper = {};"
LOADER = """
const PuzzleLoader = { parsePuzzleData: async id => {
  if (id.includes('boom')) throw new Error('the loader threw on ' + id);
  if (id.includes('{')) return JSON.parse(id.slice(id.indexOf('{')));
  if (id.includes('fail')) { console.error('parsePuzzleData:', 'bad body'); return id; }
  return { id: md5Digest(id), seen: id, fetch: typeof fetch, window: typeof window,
           document: typeof document };
} };
"""


def har_entry(url, body, mime="application/javascript"):
    return {
        "request": {"method": "GET", "url": url},
        "response": {"status": 200, "content": {"mimeType": mime, "text": body}},
    }


def write_har(path, *entries):
    path.write_text(json.dumps({"log": {"entries": list(entries)}}))
    return str(path)


@pytest.fixture
def stub_app(tmp_path, monkeypatch):
    har = write_har(
        tmp_path / "app.har",
        har_entry("https://sudokupad.app/puzpatcher.bundle.js?v=1", BUNDLE),
        har_entry("https://sudokupad.app/puzzleloader.js?v=1", LOADER),
    )
    monkeypatch.setenv("SUDOKUPAD_HAR", har)


@needs_node
def test_the_loader_runs_the_apps_code_with_an_md5_stand_in_and_nothing_else(stub_app):
    puzzle = sudokupad_codec.decode("fpuzzlesABC", "src").puzzle

    assert puzzle["seen"] == "fpuzzlesABC"
    assert puzzle["id"] == hashlib.md5(b"fpuzzlesABC").hexdigest()
    assert (puzzle["fetch"], puzzle["window"], puzzle["document"]) == ("undefined",) * 3


@needs_node
def test_a_string_back_from_the_loader_is_a_failure_naming_the_input(stub_app):
    with pytest.raises(ValueError, match="the-link") as e:
        sudokupad_codec.decode("fpuzzlesfail", "the-link")
    assert "bad body" in str(e.value)


@needs_node
def test_an_error_thrown_by_the_loader_names_the_input_too(stub_app):
    with pytest.raises(ValueError, match=r"the-link.*the loader threw on fpuzzlesboom"):
        sudokupad_codec.decode("fpuzzlesboom", "the-link")


@needs_node
def test_a_ctc_link_goes_through_the_loader_even_when_its_body_is_json(stub_app):
    body = LZString().compressToBase64(json.dumps({"lines": []}))

    decoded = sudokupad_codec.decode("ctc" + body, "src")

    assert decoded.form == "ctc" and decoded.puzzle["seen"] == "ctc" + body


@needs_node
def test_a_missing_recording_is_an_environment_error_naming_the_file(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SUDOKUPAD_HAR", str(tmp_path / "none.har"))

    with pytest.raises(RuntimeError, match=r"none\.har"):
        sudokupad_codec.decode("fpuzzlesABC", "src")


@needs_node
def test_a_recording_without_the_loader_names_the_missing_file(tmp_path, monkeypatch):
    monkeypatch.setenv("SUDOKUPAD_HAR", write_har(tmp_path / "thin.har"))

    with pytest.raises(RuntimeError, match=r"puzpatcher\.bundle\.js"):
        sudokupad_codec.decode("fpuzzlesABC", "src")


def hoisted(puzzle):
    return sudokupad_codec.decode("fpuzzles" + json.dumps(puzzle), "src").puzzle


@needs_node
def test_metadata_cages_become_metadata_and_a_repeated_rules_cage_joins(stub_app):
    puzzle = hoisted(
        {
            "cages": [
                {"value": "title: T"},
                {"value": "rules: one"},
                {"value": "rules: two"},
                {"cells": [[0, 0]], "unique": True},
                {"value": "solution: 1234"},
            ]
        }
    )

    assert puzzle["metadata"] == {"title": "T", "rules": "one\ntwo", "solution": "1234"}
    assert puzzle["cages"] == [{"cells": [[0, 0]], "unique": True}]


@needs_node
def test_a_metadata_object_the_puzzle_has_wins_and_only_five_names_hoist(stub_app):
    puzzle = hoisted(
        {
            "metadata": {"title": "kept"},
            "cages": [
                {"value": "title: from a cage"},
                {"value": "author: A"},
                {"value": "foglight: r1c1"},
                {"cells": [[0, 0]], "value": "title: not metadata"},
            ],
        }
    )

    assert puzzle["metadata"] == {"title": "kept", "author": "A"}
    assert [c["value"] for c in puzzle["cages"]] == [
        "foglight: r1c1",
        "title: not metadata",
    ]
