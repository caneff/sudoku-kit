# The gate CI runs, at the .python-version floor here and also on the newest Python in CI.
check:
    bash tests/all.sh

# Lint with auto-fix, then format.
fmt:
    uv run ruff check --fix
    uv run ruff format
