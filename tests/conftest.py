"""Fixtures shared across test files."""

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
    and the command's exit code. The search is deterministic."""
    out = tmp_path_factory.mktemp("diagonal-dots")
    code = main([str(DIAGONAL_DOTS), str(out)])
    return out, code


@pytest.fixture(scope="session")
def diagonal_dots_record(diagonal_dots_run):
    out, _ = diagonal_dots_run
    return json.loads((out / "steps.json").read_text())
