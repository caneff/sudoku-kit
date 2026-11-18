"""The step search through the solve-guide command line, and the step record
it writes, on Diagonal Dots (Logic Masters 000HUJ, `tests/solve_guide/`).

The record is read here without the search module's own helpers: each step's
candidates are rebuilt from the givens and the earlier steps' claims, so a
step that only holds because of a wrong replay still fails.
"""

import json
from pathlib import Path

import pytest

from sudoku_kit import rules_file, step_search
from sudoku_kit.solve_guide import main
from sudoku_kit.step_prover import Place, prove

FIXTURES = Path(__file__).parent / "solve_guide"
DIAGONAL_DOTS = FIXTURES / "diagonal-dots-000HUJ.json"
DUTCH_DOTS = FIXTURES / "dutch-dots-000KVY.json"


def _replay(rules, steps):
    """(candidates before the step, step) for each step, rebuilt here; the
    last pair is the candidates after every step, and None."""
    n = rules["size"]
    cands = {cell: set(range(1, n + 1)) for cell in rules_file.cells(rules)}
    for given in rules["givens"]:
        cands[tuple(given["cell"])] = {given["digit"]}
    for step in steps:
        yield {c: sorted(d) for c, d in cands.items()}, step
        cell = tuple(step["claim"]["cell"])
        cands[cell] &= set(step["claim"]["digits"])
    yield {c: sorted(d) for c, d in cands.items()}, None


def _run(source, out, *extra):
    code = main([str(source), str(out), *extra])
    record = json.loads((out / "steps.json").read_text())
    rules = json.loads((out / "rules.json").read_text())
    return code, record, rules


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    return _run(DIAGONAL_DOTS, tmp_path_factory.mktemp("solved"))


def test_the_path_on_diagonal_dots_ends_at_the_stored_solution(solved):
    code, record, rules = solved
    assert code == 0
    assert record["stuck"] is None
    *_, (final, _) = _replay(rules, record["steps"])
    n = rules["size"]
    assert [[final[r, c] for c in range(n)] for r in range(n)] == [
        [[d] for d in row] for row in rules["solution"]
    ]


SKYSCRAPERS = Path(__file__).parent / "solve_guide" / "skyscraper-nextdoor-000N2S.json"


def test_outside_cells_are_carried_as_candidates_to_the_stuck_point(tmp_path):
    code, record, rules = _run(SKYSCRAPERS, tmp_path, "--proof-limit", "0.0")
    n = rules["size"]
    outside = sorted(
        {tuple(c) for clue in rules["clues"] for c in clue["cells"]}
        - {(r, c) for r in range(n) for c in range(n)}
    )

    assert code == 5
    assert outside
    assert record["stuck"]["outside"] == [
        {"cell": list(cell), "candidates": list(range(1, n + 1))} for cell in outside
    ]


def _reproves(rules, record):
    named = rules_file.registry(rules)
    for cands, step in _replay(rules, record["steps"]):
        if step is None:
            return
        claim = Place(tuple(step["claim"]["cell"]), step["claim"]["digits"])
        result = prove(cands, named, step["named"], claim, time_limit=60)
        assert result.status == "proved", step
        assert step["hard"] == (len(step["named"]) > 3)


def test_every_step_proves_again_from_only_its_named_constraints(solved):
    _, record, rules = solved
    assert record["steps"]
    _reproves(rules, record)


def test_on_a_puzzle_with_outside_cells_the_path_solves_them_too(tmp_path):
    code, record, rules = _run(SKYSCRAPERS, tmp_path)
    assert code == 0
    _reproves(rules, record)
    *_, (final, _) = _replay(rules, record["steps"])
    for entry in rules["solution_outside"]:
        assert final[tuple(entry["cell"])] == [entry["digit"]]


def test_a_solved_grid_with_unsolved_outside_cells_is_not_finished(tmp_path):
    _, _, rules = _run(SKYSCRAPERS, tmp_path / "import", "--max-steps", "0")
    n = rules["size"]
    rules["givens"] = [
        {"cell": [r, c], "digit": rules["solution"][r][c]}
        for r in range(n)
        for c in range(n)
    ]
    source = tmp_path / "all-given.json"
    source.write_text(json.dumps(rules))

    code, record, rules = _run(source, tmp_path / "out")

    assert code == 0
    assert record["steps"]
    _reproves(rules, record)
    *_, (final, _) = _replay(rules, record["steps"])
    for entry in rules["solution_outside"]:
        assert final[tuple(entry["cell"])] == [entry["digit"]]


