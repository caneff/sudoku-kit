"""The step search through the solve-guide command line, and the step record
it writes, on Diagonal Dots (Logic Masters 000HUJ, `tests/solve_guide/`).

The record is read here without the search module's own helpers: each step's
candidates are rebuilt from the givens and the earlier steps' claims, so a
step that only holds because of a wrong replay still fails.
"""

import json
from pathlib import Path

import pytest

from sudoku_kit import rules_file
from sudoku_kit.solve_guide import main
from sudoku_kit.step_prover import Place, prove

DIAGONAL_DOTS = Path(__file__).parent / "solve_guide" / "diagonal-dots-000HUJ.json"


def _search(out, *extra):
    code = main([str(DIAGONAL_DOTS), str(out), *extra])
    return code, json.loads((out / "steps.json").read_text())


def _replay(rules, steps):
    """(candidates before the step, step) for each step, rebuilt here."""
    n = rules["size"]
    cands = {(r, c): set(range(1, n + 1)) for r in range(n) for c in range(n)}
    for given in rules["givens"]:
        cands[tuple(given["cell"])] = {given["digit"]}
    for step in steps:
        yield {c: sorted(d) for c, d in cands.items()}, step
        cell = tuple(step["claim"]["cell"])
        cands[cell] &= set(step["claim"]["digits"])
    yield {c: sorted(d) for c, d in cands.items()}, None


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    out = tmp_path_factory.mktemp("solved")
    code, record = _search(out)
    rules = json.loads((out / "rules.json").read_text())
    return code, record, rules


def test_the_path_on_diagonal_dots_ends_at_the_stored_solution(solved):
    code, record, rules = solved
    assert code == 0
    assert record["stuck"] is None
    *_, (final, _) = _replay(rules, record["steps"])
    n = rules["size"]
    assert [[final[r, c] for c in range(n)] for r in range(n)] == [
        [[d] for d in row] for row in rules["solution"]
    ]
