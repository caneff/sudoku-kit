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
