"""The solve-guide command line:

    python -m sudoku_kit.solve_guide <input> <output directory>

`<input>` is a SudokuPad link, short id, encoded string or link file, or a
`.json` file holding the puzzle JSON `sudokupad_codec.read_puzzle` returns
(each imported by `sudokupad_import`), or a `.json` rules file. A `.json`
holding `cells` is puzzle JSON; one holding `size` is a rules file. Writes
`rules.json` and `checks.json` (`rules_file.check`) into the output
directory. Exits 0 when every check that ran passed, 1 when one failed, and 2
when the input cannot be read or imported, writing nothing.
"""

import argparse
import json
import sys
from pathlib import Path

from sudoku_kit import rules_file, sudokupad_codec, sudokupad_import


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
        "--time-limit", type=float, default=60.0, help="seconds per solve"
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
    unique, fits = checks["unique"], checks["solution_fits"]
    print(f"unique: {unique['status']}")
    if fits["passed"] is None:
        print("solution fits: no stored solution")
    else:
        print(f"solution fits: {'yes' if fits['passed'] else 'no'}")
        for name in fits["failing"]:
            print(f"  the stored solution breaks {name}")
    return 0 if rules_file.passed(checks) else 1


if __name__ == "__main__":
    sys.exit(main())
