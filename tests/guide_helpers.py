"""What the guide tests share: `TOY`, a made-up 4x4 board with three dots,
and the builders of a step and a step record on it written by hand."""

TOY = {
    "size": 4,
    "regions": [
        [[0, 0], [0, 1], [1, 0], [1, 1]],
        [[0, 2], [0, 3], [1, 2], [1, 3]],
        [[2, 0], [2, 1], [3, 0], [3, 1]],
        [[2, 2], [2, 3], [3, 2], [3, 3]],
    ],
    "givens": [],
    "clues": [
        {
            "id": "white-a",
            "rule": "difference",
            "cells": [[0, 0], [0, 1]],
            "values": [1],
        },
        {
            "id": "white-b",
            "rule": "difference",
            "cells": [[2, 2], [2, 3]],
            "values": [1],
        },
        {"id": "black-a", "rule": "ratio", "cells": [[3, 0], [3, 1]], "values": [2]},
    ],
}


def cell_name(cell):
    return f"r{cell[0] + 1}c{cell[1] + 1}"


def make_step(named, cell, digits):
    """A made-up step on the 4x4 `TOY`: the cell keeps `digits`."""
    return {
        "claim": {"cell": list(cell), "digits": digits},
        "named": named,
        "hard": len(named) > 3,
        "by": "search",
    }


def make_record(*steps):
    return {"steps": list(steps), "timeouts": [], "stuck": None}


def key_entry(first, last, heading="An idea", paragraphs=("Why it holds.",), **extra):
    return {
        "type": "key",
        "first": first,
        "last": last,
        "heading": heading,
        "paragraphs": list(paragraphs),
        **extra,
    }


def fill_entry(first, last, sentence="The grid fills on."):
    return {"type": "fill", "first": first, "last": last, "sentence": sentence}


def guide_file(*entries):
    return {"version": 1, "entries": list(entries)}


SIX = [
    make_step(["row 1"], (0, 2), [1, 2, 3]),
    make_step(["white-a"], (0, 0), [1, 2, 3]),
    make_step(["row 2", "column 3"], (1, 2), [1, 2]),
    make_step(["black-a"], (3, 0), [1, 2, 4]),
    make_step(["white-b"], (2, 2), [1, 2, 3]),
    make_step(["white-b", "row 3", "column 3", "region 4"], (2, 3), [2, 3]),
]
