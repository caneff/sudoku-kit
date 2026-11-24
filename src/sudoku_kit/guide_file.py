"""The guide file, version 1 (`docs/guide-file.md`): the words of a solve
guide, which the `/solve-guide` skill writes and `guide_html` draws (spec
#127).

`parse(rules, guide)` refuses, naming the problem, a guide file whose shape is
wrong whatever the step record holds: not version 1, an unknown or missing
field, a field of the wrong kind, a run that ends before it starts, an
`explains` step outside its run, a mark, supposition or early removal naming
a cell outside `rules`' grid, or more than one break-in. It needs only the rules file, so the
command line refuses such a file before the search. `check(rules, record,
guide)` also refuses one that skips, repeats or reorders a step of `record`,
or reaches past its last step, and a key idea's early removal (#147) that is
not a candidate after the idea's steps and the early removals before it, or
that is the cell's solution digit (`_known_solution`), naming the key idea,
cell and digit. Both return the guide with its cell names read
as (row, column) cells: each mark's `from`, `to` or `cell`, and a supposition
as `{"assume": (cell, digit), "forces": [(cell, digit)], "breaks": [cell]}`,
and `early_removals` as a list of (cell, digit) pairs in file order.
"""

import itertools
import re

from sudoku_kit import rules_file, step_search

VERSION = 1
ENTRY_FIELDS = {
    "key": (
        {"heading", "paragraphs"},
        {"break_in", "early_removals", "explains", "marks", "supposition"},
    ),
    "fill": ({"sentence"}, set()),
}
MARK_CELLS = {
    "arrow": ("from", "to"),
    "circle": ("cell",),
    "label": ("cell",),
    "highlight": ("cell",),
}
SUPPOSITION_FIELDS = {"assume", "forces", "breaks"}
CELL_NAME = re.compile(r"r([1-9][0-9]*)c([1-9][0-9]*)")


def join_words(words):
    return ", ".join(words[:-1]) + " and " + words[-1] if len(words) > 1 else words[0]


def plural(count, word):
    return f"{count} {word}" + ("" if count == 1 else "s")


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def _cell(name, where, board):
    """The cell `name` (`r<row>c<column>`) names, refused unless on `board`."""
    found = CELL_NAME.fullmatch(name) if isinstance(name, str) else None
    if not found:
        raise ValueError(f"{where} has {name!r}, not a cell name")
    cell = (int(found[1]) - 1, int(found[2]) - 1)
    if cell not in board:
        raise ValueError(f"{where} names {name}, outside the grid")
    return cell


def _marks(k, marks, board):
    if not isinstance(marks, list):
        raise ValueError(f"entry {k}'s marks is not a list")
    out = []
    for m, mark in enumerate(marks, 1):
        if not isinstance(mark, dict):
            raise ValueError(f"entry {k}'s mark {m} is not a JSON object")
        kind = mark.get("type")
        if kind not in MARK_CELLS:
            raise ValueError(
                f"entry {k}'s mark {m} has type {kind!r}; a mark is one of "
                f"{', '.join(map(repr, MARK_CELLS))}"
            )
        wanted = {"type", *MARK_CELLS[kind]} | ({"text"} if kind == "label" else set())
        if set(mark) - wanted:
            raise ValueError(
                f"entry {k}'s mark {m} ({kind}) has unknown fields "
                f"{sorted(set(mark) - wanted)}"
            )
        if kind == "label" and not isinstance(mark.get("text"), str):
            raise ValueError(f"entry {k}'s mark {m} (label) has no text string")
        out.append(
            mark
            | {
                field: _cell(mark.get(field), f"entry {k}'s mark {m} {field}", board)
                for field in MARK_CELLS[kind]
            }
        )
    return out


def _supposed_digit(k, item, board, size):
    if not isinstance(item, dict) or set(item) != {"cell", "digit"}:
        raise ValueError(
            f"entry {k}'s supposition has {str(item)[:60]!r}, not a cell and a digit"
        )
    cell = _cell(item["cell"], f"entry {k}'s supposition", board)
    digit = item["digit"]
    if not _is_int(digit) or not 1 <= digit <= size:
        raise ValueError(
            f"entry {k}'s supposition has digit {digit!r} for {item['cell']}, "
            f"not 1-{size}"
        )
    return cell, digit


