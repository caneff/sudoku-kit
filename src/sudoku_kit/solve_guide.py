"""The solve-guide command line:

    python -m sudoku_kit.solve_guide <input> <output directory>

`<input>` is a SudokuPad link, short id, encoded string or link file, or a
`.json` file holding the puzzle JSON `sudokupad_codec.read_puzzle` returns
(each imported by `sudokupad_import`), or a `.json` rules file. A `.json`
holding `cells` is puzzle JSON; one holding `size` is a rules file. Writes
`rules.json` and `checks.json` (`rules_file.check`) into the output
directory. When the checks pass it runs the step search (`step_search`),
saving `steps.json`, the step record, after every step. A `steps.json`
already there is resumed from once every step in it proves again on this
rules file; one that does not (left by another puzzle, or by this one before
a clue changed) is refused. `--hint` gives a claim, as the step record
writes one, and `--named` each constraint it uses (at least one): the hint
is proved from those alone and appended before the search goes on; a hint
not proved is reported (a refuted one with its witness) and nothing is
searched.

Writes `render.html` as soon as the checks have run: the plain render
(givens and clues, no step) beside the original image when `--image` names
one, for the import comparison. After the search, whether it solved, stopped
or got stuck, it writes `guide.html` (`guide_html`): the key ideas, each on
its own SVG grid, the fill between them as one sentence each, the image once
at the top. An `--image` path that exists is written into the HTML relative to the
output directory; a URL, or a path not found, is written as given.

Exit codes:

- 0: the search reached the solution or stopped at `--max-steps`.
- 1: a check failed: the puzzle is not unique, or the stored solution breaks
  a clue.
- 2: the input, the step record already there, or a hint cannot be read,
  imported or used, including SudokuPad's loader failing (no node, or no
  recording of its app). Nothing is written.
- 3: the search is stuck: no claim proved and no proof timed out.
- 4: a hint was not proved.
- 5: a time limit stopped it before a verdict: the uniqueness check timed out
  (`checks.json` says so; nothing is searched), the stored-solution check or
  proving the step record again timed out (nothing is written), or the search
  found no step but some proof timed out (`steps.json` holds the stuck point
  and the timeouts; a higher `--proof-limit` may go on).
"""

import argparse
import json
import os
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
        except OSError as e:
            raise ValueError(f"cannot read {source}: {e.strerror}") from e
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
    try:
        puzzle = sudokupad_codec.read_puzzle(source)
    except RuntimeError as e:
        raise ValueError(f"SudokuPad's loader failed on {source[:60]!r}: {e}") from e
    return sudokupad_import.rules_file(puzzle)


def _image_src(image, output):
    """`image` as the HTML in `output` reaches it."""
    if image is None or "://" in image or not Path(image).exists():
        return image
    return os.path.relpath(Path(image).resolve(), output.resolve())


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
    path = args.output / "steps.json"
    try:
        rules = _read(args.input)
        hint = _hint(args)
        record = step_search.load_record(path)
        search = step_search.Search(rules, record, path, args.proof_limit)
        if hint is not None:
            search.check_hint(hint, args.named)
        checks = rules_file.check(rules, args.time_limit)
    except ValueError as e:
        print(f"solve-guide: {e}", file=sys.stderr)
        return 2
    except TimeoutError as e:
        print(f"solve-guide: {e}", file=sys.stderr)
        return 5
    image = _image_src(args.image, args.output)
    args.output.mkdir(parents=True, exist_ok=True)
    _write(args.output / "rules.json", rules)
    _write(args.output / "checks.json", checks)
    (args.output / "render.html").write_text(guide_html.plain_page(rules, image))
    unique, fits = checks["unique"], checks["solution_fits"]
    print(f"unique: {unique['status']}")
    if fits["passed"] is None:
        print("solution fits: no stored solution")
    else:
        print(f"solution fits: {'yes' if fits['passed'] else 'no'}")
        for name in fits["failing"]:
            print(f"  the stored solution breaks {name}")
    if unique["status"] == "timeout":
        print(f"the uniqueness check hit --time-limit {args.time_limit}s: no verdict")
        return 5
    if not rules_file.passed(checks):
        return 1
    if hint is not None:
        result = search.hint(hint, args.named)
        if result.status != "proved":
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
    if outcome == "timeout":
        print(
            f"{record['stuck']['timeouts']} proofs hit --proof-limit "
            f"{args.proof_limit}s: no verdict on whether a step exists"
        )
    (args.output / "guide.html").write_text(guide_html.guide_page(rules, record, image))
    return {"stuck": 3, "timeout": 5}.get(outcome, 0)


def _hint(args):
    """The hint's claim, or None when there is none."""
    if args.hint is None:
        if args.named:
            raise ValueError("--named is given with no --hint")
        return None
    return step_search.claim_from_json(_hint_json(args.hint))


def _hint_json(text):
    try:
        return json.loads(text)
    except ValueError as e:
        raise ValueError(f"hint {text[:60]!r} is not JSON: {e}") from e


if __name__ == "__main__":
    sys.exit(main())
