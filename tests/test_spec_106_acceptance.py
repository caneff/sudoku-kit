"""Spec #106 end to end: the solve-guide command line, puzzle to guide, on
Diagonal Dots (Logic Masters 000HUJ, its decoded puzzle JSON in
`tests/solve_guide/`). One run, read back from the files it writes:

- the rules file passes its checks: exactly one solution, and the stored
  solution fits every clue;
- every step in the step record proves again from scratch with `prove`, from
  only the constraints it names, on candidates rebuilt here from the givens;
- the path ends at the stored solution, with no stuck point;
- the guide HTML numbers its key ideas 1..N, each merged deduction's steps
  name the same constraints, and each key idea's grid marks the cells it
  changes.

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

import pytest

from sudoku_kit import rules_file
from sudoku_kit.step_prover import Place, prove


@pytest.fixture(scope="module")
def guide(diagonal_dots_run):
    out, code = diagonal_dots_run
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


def test_key_ideas_run_1_to_n_and_each_merge_shares_its_constraints(guide):
    """Spec #127: the guide shows deductions. Every step lands in exactly one
    (a key idea's section or a fill list's item); each one's steps name the
    same constraints, and no step between them changed a cell they use."""
    rules, steps, page = guide["rules"], guide["record"]["steps"], guide["html"]
    registry = rules_file.registry(rules)
    keys = re.findall(
        r'<section class="key" data-key="(\d+)" data-steps="([\d ]+)">(.*?)</section>',
        page,
        re.S,
    )
    fill = re.findall(r'<li class="deduction" data-steps="([\d ]+)">', page)
    groups = [[int(n) for n in g.split()] for g in [k[1] for k in keys] + fill]

    assert [int(k[0]) for k in keys] == list(range(1, len(keys) + 1))
    assert keys and any(len(g) > 1 for g in groups)
    assert sorted(n for g in groups for n in g) == list(range(1, len(steps) + 1))
    for group in groups:
        named = steps[group[0] - 1]["named"]
        assert {frozenset(steps[n - 1]["named"]) for n in group} == {frozenset(named)}
        used = {cell for name in named for cell in registry[name].cells}
        for n in set(range(group[0], group[-1])) - set(group):
            assert tuple(steps[n - 1]["claim"]["cell"]) not in used, (group, n)
    for number, group, section in keys:
        for n in group.split():
            cell = rules_file.cell_name(steps[int(n) - 1]["claim"]["cell"])
            assert re.search(
                rf'<svg class="grid"[^>]*data-key="{number}".*'
                rf'<rect class="[^"]*changed[^"]*"[^>]*data-cell="{cell}"',
                section,
                re.S,
            )
