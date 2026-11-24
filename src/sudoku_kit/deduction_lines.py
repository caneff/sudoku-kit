"""The step record as one line per deduction, for the `/solve-guide` skill to
read before it writes the guide file (spec #127):

    python -m sudoku_kit.deduction_lines <output directory>

The directory is a `solve-guide` output directory: it reads `rules.json` and
`steps.json`. Each line is `D<k> (steps <numbers>): <changes>, from <constraints>.`
with the deductions of `guide_html.deductions` in guide order, so every step
of the record appears on exactly one line. The changes are the guide's step
lines' words (`guide_html.describe_steps`: the digits a cell loses, or the
digit it is), each loss followed by what its cells have left
(`r2c4 loses 6 (left: 1 2 3 4 5)`), and the constraints are `guide_html.named_words`, never a clue
id.

Exit codes: 0 printed, 2 `rules.json` or `steps.json` missing, unreadable or
malformed: a rules file `rules_file.load` refuses, or a step record whose
steps lack a claim `step_search` reads or a `named` list of constraints
`rules.json` holds.
"""

import argparse
import sys
from pathlib import Path

from sudoku_kit import guide_html, rules_file, step_search


def lines(rules, record):
    """One line per deduction of `record`, in guide order."""
    out = []
    before = guide_html.states(rules, record)
    for k, group in enumerate(guide_html.deductions(rules, record), 1):
        steps = ", ".join(map(str, group["steps"]))
        changes = guide_html.describe_steps(record, before, group["steps"], left=True)
        named = guide_html.named_words(rules, group["named"])
        label = "steps" if len(group["steps"]) > 1 else "step"
        out.append(f"D{k} ({label} {steps}): {changes}, from {named}.")
    return out


def _record(path, rules):
    """The step record at `path`, refused, naming the step, when a step has
    no claim `step_search` reads or names a constraint `rules` lacks."""
    record = rules_file.read_json(path)
    if not isinstance(record, dict) or not isinstance(record.get("steps"), list):
        raise ValueError(f"{path} has no steps list")
    names = set(rules_file.registry(rules))
    for k, step in enumerate(record["steps"], 1):
        if not isinstance(step, dict):
            raise ValueError(f"{path} step {k} is not a JSON object")
        try:
            step_search.claim_from_json(step.get("claim"))
        except ValueError as e:
            raise ValueError(f"{path} step {k}: {e}") from e
        named = step.get("named")
        if not isinstance(named, list) or not named:
            raise ValueError(f"{path} step {k} has no named list of constraints")
        unknown = [name for name in named if name not in names]
        if unknown:
            raise ValueError(f"{path} step {k} names {unknown}, not in rules.json")
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(prog="solve-deductions", description=__doc__)
    parser.add_argument("directory", type=Path, help="a solve-guide output directory")
    args = parser.parse_args(argv)
    try:
        rules = rules_file.load(args.directory / "rules.json")
        record = _record(args.directory / "steps.json", rules)
        text = lines(rules, record)
    except ValueError as e:
        print(f"solve-deductions: {e}", file=sys.stderr)
        return 2
    print("\n".join(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
