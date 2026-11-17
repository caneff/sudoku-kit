"""The reader for SudokuPad puzzle links: https://sudokupad.app/<form><body>

`read_puzzle` returns the puzzle JSON that a link, a short id, a bare encoded
string or a file holding one stands for. `decode` takes the encoded string and
returns a `Decoded`: the puzzle and the `form` (`scl`, `ctc`, `fpuzzles` or
`fpuz`) the link carried. Both name the input in the `ValueError` they raise.

A plain-JSON `scl` body is read here (lz-string and `json.loads`). Every other
body (a `ctc` or f-puzzles link, a compact JS-literal body from a SudokuMaker or
Penpa import) goes through SudokuPad's own `PuzzleLoader`, run in `node` over
app files taken from a recording of the app (`sudokupad_loader.js`), because
SudokuPad is not open source. The recording is a HAR file at `$SUDOKUPAD_HAR`,
else `~/.cache/sudokupad-art/sudokupad.har`; sudokupad-art's
`render_real.js --record` writes it. A missing node or recording is a
`RuntimeError`, the environment's, never a bad link.

A short id is resolved with one GET of `https://sudokupad.app/api/puzzle/<id>`.
Only the decode lives here: the drawing helpers, build runner and `save` stay
in sudokupad-art.
"""

import json
import os
import re
import subprocess
import typing
import urllib.parse
import urllib.request
from pathlib import Path

from lzstring import LZString

# The link forms decoded without a fetch; `fpuzzles` before its prefix `fpuz`.
ENCODED_PREFIXES = ("scl", "fpuzzles", "fpuz", "ctc")
SUDOKUPAD_HOSTS = ("sudokupad.app", "www.sudokupad.app")
BASE_URL = "https://sudokupad.app/"
FETCH_TIMEOUT_SECONDS = 15
LOADER = Path(__file__).with_name("sudokupad_loader.js")
PREVIEW_CHARACTERS = 60
META_TAG = re.compile(r"(title|author|rules|solution|msgcorrect): ?([\s\S]*)")


class Decoded(typing.NamedTuple):
    """A decoded link: the SCL `puzzle`, and `form`, the prefix the link carried."""

    puzzle: dict
    form: str


def default_har():
    """Where the recording of SudokuPad's app is read from."""
    return os.environ.get("SUDOKUPAD_HAR") or str(
        Path.home() / ".cache" / "sudokupad-art" / "sudokupad.har"
    )


def link_token(src):
    """The one token a link carries: the `puzzle=` query value of a `?puzzle=scl…`
    URL, else the last path segment with any `?setting-…` query dropped."""
    m = re.search(r"[?&]puzzle=([^&#]*)", src)
    if m:
        return urllib.parse.unquote(m.group(1))
    path = urllib.parse.urlsplit(src).path.lstrip("/")
    if path.startswith(ENCODED_PREFIXES):
        return path  # an encoded body is base64, which holds `/`: the whole path is the token
    return path.rstrip("/").split("/")[-1]


def encoded_string(src):
    """Resolve `src` (a short id, link, encoded string or local `.scl`/`.txt`
    file) to a raw encoded string. Fetches once, and only when nothing local
    matched."""
    if src.endswith((".txt", ".scl")):
        text = Path(src).read_text().strip()
        if not text.startswith(ENCODED_PREFIXES):
            raise ValueError(f"{src} does not contain an encoded puzzle string")
        return text
    if "://" in src and urllib.parse.urlsplit(src).hostname not in SUDOKUPAD_HOSTS:
        raise ValueError(f"not a sudokupad.app link: {src[:PREVIEW_CHARACTERS]!r}")
    token = link_token(src)
    if token.startswith(ENCODED_PREFIXES):
        return token
    if not re.fullmatch(r"[A-Za-z0-9_-]+", token):
        raise ValueError(
            f"unrecognised puzzle link form, not a link: {src[:PREVIEW_CHARACTERS]!r}"
        )
    with urllib.request.urlopen(
        f"{BASE_URL}api/puzzle/{token}", timeout=FETCH_TIMEOUT_SECONDS
    ) as response:
        blob = response.read().decode().strip()
    if not blob.startswith("scl"):
        raise ValueError(
            f"unexpected payload for id={token!r}: {blob[:PREVIEW_CHARACTERS]!r}"
        )
    return blob


