"""The plain reason sentence under each deduction of the solve guide (#129).

`TEMPLATES` has one function per rule type of `clue_rules.RULES`; each takes a
clue and returns a clause saying why the clue's rule holds, naming its cells
and never its id. `house` does the same for a row, column or region.
`reason(rules, named)` joins the clauses of a deduction's named constraints
into one sentence.
"""

from sudoku_kit import rules_file


def _cells(clue):
    return [rules_file.cell_name(c) for c in clue["cells"]]


def _list(names):
    return ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]


def _ends(clue):
    cells = _cells(clue)
    return cells[0], cells[-1]


def difference(clue):
    a, b = _cells(clue)
    return f"{a} and {b} differ by {clue['values'][0]}"


def ratio(clue):
    a, b = _cells(clue)
    return f"one of {a} and {b} is {clue['values'][0]} times the other"


def thermo(clue):
    first, last = _ends(clue)
    return f"digits rise from the bulb {first} to {last} along its thermometer"


def slow_thermo(clue):
    first, last = _ends(clue)
    return f"digits never fall from the bulb {first} to {last} along its thermometer"


def renban(clue):
    return f"{_list(_cells(clue))} hold different, consecutive digits"


def whisper(clue):
    first, last = _ends(clue)
    return (
        f"neighbours on the line from {first} to {last} differ by "
        f"at least {clue['values'][0]}"
    )


def lockout(clue):
    first, last = _ends(clue)
    return (
        f"{first} and {last} differ by at least {clue['values'][0]}, and "
        "every cell between them lies outside their digits"
    )


def arrow(clue):
    cells = _cells(clue)
    width = clue["values"][0]
    return (
        f"the digits of {_list(cells[width:])} add up to "
        f"the number in {_list(cells[:width])}"
    )


def killer_cage(clue):
    return (
        f"{_list(_cells(clue))} hold different digits adding up to {clue['values'][0]}"
    )


def little_killer(clue):
    return f"the digits of {_list(_cells(clue))} add up to {clue['values'][0]}"


def skyscraper(clue):
    outside, *line = _cells(clue)
    return (
        f"{outside} counts the digits of {_list(line)} that stand taller "
        "than every digit before them"
    )


def numbered_rooms(clue):
    outside, near, *_ = _cells(clue)
    return (
        f"{outside} is the digit that {near} names the position of, "
        "counting from the clue"
    )


def _differ(clue):
    a, b = _cells(clue)
    return f"{a} and {b} cannot hold the same digit"


def anti_knight(clue):
    a, b = _cells(clue)
    return f"{a} and {b} are a knight's move apart, so they differ"


def tessellation(clue):
    a, b = _cells(clue)
    return f"{a} and {b} share an edge, so they differ"


def consecutive_set(clue):
    return f"{_list(_cells(clue))} hold different digits that run consecutively"


TEMPLATES = {
    "difference": difference,
    "ratio": ratio,
    "thermo": thermo,
    "slow_thermo": slow_thermo,
    "renban": renban,
    "whisper": whisper,
    "lockout": lockout,
    "arrow": arrow,
    "killer_cage": killer_cage,
    "little_killer": little_killer,
    "skyscraper": skyscraper,
    "numbered_rooms": numbered_rooms,
    "anti_knight": anti_knight,
    "tessellation": tessellation,
    "consecutive_set": consecutive_set,
}


def house(name):
    """The clause for a row, column or region, named like `row 3`."""
    return f"{name} holds each digit once"


def reason(rules, named):
    """One sentence: why the deduction holds, from its named constraints."""
    houses = rules_file.house_names(rules)
    clues = {clue["id"]: clue for clue in rules["clues"]}
    clauses = [
        house(name) if name in houses else TEMPLATES[clues[name]["rule"]](clues[name])
        for name in named
    ]
    return f"This holds because {_list(clauses)}."
