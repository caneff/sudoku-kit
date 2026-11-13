"""What the link tests share: one fake of the SudokuMaker app's `/api/puzzles`
and the builders of a D payload."""

import base64
import io
import json
import zlib

from sudoku_kit import link_codec


def puzzle_answer_body(puzzle):
    """The body `/api/puzzles/<id>` answers a GET with."""
    return json.dumps({"puzzle": puzzle}).encode()


class ShortLinkApp:
    """Mints an id on a POST; answers a GET with `body` as it stands, else
    raises `error`, else the stored payload, else the last one posted. Records
    every request's URL and timeout."""

    def __init__(
        self,
        monkeypatch,
        *,
        minted=b'{"id": "AbCdEfGhIj"}',
        stored=None,
        body=None,
        error=None,
    ):
        self.requests, self.timeouts = [], []
        self.posts, self.gets = [], []
        self._minted, self._stored = minted, stored
        self._body, self._error = body, error
        monkeypatch.setattr(link_codec.urllib.request, "urlopen", self)

    @property
    def urls(self):
        return [request.full_url for request in self.requests]

    def __call__(self, request, timeout=None):
        self.requests.append(request)
        self.timeouts.append(timeout)
        if request.data is None:
            self.gets.append(request)
            if self._error is not None:
                raise self._error
            if self._body is not None:
                return io.BytesIO(self._body)
            stored = self._stored
            if stored is None:
                stored = json.loads(self.posts[-1].data)["puzzle"]
            return io.BytesIO(puzzle_answer_body(stored))
        self.posts.append(request)
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
