# Lint and every test: the gate CI runs.
check:
    uv run ruff check
    uv run ruff format --check
    uv run pytest -q

# Lint with auto-fix, then format.
fmt:
    uv run ruff check --fix
    uv run ruff format
