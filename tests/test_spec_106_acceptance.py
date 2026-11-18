"""Spec #106 end to end: the solve-guide command line, puzzle to guide, on
Diagonal Dots (Logic Masters 000HUJ, its decoded puzzle JSON in
`tests/solve_guide/`). One run, read back from the files it writes:

- the rules file passes its checks: exactly one solution, and the stored
  solution fits every clue;
- every step in the step record proves again from scratch with `prove`, from
  only the constraints it names, on candidates rebuilt here from the givens;
- the path ends at the stored solution, with no stuck point;
- the guide HTML has one grid per shown step, with that step's cells marked.

Blind to: the consumers. grid-hunts and sudokumaker-custom-constraints both
track main and each lock a commit in `uv.lock`, so none of this runs against
their code until one of them runs `uv lock --upgrade-package sudoku-kit`.
Also blind to what the shipping surface shows: the guide opened in Chromium
and printed to PDF, Claude's image import and its step prose (the
`/solve-guide` skill, agent-skills#1947), and SudokuPad's own loader on a live
link, which CI has no recording of; the import from a link is pinned to the
committed JSON by the `needs_app` tests.
"""

import json
import re
from pathlib import Path

import pytest

from sudoku_kit import rules_file
from sudoku_kit.solve_guide import main
from sudoku_kit.step_prover import Place, prove

DIAGONAL_DOTS = Path(__file__).parent / "solve_guide" / "diagonal-dots-000HUJ.json"


@pytest.fixture(scope="module")
def guide(tmp_path_factory):
    out = tmp_path_factory.mktemp("guide")
    code = main([str(DIAGONAL_DOTS), str(out)])
    read = lambda name: json.loads((out / name).read_text())
    return {
        "code": code,
        "rules": read("rules.json"),
        "checks": read("checks.json"),
        "record": read("steps.json"),
        "html": (out / "guide.html").read_text(),
    }


def _candidates_before_each_step(rules, steps):
    n = rules["size"]
    cands = {cell: set(range(1, n + 1)) for cell in rules_file.cells(rules)}
    for given in rules["givens"]:
        cands[tuple(given["cell"])] = {given["digit"]}
    for step in steps:
        yield {c: sorted(d) for c, d in cands.items()}, step
        cands[tuple(step["claim"]["cell"])] &= set(step["claim"]["digits"])
    yield {c: sorted(d) for c, d in cands.items()}, None


def test_the_rules_file_passes_both_checks(guide):
    assert guide["checks"]["unique"]["status"] == "unique"
    assert guide["checks"]["solution_fits"] == {"passed": True, "failing": []}


def test_every_step_proves_again_from_only_its_named_constraints(guide):
    rules, steps = guide["rules"], guide["record"]["steps"]
    registry = rules_file.registry(rules)
    assert steps
    for cands, step in _candidates_before_each_step(rules, steps):
        if step is None:
            break
        claim = Place(tuple(step["claim"]["cell"]), step["claim"]["digits"])
        result = prove(cands, registry, step["named"], claim, time_limit=60)
        assert result.status == "proved", step


def test_the_path_ends_at_the_stored_solution(guide):
    rules, record = guide["rules"], guide["record"]
    assert guide["code"] == 0
    assert record["stuck"] is None
    *_, (final, _) = _candidates_before_each_step(rules, record["steps"])
    for (r, c), digits in final.items():
        assert digits == [rules["solution"][r][c]], (r, c)


def test_the_guide_has_one_grid_per_shown_step_with_its_cells_marked(guide):
    rules, steps, page = guide["rules"], guide["record"]["steps"], guide["html"]
    houses = set(rules_file.house_names(rules))
    expected = {
        i
        for i, step in enumerate(steps, 1)
        if len(step["named"]) >= 2 or not set(step["named"]) <= houses
    }
    grids = dict(
        re.findall(
            r'<svg class="grid"[^>]*data-step="(\d+)"[^>]*>(.*?)</svg>', page, re.S
        )
    )
    assert expected
    assert {int(i) for i in grids} == expected
    for i in expected:
        cell = rules_file.cell_name(steps[i - 1]["claim"]["cell"])
        assert re.search(
            rf'<rect class="[^"]*changed[^"]*"[^>]*data-cell="{cell}"', grids[str(i)]
        )