def _plain_scl(encoded):
    """The one decode that needs no SudokuPad logic; None when the body is not JSON."""
    text = LZString().decompressFromBase64(urllib.parse.unquote(encoded[len("scl") :]))
    if not text:
        return None
    # SudokuPad compresses UTF-16 units, so an emoji outside the BMP decodes as
    # two surrogates; join them.
    try:
        return json.loads(text.encode("utf-16", "surrogatepass").decode("utf-16"))
    except ValueError:
        return None


def _sudokupad_parse(encoded):
    """`encoded` parsed by SudokuPad's own `PuzzleLoader.parsePuzzleData`.
    ValueError is a bad body; RuntimeError is the recording, its app code or node."""
    try:
        run = subprocess.run(
            ["node", str(LOADER), json.dumps(SUDOKUPAD_HOSTS)],
            input=encoded,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
    except FileNotFoundError as e:
        raise RuntimeError(
            "node is not installed: SudokuPad's PuzzleLoader runs in it"
        ) from e
    if run.returncode == 2:
        raise RuntimeError(run.stderr.strip())
    if run.returncode:
        raise ValueError(run.stderr.strip() or f"the loader exited {run.returncode}")
    return json.loads(run.stdout)


def _hoist_metadata(puzzle):
    """`puzzle` with its metadata cages moved into `metadata`, the shape every
    caller reads. The loader hands a title, author, rules, solution or solve
    message back as a cage with no cells and a `name: value` value, which
    SudokuPad's `App.extractPuzzleMeta` reads at load; this does that move for
    those five names only. A repeated `rules` joins on a newline, any other
    repeat keeps the last, and an existing `metadata` wins."""
    cages, meta = [], {}
    for cage in puzzle.get("cages", []):
        tag = (
            META_TAG.fullmatch(str(cage.get("value", "")))
            if not cage.get("cells")
            else None
        )
        if not tag:
            cages.append(cage)
        elif tag[1] == "rules" and "rules" in meta:
            meta["rules"] += "\n" + tag[2]
        else:
            meta[tag[1]] = tag[2]
    if len(cages) == len(puzzle.get("cages", [])):
        return puzzle
    return {
        **puzzle,
        "cages": cages,
        "metadata": {**meta, **puzzle.get("metadata", {})},
    }


def decode(encoded, src):
    """Decompress an encoded string to a `Decoded` SCL puzzle. Names `src` on
    any failure, including a body that is not a puzzle object."""
    prefix = next((p for p in ENCODED_PREFIXES if encoded.startswith(p)), None)
    if prefix is None:
        raise ValueError(
            f"{src[:PREVIEW_CHARACTERS]!r} is not a decodable puzzle: it starts with no known "
            f"prefix ({', '.join(ENCODED_PREFIXES)})"
        )
    try:
        body = _plain_scl(encoded) if prefix == "scl" else None
        if body is None:
            body = _hoist_metadata(_sudokupad_parse(encoded))
        if not isinstance(body, dict):
            raise ValueError(
                f"the body is a {type(body).__name__}, not a puzzle object"
            )
        return Decoded(body, prefix)
    except (
        AttributeError,
        KeyError,
        TypeError,
        ValueError,
        AssertionError,
        IndexError,
    ) as e:
        raise ValueError(
            f"{src[:PREVIEW_CHARACTERS]!r} is not a decodable {prefix}… puzzle: {e}"
        ) from e


def read_puzzle(source):
    """The puzzle JSON that `source` stands for: a short id, a SudokuPad URL
    (a `?setting-…` query is dropped, a `?puzzle=scl…` one decodes offline), an
    `scl…`/`ctc…`/`fpuzzles…`/`fpuz…` string, or a `.scl`/`.txt` file holding one of those."""
    return decode(encoded_string(source), source).puzzle
