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
import os
import urllib.parse
from pathlib import Path

from lzstring import LZString

LINK_PREFIX = "https://sudokumaker.app/?puzzle="


def read_link(source):
    """The link named by `source`: the link itself, or a file holding one.

    A link is one long token with no whitespace, so a `source` that names an
    existing file is read and anything else is already the link. The file's
    last whitespace-separated token wins, which tolerates a trailing newline
    and a file that comments above the link. `source` is a string or a path;
    a file with nothing in it raises ValueError. A mistyped path is not a
    file, so it comes back as it stands and `decode_puzzle` refuses it.
    """
    source = os.fspath(source)
    try:
        is_file = Path(source).is_file()
    except OSError:
        # A link is longer than a file name may be, and before Python 3.14
        # asking about such a name raises instead of answering "no file".
        is_file = False
    if not is_file:
        return source.strip()
    tokens = Path(source).read_text().split()
    if not tokens:
        raise ValueError(f"{source} holds no link: the file is empty")
    return tokens[-1]


def decode_puzzle(link):
    """The puzzle doc (a dict) held in a SudokuMaker link or bare payload.

    Raises ValueError when `link` is neither, naming the start of what it was
    handed: the usual cause is a mistyped file name that `read_link` took for
    the link itself.
    """
    payload = link.split("puzzle=")[-1]
    try:
        text = LZString.decompressFromEncodedURIComponent(urllib.parse.unquote(payload))
        if not text:
            raise ValueError("the payload decompresses to nothing")
        return json.loads(text)
    except (ValueError, KeyError, IndexError, TypeError) as error:
        raise ValueError(f"not a SudokuMaker link or payload: {link[:60]!r}") from error


def _same_document(sent, back):
    """Whether `back`, decoded from a link, is the document `sent` into it.

    A tuple in `sent` matches the list JSON makes of it; nothing else is
    forgiven. A key that is not a string comes back as one, and NaN comes
    back unequal to itself, so a document holding either is not the same.
    """
    if isinstance(sent, dict):
        return (
            isinstance(back, dict)
            and sent.keys() == back.keys()
            and all(_same_document(v, back[k]) for k, v in sent.items())
        )
    if isinstance(sent, list | tuple):
        return (
            isinstance(back, list)
            and len(sent) == len(back)
            and all(map(_same_document, sent, back))
        )
    return sent == back


def encode_link(doc):
    """The full SudokuMaker link for a puzzle doc; decode_puzzle reads it back.

    Raises ValueError rather than return a link that does not decode back to
    `doc`: a link that has quietly lost a field opens as a different puzzle,
    and finding that out from a solver is far too late. A tuple where the
    document holds a list is the one difference let through; a key that is
    not a string and a NaN are both refused, since JSON does not carry them.
    """
    link = LINK_PREFIX + LZString.compressToEncodedURIComponent(json.dumps(doc))
    if not _same_document(doc, decode_puzzle(link)):
        raise ValueError("link does not round-trip; refusing to return it")
    return link
