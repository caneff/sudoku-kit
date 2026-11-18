"""What the link tests share: one fake of the SudokuMaker app's `/api/puzzles`,
the builders of a D payload, and `needs_app`, the mark on a test that runs
SudokuPad's own loader."""

import base64
import io
import json
import shutil
import zlib
from pathlib import Path

import pytest

from sudoku_kit import link_codec, sudokupad_codec

needs_app = pytest.mark.skipif(
    not shutil.which("node") or not Path(sudokupad_codec.default_har()).exists(),
    reason="node, or the recording of SudokuPad's app, is missing",
)


def puzzle_answer_body(puzzle):
    """The body `/api/puzzles/<id>` answers a GET with."""
    return json.dumps({"puzzle": puzzle}).encode()


class ShortLinkApp:
    """Mints an id on a POST; answers a GET by raising `error`, else with `body`
    as it stands, else the stored payload, else the last one posted. Records
    every request's URL and timeout. `refusals` are raised, one per request in
    order, after recording the request, so a test scripts "429, then fine"."""

    def __init__(
        self,
        monkeypatch,
        *,
        minted=b'{"id": "AbCdEfGhIj"}',
        stored=None,
        body=None,
        error=None,
        refusals=(),
    ):
        self.requests, self.timeouts = [], []
        self.posts, self.gets = [], []
        self._minted, self._stored = minted, stored
        self._body, self._error = body, error
        self._refusals = list(refusals)
        monkeypatch.setattr(link_codec.urllib.request, "urlopen", self)

    @property
    def urls(self):
        return [request.full_url for request in self.requests]

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        is_get = request.data is None
        (self.gets if is_get else self.posts).append(request)
        if self._refusals:
            raise self._refusals.pop(0)
        if is_get:
            if self._error is not None:
                raise self._error
            if self._body is not None:
                return io.BytesIO(self._body)
            stored = self._stored
            if stored is None:
                stored = json.loads(self.posts[-1].data)["puzzle"]
            return io.BytesIO(puzzle_answer_body(stored))
        if isinstance(self._minted, Exception):
            raise self._minted
        return io.BytesIO(self._minted)


def d_payload_of_deflate(raw, *, pad=False):
    payload = base64.urlsafe_b64encode(raw).decode()
    return "D" + (payload if pad else payload.rstrip("="))


def d_payload_of_text(text):
    return d_payload_of_deflate(zlib.compress(text.encode(), wbits=-zlib.MAX_WBITS))


def d_payload_of_stored(doc, *, pad):
    # Stored blocks keep the deflate length exactly what the text makes it.
    deflate = zlib.compressobj(0, wbits=-zlib.MAX_WBITS)
    raw = deflate.compress(json.dumps(doc).encode()) + deflate.flush()
    return d_payload_of_deflate(raw, pad=pad)


def d_payload(doc):
    return d_payload_of_text(json.dumps(doc))
