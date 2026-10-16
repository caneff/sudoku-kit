# The gate CI runs: tests/all.sh holds the suite list. `.python-version` holds
# it to the floor pyproject.toml declares; CI also runs it on the newest Python.
check:
    bash tests/all.sh

# Lint with auto-fix, then format.
fmt:
    uv run ruff check --fix
    uv run ruff format
