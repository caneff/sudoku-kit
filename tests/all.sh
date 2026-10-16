#!/usr/bin/env bash
# The gate's one listing of suites; `just check` calls this. A suite is one
# command, and it is its own label.
#
#   bash tests/all.sh [--list] [--changed <base>]
#
# `--list` prints the suites and runs none. `--changed <base>` is accepted and
# runs the whole seam, its last line saying so: the full run takes seconds, so
# a selector would be machinery with nothing to save.
#
# One line per suite as it finishes (`PASS <suite>`); a failing suite prints
# `FAIL <suite>` and its whole output, no further suite starts, and the run
# exits 1. The last line states what ran: `N of M suites passed`, or
# `N of M suites passed, 1 failed: <suite>`.
set -uf
cd "$(dirname "${BASH_SOURCE[0]}")/.." || exit 1

suites=(
  "uv run ruff check"
  "uv run ruff format --check"
  "uv lock --check"
  "uv run pytest -q"
)

usage() { # <what is wrong>
  echo "tests/all.sh: $1" >&2
  echo "usage: tests/all.sh [--list] [--changed <base>]" >&2
  exit 2
}

list_only=0 note=""
while [ $# -gt 0 ]; do
  case $1 in
    --list) list_only=1; shift ;;
    --changed)
      case ${2:-} in '' | -*) usage "$1 needs a base ref" ;; esac
      note=" (widened: the whole suite runs in seconds)"; shift 2 ;;
    *) usage "no flag named $1" ;;
  esac
done

if [ "$list_only" = 1 ]; then printf '%s\n' "${suites[@]}"; exit 0; fi

passed=0
for suite in "${suites[@]}"; do
  if out=$($suite 2>&1 </dev/null); then
    echo "PASS $suite"
    passed=$((passed + 1))
  else
    printf 'FAIL %s\n%s\n' "$suite" "$out"
    echo "$passed of ${#suites[@]} suites passed, 1 failed: $suite$note"
    exit 1
  fi
done
echo "$passed of ${#suites[@]} suites passed$note"
