"""The solve-guide command line:

    python -m sudoku_kit.solve_guide <input> <output directory>

`<input>` is a SudokuPad link, short id, encoded string or link file, or a
`.json` file holding the puzzle JSON `sudokupad_codec.read_puzzle` returns
(each imported by `sudokupad_import`), or a `.json` rules file. A `.json`
holding `cells` is puzzle JSON; one holding `size` is a rules file. Writes
`rules.json` and `checks.json` (`rules_file.check`) into the output
directory. When the checks pass it runs the step search (`step_search`),
saving `steps.json`, the step record, after every step; a `steps.json`
already there is resumed from. `--hint` gives a claim, as the step record
writes one, and `--named` each constraint it uses: the hint is proved from
those alone and appended before the search goes on; a hint not proved is
reported (a refuted one with its witness) and nothing is searched.

Writes `render.html` as soon as the rules file is read: the plain render
(givens and clues, no step) beside the original image when `--image` names one,
for the import comparison. After the search, whether it solved, stopped or got
stuck, it writes `guide.html` (`guide_html`): the main steps, each on its own
SVG grid, runs of singles as one line each, the image once at the top.

Exits 0 when the search reached the solution or stopped at `--max-steps`, 1
when a check failed, 2 when the input or a hint cannot be read or imported
(writing nothing), 3 when the search is stuck, and 4 when a hint was not
proved.
"""

import argparse
import json
import sys
from pathlib import Path

from sudoku_kit import (
    guide_html,
    rules_file,
    step_search,
    sudokupad_codec,
    sudokupad_import,
)


def _read(source):
    if source.endswith(".json"):
        try:
            data = json.loads(Path(source).read_text())
        except ValueError as e:
            raise ValueError(f"{source} is not JSON: {e}") from e
        if isinstance(data, dict) and "cells" in data:
            return sudokupad_import.rules_file(data)
        if isinstance(data, dict) and "size" in data:
            return rules_file.load(source)
        raise ValueError(
            f"{source} is neither SudokuPad puzzle JSON (no cells) nor a rules "
            "file (no size)"
        )
    return sudokupad_import.rules_file(sudokupad_codec.read_puzzle(source))


def _write(path, data):
    path.write_text(json.dumps(data, indent=1) + "\n")


def main(argv=None):
    parser = argparse.ArgumentParser(prog="solve-guide", description=__doc__)
    parser.add_argument("input", help="SudokuPad link or file, or a rules .json")
    parser.add_argument("output", type=Path, help="directory to write into")
    parser.add_argument(
        "--time-limit", type=float, default=60.0, help="seconds per check solve"
    )
    parser.add_argument(
        "--proof-limit", type=float, default=60.0, help="seconds per search proof"
    )
    parser.add_argument("--max-steps", type=int, help="stop after this many new steps")
    parser.add_argument("--hint", help="a claim as JSON, proved before the search")
    parser.add_argument(
        "--named",
        action="append",
        default=[],
        help="a constraint the hint uses; repeat for each",
    )
    parser.add_argument(
        "--image", help="the original puzzle image, shown at the top of the guide"
    )
    args = parser.parse_args(argv)
    try:
        rules = _read(args.input)
    except ValueError as e:
        print(f"solve-guide: {e}", file=sys.stderr)
        return 2
    checks = rules_file.check(rules, args.time_limit)
    args.output.mkdir(parents=True, exist_ok=True)
    _write(args.output / "rules.json", rules)
    _write(args.output / "checks.json", checks)
    (args.output / "render.html").write_text(guide_html.plain_page(rules, args.image))
    unique, fits = checks["unique"], checks["solution_fits"]
    print(f"unique: {unique['status']}")
    if fits["passed"] is None:
        print("solution fits: no stored solution")
    else:
        print(f"solution fits: {'yes' if fits['passed'] else 'no'}")
        for name in fits["failing"]:
            print(f"  the stored solution breaks {name}")
    if not rules_file.passed(checks):
        return 1
    return _search(rules, args)


def _search(rules, args):
    path = args.output / "steps.json"
    try:
        record = step_search.load_record(path)
        search = step_search.Search(rules, record, path, args.proof_limit)
        if args.hint is not None:
            claim = step_search.claim_from_json(_hint_json(args.hint))
            result = search.hint(claim, args.named)
    except ValueError as e:
        print(f"solve-guide: {e}", file=sys.stderr)
        return 2
    if args.hint is not None and result.status != "proved":
        print(f"hint: {result.status}")
        if result.witness:
            cells = " ".join(
                f"{rules_file.cell_name(c)}={d}" for c, d in result.witness.items()
            )
            print(f"witness: {cells}")
        return 4
    outcome = search.run(args.max_steps)
    steps = record["steps"]
    hard = sum(step["hard"] for step in steps)
    print(f"search: {outcome} after {len(steps)} steps ({hard} hard)")
    (args.output / "guide.html").write_text(
        guide_html.guide_page(rules, record, args.image)
    )
    return 3 if outcome == "stuck" else 0


def _hint_json(text):
    try:
        return json.loads(text)
    except ValueError as e:
        raise ValueError(f"hint {text[:60]!r} is not JSON: {e}") from e


if __name__ == "__main__":
    sys.exit(main())
