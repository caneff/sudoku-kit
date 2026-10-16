# Two uniqueness proofs, two contracts

`cpsat.solve_unique` and `uniqueness.check_uniqueness` both run the same proof: solve, forbid the first solution, solve again. We keep both, because their contracts differ on purpose. `solve_unique` raises on a timeout, spends the caller's model, and runs under `cpsat.solver`'s reproducible configuration (one worker, seed 0), so the generators that commit a proof get the same solution every run. `check_uniqueness` reports a timeout as a status, works on a clone so a clue-stripping loop can reuse one model, and runs under CP-SAT's default seed (1). Folding one into the other would change the solutions `check_uniqueness` returns to its callers in grid-hunts and sudokumaker-custom-constraints, or make `solve_unique` pay for a clone it never needed.

The rule both must keep is the one that let them drift: a timeout or an invalid model is never a verdict (CODING_STANDARDS.md rule 3). A fix to how either proof reads a solve status is checked against the other.

Decided in the 2026-10-16 audit sweep, after improve-codebase-architecture and thermo-nuclear-code-quality-review proposed folding them and ponytail-audit proposed keeping both.