def _supposition(k, sup, board, size):
    if not isinstance(sup, dict):
        raise ValueError(f"entry {k}'s supposition is not a JSON object")
    unknown = set(sup) - SUPPOSITION_FIELDS
    if unknown:
        raise ValueError(
            f"entry {k}'s supposition has unknown fields {sorted(unknown)}"
        )
    missing = SUPPOSITION_FIELDS - set(sup)
    if missing:
        raise ValueError(f"entry {k}'s supposition has no {sorted(missing)}")
    if not isinstance(sup["forces"], list) or not isinstance(sup["breaks"], list):
        raise ValueError(f"entry {k}'s supposition forces and breaks are not lists")
    if not sup["breaks"]:
        raise ValueError(
            f"entry {k}'s supposition breaks is empty; name the cells it clashes at"
        )
    return {
        "assume": _supposed_digit(k, sup["assume"], board, size),
        "forces": [_supposed_digit(k, f, board, size) for f in sup["forces"]],
        "breaks": [_cell(b, f"entry {k}'s supposition", board) for b in sup["breaks"]],
    }


def _early_removals(k, removals, board, size):
    """The (cell, digit) pairs of `removals`, in file order."""
    if not isinstance(removals, list):
        raise ValueError(f"entry {k}'s early_removals is not a list")
    out = []
    for item in removals:
        if not isinstance(item, dict) or set(item) != {"cell", "digits"}:
            raise ValueError(
                f"entry {k}'s early removal {str(item)[:60]!r} is not a cell and "
                "its digits"
            )
        cell = _cell(item["cell"], f"entry {k}'s early removal", board)
        digits = item["digits"]
        if not isinstance(digits, list) or not digits:
            raise ValueError(
                f"entry {k}'s early removal from {item['cell']} has no digits list"
            )
        for digit in digits:
            if not _is_int(digit) or not 1 <= digit <= size:
                raise ValueError(
                    f"entry {k}'s early removal has digit {digit!r} for "
                    f"{item['cell']}, not 1-{size}"
                )
            out.append((cell, digit))
    return out


def _explains(k, entry):
    steps = entry["explains"]
    if not isinstance(steps, list) or not all(_is_int(s) for s in steps):
        raise ValueError(f"entry {k}'s explains is not a list of step numbers")
    if not steps:
        raise ValueError(f"entry {k}'s explains is empty; omit it to explain the run")
    for step in steps:
        if not entry["first"] <= step <= entry["last"]:
            raise ValueError(
                f"entry {k} explains step {step}, outside its run, "
                f"steps {entry['first']}-{entry['last']}"
            )
    for step in set(steps):
        if steps.count(step) > 1:
            raise ValueError(f"entry {k}'s explains repeats step {step}")


def _entry(k, entry, board, size):
    if not isinstance(entry, dict):
        raise ValueError(f"entry {k} is not a JSON object: {str(entry)[:60]!r}")
    kind = entry.get("type")
    if kind not in ENTRY_FIELDS:
        raise ValueError(f"entry {k} has type {kind!r}; an entry is 'key' or 'fill'")
    required, optional = ENTRY_FIELDS[kind]
    required = required | {"first", "last"}
    unknown = set(entry) - required - optional - {"type"}
    if unknown:
        raise ValueError(f"entry {k} ({kind}) has unknown fields {sorted(unknown)}")
    missing = required - set(entry)
    if missing:
        raise ValueError(f"entry {k} ({kind}) has no {sorted(missing)}")
    for field in ("first", "last"):
        if not _is_int(entry[field]):
            raise ValueError(
                f"entry {k}'s {field} {entry[field]!r} is not a step number"
            )
    first, last = entry["first"], entry["last"]
    if first < 1:
        raise ValueError(f"entry {k} starts at step {first}; steps count from 1")
    if first > last:
        raise ValueError(f"entry {k} has its first {first} after its last {last}")
    for field in ("heading", "sentence"):
        if field in entry and not isinstance(entry[field], str):
            raise ValueError(f"entry {k}'s {field} is not a string")
    paragraphs = entry.get("paragraphs", [])
    if not isinstance(paragraphs, list) or not all(
        isinstance(p, str) for p in paragraphs
    ):
        raise ValueError(f"entry {k}'s paragraphs is not a list of strings")
    if not isinstance(entry.get("break_in", False), bool):
        raise ValueError(f"entry {k}'s break_in is not true or false")
    if "explains" in entry:
        _explains(k, entry)
    parsed = dict(entry)
    if "marks" in entry:
        parsed["marks"] = _marks(k, entry["marks"], board)
    if "supposition" in entry:
        parsed["supposition"] = _supposition(k, entry["supposition"], board, size)
    if "early_removals" in entry:
        parsed["early_removals"] = _early_removals(
            k, entry["early_removals"], board, size
        )
    return parsed