def test_a_stopped_run_saved_the_first_steps_of_the_full_path(solved, tmp_path):
    _, full, _ = solved
    code, stopped, _ = _run(DIAGONAL_DOTS, tmp_path, "--max-steps", "5")
    assert code == 0
    assert stopped["steps"] == full["steps"][:5]
    assert stopped["stuck"] is None


@pytest.mark.parametrize("left", [5, 30])
def test_a_run_resumes_from_its_step_record_to_the_same_path(solved, tmp_path, left):
    _, full, _ = solved
    kept = len(full["steps"]) - left
    stopped = dict(full, steps=full["steps"][:kept], timeouts=[])
    (tmp_path / "steps.json").write_text(json.dumps(stopped))

    code, resumed, _ = _run(DIAGONAL_DOTS, tmp_path, "--max-steps", "2")

    # A fresh run would stop after 2 steps; a resumed one after kept + 2.
    assert code == 0
    assert resumed["steps"] == full["steps"][: kept + 2]

    code, resumed, _ = _run(DIAGONAL_DOTS, tmp_path)

    assert code == 0
    assert resumed["steps"] == full["steps"]


def test_the_step_record_is_saved_after_every_step(tmp_path, monkeypatch):
    on_disk = []
    save = step_search.save_record

    def saving(record, path):
        save(record, path)
        on_disk.append(len(json.loads(path.read_text())["steps"]))

    monkeypatch.setattr(step_search, "save_record", saving)
    code, record, _ = _run(DIAGONAL_DOTS, tmp_path, "--max-steps", "3")

    assert code == 0
    assert len(record["steps"]) == 3
    assert on_disk[:3] == [1, 2, 3]


def test_a_search_step_names_only_its_irreducible_set(solved):
    _, record, rules = solved
    named = rules_file.registry(rules)
    steps = record["steps"]
    for cands, step in _replay(rules, steps):
        if step is None:
            break
        claim = Place(tuple(step["claim"]["cell"]), step["claim"]["digits"])
        for drop in step["named"]:
            fewer = [n for n in step["named"] if n != drop]
            result = prove(cands, named, fewer, claim, time_limit=60)
            assert result.status == "refuted", (step, drop)


def test_a_step_record_from_another_puzzle_is_refused_and_nothing_written(
    tmp_path, capsys
):
    first = tmp_path / "first"
    code, record, _ = _run(DIAGONAL_DOTS, first, "--max-steps", "3")
    assert code == 0
    second = tmp_path / "second"
    second.mkdir()
    (second / "steps.json").write_text(json.dumps(record))

    code = main([str(DUTCH_DOTS), str(second)])

    assert code == 2
    assert "step 1" in capsys.readouterr().err
    assert sorted(p.name for p in second.iterdir()) == ["steps.json"]
    assert json.loads((second / "steps.json").read_text()) == record


def test_a_step_record_a_changed_clue_breaks_is_refused(solved, tmp_path, capsys):
    _, full, rules = solved
    used = next(n for s in full["steps"] for n in s["named"] if n in _clue_ids(rules))
    rules["clues"] = [c for c in rules["clues"] if c["id"] != used]
    source = tmp_path / "changed.json"
    source.write_text(json.dumps(rules))
    out = tmp_path / "out"
    out.mkdir()
    (out / "steps.json").write_text(json.dumps(full))

    code = main([str(source), str(out)])

    assert code == 2
    assert used in capsys.readouterr().err


def _clue_ids(rules):
    return {clue["id"] for clue in rules["clues"]}


@pytest.fixture
def stuck(tmp_path):
    """Diagonal Dots stopped at the start: every proof forced to time out."""
    code, record, _ = _run(DIAGONAL_DOTS, tmp_path, "--proof-limit", "0.0")
    assert code == 5
    return tmp_path, record


def test_a_search_whose_proofs_all_time_out_records_a_timed_out_stuck_point(stuck):
    _, record = stuck
    assert record["steps"] == []
    assert record["timeouts"]
    assert record["stuck"]["timeouts"] == len(record["timeouts"])
    assert record["stuck"]["grid"][4][5] == 4
    assert record["stuck"]["grid"][0][0] == 0
    assert record["stuck"]["candidates"][0][0] == [1, 2, 3, 4, 5, 6]


def _hint(out, claim, *named, extra=()):
    flags = [f for name in named for f in ("--named", name)]
    args = [str(DIAGONAL_DOTS), str(out), "--hint", json.dumps(claim), *flags]
    return main([*args, *extra])


# r5c6 is given as 4, so row 5 keeps 4 out of r5c1. The hint names three
# constraints more than it needs: a hint is recorded as named, and so is hard.
HINT = {"cell": [4, 0], "digits": [1, 2, 3, 5, 6]}
HINT_NAMED = (
    "row 5",
    "region 5",
    "white-dot-r5c3-r6c2",
    "black-dot-r5c1-r6c2",
)


