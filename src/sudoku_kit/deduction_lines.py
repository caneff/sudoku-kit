"""The step record as one line per deduction, for the `/solve-guide` skill to
read before it writes the guide file (spec #127):

    python -m sudoku_kit.deduction_lines <output directory>

The directory is a `solve-guide` output directory: it reads `rules.json` and
`steps.json`. Each line is `D<k> (steps <numbers>): <claims>, from <constraints>.`
with the deductions of `guide_html.deductions` in guide order, so every step
of the record appears on exactly one line. The claims are `guide_html`'s
words, joined by `;`, and the constraints are `guide_html.constraint_words`,
never a clue id.

Exit codes: 0 printed, 2 `rules.json` or `steps.json` missing or unreadable.
"""

import argparse
import json
import sys
from pathlib import Path

from sudoku_kit import guide_html


def lines(rules, record):
    """One line per deduction of `record`, in guide order."""
    out = []
    for k, group in enumerate(guide_html.deductions(rules, record), 1):
        steps = ", ".join(map(str, group["steps"]))
        claims = "; ".join(guide_html.describe_claim(c) for c in group["claims"])
        named = guide_html.join_words(
            [guide_html.constraint_words(rules, n) for n in group["named"]]
        )
        label = "steps" if len(group["steps"]) > 1 else "step"
        out.append(f"D{k} ({label} {steps}): {claims}, from {named}.")
    return out


def _load(path):
    try:
        return json.loads(path.read_text())
    except OSError as e:
        raise ValueError(f"cannot read {path}: {e.strerror}") from e
    except ValueError as e:
        raise ValueError(f"{path} is not JSON: {e}") from e


def main(argv=None):
    parser = argparse.ArgumentParser(prog="solve-deductions", description=__doc__)
    parser.add_argument("directory", type=Path, help="a solve-guide output directory")
    args = parser.parse_args(argv)
    try:
        rules = _load(args.directory / "rules.json")
        record = _load(args.directory / "steps.json")
        if not isinstance(record, dict) or not isinstance(record.get("steps"), list):
            raise ValueError(f"{args.directory / 'steps.json'} has no steps list")
        text = lines(rules, record)
    except ValueError as e:
        print(f"solve-deductions: {e}", file=sys.stderr)
        return 2
    print("\n".join(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
