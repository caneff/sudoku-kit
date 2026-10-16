#!/usr/bin/env bash
# The repo's end-to-end seam: the same gate as `just check` (ruff, format, pytest).
# `--changed <ref>` is accepted and ignored: the whole suite runs in seconds, so
# there is no narrower run to select.
set -euo pipefail
cd "$(dirname "$0")/.."
uv run ruff check
uv run ruff format --check
uv run pytest -q