def test_a_valid_hint_is_appended_and_the_search_continues(stuck):
    out, _ = stuck
    code = _hint(out, HINT, *HINT_NAMED, extra=("--max-steps", "3"))

    record = json.loads((out / "steps.json").read_text())
    assert code == 0
    assert record["stuck"] is None
    assert record["steps"][0] == {
        "claim": HINT,
        "named": list(HINT_NAMED),
        "hard": True,
        "by": "hint",
    }
    assert [s["by"] for s in record["steps"][1:]] == ["search"] * 3
    rules = json.loads((out / "rules.json").read_text())
    _reproves(rules, record)


def test_a_wrong_hint_is_refuted_with_a_witness_and_not_recorded(stuck, capsys):
    out, before = stuck
    capsys.readouterr()

    code = _hint(out, {"cell": [4, 0], "digits": [4]}, *HINT_NAMED)

    assert code == 4
    printed = capsys.readouterr().out
    assert "refuted" in printed
    assert "r5c6=4" in printed  # the given, which keeps 4 out of r5c1
    assert json.loads((out / "steps.json").read_text()) == before


def test_a_hint_naming_an_unknown_constraint_is_refused(stuck, capsys):
    out, before = stuck
    code = _hint(out, HINT, "row 99")
    assert code == 2
    assert "row 99" in capsys.readouterr().err
    assert json.loads((out / "steps.json").read_text()) == before


def test_a_hint_with_no_named_constraint_is_refused_writing_nothing(tmp_path, capsys):
    out = tmp_path / "out"
    code = _hint(out, HINT)
    assert code == 2
    assert "constraint" in capsys.readouterr().err
    assert not out.exists()


def test_a_hint_that_is_not_json_is_refused_writing_nothing(tmp_path, capsys):
    out = tmp_path / "out"
    code = main([str(DIAGONAL_DOTS), str(out), "--hint", "r5c1", "--named", "row 5"])
    assert code == 2
    assert "r5c1" in capsys.readouterr().err
    assert not out.exists()


def test_a_missing_input_file_is_refused_by_name(tmp_path, capsys):
    out = tmp_path / "out"
    code = main([str(tmp_path / "missing.json"), str(out)])
    assert code == 2
    assert "missing.json" in capsys.readouterr().err
    assert not out.exists()


def test_a_link_sudokupads_loader_cannot_read_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SUDOKUPAD_HAR", str(tmp_path / "no-recording.har"))
    out = tmp_path / "out"
    code = main(["ctcN4IgzglgXgpiBcBOANCA5gJwgEwQbT2AF9AA", str(out)])
    assert code == 2
    assert "SudokuPad" in capsys.readouterr().err
    assert not out.exists()


def test_a_uniqueness_check_that_times_out_is_no_verdict(tmp_path):
    _, _, rules = _run(DIAGONAL_DOTS, tmp_path / "import", "--max-steps", "0")
    del rules["solution"]  # its check would time out first
    source = tmp_path / "no-solution.json"
    source.write_text(json.dumps(rules))
    out = tmp_path / "out"

    code = main([str(source), str(out), "--time-limit", "0.0"])

    checks = json.loads((out / "checks.json").read_text())
    assert code == 5
    assert checks["unique"] == {"status": "timeout", "passed": None}
    assert not (out / "steps.json").exists()


def test_an_image_path_is_written_relative_to_the_output_directory(tmp_path):
    image = tmp_path / "pictures" / "original.png"
    image.parent.mkdir()
    image.write_bytes(b"")
    out = tmp_path / "out"
    main([str(DIAGONAL_DOTS), str(out), "--max-steps", "0", "--image", str(image)])
    for page in ("render.html", "guide.html"):
        assert 'src="../pictures/original.png"' in (out / page).read_text()


def _empty_grid():
    """A 4x4 grid with no givens and no clues: many solutions, so no claim
    ever proves."""
    boxes = [
        [[r, c] for r in range(br, br + 2) for c in range(bc, bc + 2)]
        for br in (0, 2)
        for bc in (0, 2)
    ]
    return {"size": 4, "regions": boxes, "givens": [], "clues": []}


def test_a_stuck_point_where_no_proof_timed_out_is_a_real_one(tmp_path):
    record = step_search.new_record()
    path = tmp_path / "steps.json"
    search = step_search.Search(_empty_grid(), record, path, proof_limit=60)

    assert search.run() == "stuck"
    assert record["timeouts"] == []
    assert record["stuck"]["timeouts"] == 0
    assert record["stuck"]["candidates"][0][0] == [1, 2, 3, 4]
