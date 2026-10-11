"""The codec for SudokuMaker puzzle links: https://sudokumaker.app/?puzzle=<payload>

`encode_link` returns the full link, not the bare payload. `decode_puzzle`
takes a full link or a bare payload and splits out the payload itself, so
`encode_link`'s output can be fed straight back into `decode_puzzle`.
`read_link` fetches the link to decode when it may be sitting in a file.

A round trip preserves the document, not the link text: a link written by the
app and a link written here can compress to different payloads and still open
the same puzzle. Compare documents, never link strings.
"""

import json
import urllib.parse
from pathlib import Path

from lzstring import LZString

LINK_PREFIX = "https://sudokumaker.app/?puzzle="


def read_link(source):
    """The link named by `source`: the link itself, or a file holding one.

    A link is one long token with no whitespace, so a `source` that names an
    existing file is read and anything else is already the link. The file's
    last whitespace-separated token wins, which tolerates a trailing newline
    and a file that comments above the link.
    """
    try:
        is_file = Path(source).is_file()
    except OSError:
        # A link is longer than a file name may be, and Python 3.11 raises
        # on such a name instead of answering that it is no file.
        is_file = False
    if is_file:
        return Path(source).read_text().split()[-1]
    return source.strip()


def decode_puzzle(link):
    """The puzzle doc (a dict) held in a SudokuMaker link or bare payload."""
    payload = link.split("puzzle=")[-1]
    return json.loads(
        LZString.decompressFromEncodedURIComponent(urllib.parse.unquote(payload))
    )


def encode_link(doc):
    """The full SudokuMaker link for a puzzle doc; decode_puzzle reads it back.

    Raises ValueError rather than return a link that does not decode back to
    `doc`: a link that has quietly lost a field opens as a different puzzle,
    and finding that out from a solver is far too late. The comparison is
    against `doc` as JSON carries it, so a tuple where the document holds a
    list is not a difference.
    """
    text = json.dumps(doc)
    link = LINK_PREFIX + LZString.compressToEncodedURIComponent(text)
    if decode_puzzle(link) != json.loads(text):
        raise ValueError("link does not round-trip; refusing to return it")
    return link
