"""Fixtures shared across test files."""

import contextlib
import io
import json
from pathlib import Path

import pytest

from sudoku_kit.solve_guide import main

DIAGONAL_DOTS = Path(__file__).parent / "solve_guide" / "diagonal-dots-000HUJ.json"


@pytest.fixture(scope="session")
def diagonal_dots_run(tmp_path_factory):
    """One full `solve-guide` search on Diagonal Dots (000HUJ), run once per
    session from the committed puzzle JSON; its step record is never committed
    (AGENTS.md: never publish a solution path). Returns the output directory
    the command's exit code and what it wrote to stderr. The search is
    deterministic."""
    out = tmp_path_factory.mktemp("diagonal-dots")
    stderr = io.StringIO()
    with contextlib.redirect_stderr(stderr):
        code = main([str(DIAGONAL_DOTS), str(out)])
    assert code == 0, f"the session's Diagonal Dots search exited {code}, not 0"
    return out, code, stderr.getvalue()


@pytest.fixture(scope="session")
def diagonal_dots_steps(diagonal_dots_run):
    """Path of the session run's step record, to seed a guide run from."""
    return diagonal_dots_run[0] / "steps.json"


@pytest.fixture(scope="session")
def diagonal_dots_record(diagonal_dots_run):
    out, *_ = diagonal_dots_run
    return json.loads((out / "steps.json").read_text())
