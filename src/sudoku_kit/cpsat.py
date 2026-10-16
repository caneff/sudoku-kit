"""The CP-SAT calls the generators and uniqueness proofs all make.

The configuration is the part worth stating once, because a solver is asked
for two different things:

- **A committed proof** takes `solver(limit)` -- one worker, seed 0,
  reproducible run to run. CP-SAT's parallel portfolio races its workers, so
  which solution comes back depends on thread timing, and a check that
  regenerates a committed result and diffs it then compares noise. One worker
  is slower, and that is the price of a verdict that means the same thing
  twice.
- **A search for a fresh grid** takes `solver(limit, reproducible=False,
  seed=..., randomize=True)` -- the full portfolio, the caller's seed. Nothing
  downstream re-derives that grid; the caller saves it and proves it from
  the saved copy.

A proof too large for one worker inside any usable limit takes the portfolio
anyway, and its caller says so where the proof is committed.
"""

from ortools.sat.python import cp_model

SOLVED = (cp_model.OPTIMAL, cp_model.FEASIBLE)

# No verdict: the search hit its time cap. Re-exported so a caller reads its
# own solve status without importing cp_model beside this module.
UNKNOWN = cp_model.UNKNOWN

# The portfolio width the sampling searches run at. Not the core count: these
# runs share the machine with other work.
SEARCH_WORKERS = 8


def solver(limit, reproducible=True, seed=0, randomize=False, workers=None):
    """A CpSolver capped at `limit` seconds.

    Reproducible by default: one worker and seed 0, so the same model gives
    the same answer on every run. `reproducible=False` opens the portfolio and
    takes the caller's `seed`, with `randomize` steering the search away from
    the dull grids the default order keeps returning.

    `workers` overrides the thread count in either configuration. More than
    one worker races CP-SAT's portfolio, so a reproducible solver given
    several keeps seed 0 but is not run-to-run stable: the same model can
    return a different solution each time.
    """
    if reproducible and (seed or randomize):
        raise ValueError("a reproducible solver takes no seed and no randomize")
    s = cp_model.CpSolver()
    s.parameters.max_time_in_seconds = limit
    if workers is None:
        workers = 1 if reproducible else SEARCH_WORKERS
    s.parameters.num_workers = workers
    s.parameters.random_seed = 0 if reproducible else seed
    s.parameters.randomize_search = randomize
    return s


def forbid(m, x, assignment, tag=""):
    """Rule `assignment` out of model `m`: some cell must differ from it.

    `x` maps a cell to its variable, keyed however the caller keys cells --
    (row, column) pairs in the generators, board indices in a link check. Only
    the cells `assignment` names are constrained. `tag` distinguishes the
    literals when one model is forbidden more than once; CP-SAT does not
    require distinct names, but a duplicate makes the model unreadable in a
    dump.
    """
    lits = []
    for cell, v in assignment.items():
        b = m.NewBoolVar(f"d{tag}_{cell}")
        m.Add(x[cell] != v).OnlyEnforceIf(b)
        m.Add(x[cell] == v).OnlyEnforceIf(b.Not())
        lits.append(b)
    m.AddBoolOr(lits)


def _check_status(status, limit, m):
    """Raise for a status that is no verdict: a spent cap or a broken model."""
    if status == cp_model.UNKNOWN:
        raise TimeoutError(f"CP-SAT hit the {limit}s limit; no verdict")
    if status == cp_model.MODEL_INVALID:
        raise ValueError(f"CP-SAT rejected the model as invalid: {m.Validate()}")


def has_second_solution(m, x, first, limit, reproducible=True):
    """True when `m` has a solution other than `first`, False when it has none.

    Raises TimeoutError when the search hits `limit` without a verdict -- a
    timeout is never reported as "no second solution", which is the one way a
    uniqueness proof can lie. Raises ValueError when CP-SAT rejects `m` as
    invalid (MODEL_INVALID): a broken model is not "no second solution".
    Forbids `first` on `m` in place, so the model is
    spent afterwards.
    """
    forbid(m, x, first)
    status = solver(limit, reproducible=reproducible).Solve(m)
    _check_status(status, limit, m)
    return status in SOLVED


def boxes(n, height, width):
    """The box houses of an n x n board, as cell lists of `height` x `width`.

    A 6x6 board with boxes two rows tall and three columns wide is
    `boxes(6, 2, 3)`. Raises ValueError when height x width is not n, or
    either is not positive: a box that holds fewer cells than n is a weaker
    rule than sudoku, and one that does not tile the board leaves cells
    outside every box.
    """
    if height < 1 or width < 1 or height * width != n:
        raise ValueError(f"{height}x{width} boxes do not hold {n} cells")
    return [
        [(br + dr, bc + dc) for dr in range(height) for dc in range(width)]
        for br in range(0, n, height)
        for bc in range(0, n, width)
    ]


def sudoku_model(n, regions):
    """(m, x) for an n x n board: digits 1..n, rows and columns distinct.

    `x` maps (row, column) to its variable. `regions`, a list of cell lists,
    are the houses posted beside the rows and columns: `boxes(n, h, w)` for a
    sudoku, `()` for a plain Latin square. Givens and every other rule are the
    caller's to post on `m`.
    """
    m = cp_model.CpModel()
    x = {(r, c): m.NewIntVar(1, n, f"x{r}{c}") for r in range(n) for c in range(n)}
    for i in range(n):
        m.AddAllDifferent([x[i, c] for c in range(n)])
        m.AddAllDifferent([x[r, i] for r in range(n)])
    for house in regions:
        m.AddAllDifferent([x[cell] for cell in house])
    return m, x


def solve_unique(m, x, limit, reproducible=True):
    """(first, is_unique) for model `m` whose cell variables are `x`.

    `first` is a solution as {cell: digit}, or None when `m` has none, in which
    case is_unique is False. Raises TimeoutError when either solve spends
    `limit` without a verdict: a timeout is "don't know", never "infeasible"
    and never "unique". Raises ValueError when either solve meets a model
    CP-SAT rejects as invalid (MODEL_INVALID), which is no "infeasible" either.
    Spends `m`, as has_second_solution does.
    """
    s = solver(limit, reproducible=reproducible)
    status = s.Solve(m)
    _check_status(status, limit, m)
    if status not in SOLVED:
        return None, False
    first = {k: s.Value(v) for k, v in x.items()}
    return first, not has_second_solution(m, x, first, limit, reproducible)