def parse(rules, guide):
    """`guide` with its cells read, refused, naming the problem, when its shape
    is wrong whatever the step record holds."""
    if not isinstance(guide, dict):
        raise ValueError(f"the guide file is not a JSON object: {str(guide)[:60]!r}")
    version = guide.get("version")
    if not _is_int(version) or version != VERSION:
        raise ValueError(
            f"the guide file has version {version!r}; only version {VERSION} is read"
        )
    entries = guide.get("entries")
    if not isinstance(entries, list):
        raise ValueError("the guide file has no entries list")
    board = set(rules_file.cells(rules))
    parsed = [_entry(k, e, board, rules["size"]) for k, e in enumerate(entries, 1)]
    flagged = [str(k) for k, e in enumerate(parsed, 1) if e.get("break_in")]
    if len(flagged) > 1:
        raise ValueError(
            f"entries {join_words(flagged)} each flag the break-in; a guide has one at most"
        )
    return guide | {"entries": parsed}


def states(rules, record):
    """The candidates before each step, by step number from 1, and after the
    last step under the number past it."""
    state = step_search.State(rules)
    before = {}
    for i, step in enumerate(record["steps"], 1):
        before[i] = dict(state.candidates)
        state.apply(step_search.claim_from_json(step["claim"]))
    before[len(record["steps"]) + 1] = dict(state.candidates)
    return before


def _known_solution(rules, final):
    """{cell: digit} of the solution as far as it is known: the rules file's
    stored solution, else each cell `final`, the record's last candidates,
    has solved."""
    known = {cell: next(iter(ds)) for cell, ds in final.items() if len(ds) == 1}
    stored = rules.get("solution")
    if stored is not None:
        known |= {
            (r, c): d
            for r, row in enumerate(stored)
            for c, d in enumerate(row)
            if d is not None
        }
        known |= {
            tuple(o["cell"]): o["digit"] for o in rules.get("solution_outside") or []
        }
    return known


def _check_early_removals(rules, record, entries):
    """Refuse, naming the key idea, cell and digit, an early removal that is
    not a candidate after its idea's steps and the early removals before it,
    or that is the cell's solution digit."""
    before = states(rules, record)
    solution = _known_solution(rules, before[len(record["steps"]) + 1])
    gone, key = {}, 0
    for k, entry in enumerate(entries, 1):
        if entry["type"] != "key":
            continue
        key += 1
        after = before[entry["last"] + 1]
        for cell, digit in entry.get("early_removals", []):
            name = rules_file.cell_name(cell)
            where = f"key idea {key} (entry {k}) removes {digit} from {name} early"
            if digit not in after[cell] - gone.get(cell, set()):
                raise ValueError(
                    f"{where}, but {digit} is not a candidate there after the "
                    "idea's steps and the early removals before it"
                )
            if cell not in solution:
                raise ValueError(
                    f"{where}, but the solution digit there is not known: the "
                    "rules file stores no solution and the step record does not "
                    "solve it"
                )
            if solution[cell] == digit:
                raise ValueError(f"{where}, but {digit} is the solution digit there")
            gone.setdefault(cell, set()).add(digit)


def check(rules, record, guide):
    """`parse`'s guide, also refused when it does not cover every step of
    `record` exactly once, in order, or an early removal does not hold."""
    guide = parse(rules, guide)
    entries, total = guide["entries"], len(record["steps"])
    covered = {}
    for k, entry in enumerate(entries, 1):
        if entry["last"] > total:
            raise ValueError(
                f"entry {k} reaches step {entry['last']}, past the record's "
                f"{plural(total, 'step')}"
            )
        for step in range(entry["first"], entry["last"] + 1):
            if step in covered:
                raise ValueError(
                    f"entry {k} repeats step {step}, already in entry {covered[step]}"
                )
            covered[step] = k
    missing = [step for step in range(1, total + 1) if step not in covered]
    if missing:
        more = f" and {len(missing) - 1} more" if len(missing) > 1 else ""
        raise ValueError(f"the guide file skips step {missing[0]}{more}")
    for k, (a, b) in enumerate(itertools.pairwise(entries), 2):
        if b["first"] < a["first"]:
            raise ValueError(
                f"entry {k} is out of order: steps {b['first']}-{b['last']} come "
                f"after steps {a['first']}-{a['last']} of entry {k - 1}"
            )
    _check_early_removals(rules, record, entries)
    return guide
