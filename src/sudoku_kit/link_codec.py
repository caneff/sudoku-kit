"""The codec for SudokuMaker puzzle links: https://sudokumaker.app/?puzzle=<payload>

The payload's first letter names its format, as in the app: `D` is
base64url of deflate-raw JSON (what the app writes now), `N` is the older
lz-string form. `decode_puzzle` reads both; `encode_link` writes only `N`.

`encode_link` returns the full link, not the bare payload. `decode_puzzle`
takes a full link or a bare payload and splits out the payload itself, so
`encode_link`'s output can be fed straight back into `decode_puzzle`.
`read_link` fetches the link to decode when it may be sitting in a file, or
behind a short link (https://sudokumaker.app/p/<id>).

A round trip preserves the document, not the link text: a link written by the
app and a link written here can compress to different payloads and still open
the same puzzle. Compare documents, never link strings.
"""

import base64
import http.client
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import zlib
from pathlib import Path

from lzstring import LZString

LINK_PREFIX = "https://sudokumaker.app/?puzzle="
SHORT_LINK = re.compile(
    r"https?://(?:www\.)?((?:dev\.)?sudokumaker\.app)/p/([^/?#]*)/?(?:[?#].*)?",
    re.IGNORECASE,
)
SHORT_LINK_ID = re.compile(r"[A-Za-z0-9_-]+")
USER_AGENT = "sudoku-kit"
FETCH_TIMEOUT_SECONDS = 15


def read_link(source):
    """The link named by `source`: the link itself, or a file holding one.

    A link is one long token with no whitespace, so a `source` that names an
    existing file is read and anything else is already the link. The file's
    last whitespace-separated token wins, which tolerates a trailing newline
    and a file that comments above the link. `source` is a string or a path;
    a file with nothing in it raises ValueError. A mistyped path is not a
    file, so it comes back as it stands and `decode_puzzle` refuses it.

    A short link (`https://sudokumaker.app/p/<id>`), whether passed itself or
    held in the file, is resolved the way the app does it, with one GET of
    `/api/puzzles/<id>`, and comes back as the full link holding the payload.
    A link with no id, an id the app does not know, a failed or cut-off
    request and an answer with no payload each raise ValueError naming the id
    or the link; a request that times out raises TimeoutError.
    """
    source = os.fspath(source)
    try:
        is_file = Path(source).is_file()
    except OSError:
        # A link is longer than a file name may be, and before Python 3.14
        # asking about such a name raises instead of answering "no file".
        is_file = False
    if is_file:
        tokens = Path(source).read_text().split()
        if not tokens:
            raise ValueError(f"{source} holds no link: the file is empty")
        link = tokens[-1]
    else:
        link = source.strip()
    short = SHORT_LINK.fullmatch(link)
    if not short:
        return link
    host, link_id = short.groups()
    if not SHORT_LINK_ID.fullmatch(link_id):
        raise ValueError(f"short link has no usable id after /p/: {link[:60]!r}")
    return _resolve_short_link(host, link_id)


def _resolve_short_link(host, link_id):
    """The full link behind the short link `https://<host>/p/<link_id>`."""
    url = f"https://{host}/api/puzzles/{link_id}"
    where = f"short link {link_id!r}: {url}"
    # The API's CDN refuses urllib's default User-Agent with a 403.
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=FETCH_TIMEOUT_SECONDS) as response:
            payload = json.load(response)["puzzle"]
        if not isinstance(payload, str) or not payload:
            raise ValueError("the puzzle is not a payload")
    except urllib.error.HTTPError as error:
        raise ValueError(f"{where} answered {error.code} {error.reason}") from error
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError(f"{where} answered no puzzle payload") from error
    except (OSError, http.client.HTTPException) as error:
        reason = error.reason if isinstance(error, urllib.error.URLError) else error
        if isinstance(reason, TimeoutError):
            raise TimeoutError(f"{where} timed out") from error
        raise ValueError(f"{where} could not be read: {reason!r}") from error
    return LINK_PREFIX + payload


def _payload_text(payload):
    """The JSON text inside `payload`, read by its one-letter format prefix."""
    prefix = payload[:1]
    if prefix == "D":
        body = payload[1:]
        raw = base64.b64decode(
            body + "=" * (-len(body) % 4), altchars=b"-_", validate=True
        )
        inflater = zlib.decompressobj(-zlib.MAX_WBITS)
        text = inflater.decompress(raw)
        if not inflater.eof or inflater.unused_data:
            raise ValueError(
                "the deflate stream is cut short or has bytes after its end"
            )
        return text.decode("utf-8")
    if prefix == "N":
        return LZString.decompressFromEncodedURIComponent(payload)
    if prefix:
        raise ValueError(f"unknown format prefix {prefix!r}")
    raise ValueError("the payload is empty")


def decode_puzzle(link):
    """The puzzle doc (a dict) held in a SudokuMaker link or bare payload.

    Raises ValueError when `link` is neither, naming the start of what it was
    handed: the usual cause is a mistyped file name that `read_link` took for
    the link itself. A payload whose first letter is neither `D` nor `N` is
    refused with that letter named, as the app refuses it.
    """
    payload = urllib.parse.unquote(link.split("puzzle=")[-1])
    try:
        text = _payload_text(payload)
        if not text:
            raise ValueError("the payload decompresses to nothing")
        return json.loads(text)
    except (ValueError, KeyError, IndexError, TypeError, zlib.error) as error:
        raise ValueError(
            f"not a SudokuMaker link or payload ({error}): {link[:60]!r}"
        ) from error


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
