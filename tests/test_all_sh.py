"""`tests/all.sh`, the seam runner, driven against a stub `uv` on PATH.

The script runs from a copy in a temp tree so its `cd ..` lands there, and the
stub `uv` records each call and fails the one named by `FAIL_ON`. The real
suites never run, so these tests cannot recurse into pytest.
"""

import os
import shutil
import stat
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).with_name("all.sh")
SUITES = [
    "uv run ruff check",
    "uv run ruff format --check",
    "uv run shellcheck --severity=error tests/all.sh",
    "uv lock --check",
    "uv run pytest -q",
]
STUB_UV = """#!/usr/bin/env bash
echo "$*" >>"$CALLS"
if [ "$*" = "$FAIL_ON" ]; then echo "stub output for $*" >&2; exit 1; fi
"""


@pytest.fixture
def seam(tmp_path):
    (tmp_path / "tests").mkdir()
    shutil.copy(SCRIPT, tmp_path / "tests" / "all.sh")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    uv = bin_dir / "uv"
    uv.write_text(STUB_UV)
    uv.chmod(uv.stat().st_mode | stat.S_IEXEC)
    calls = tmp_path / "calls"
    calls.touch()

    def run(*args, fail_on=""):
        env = {
            **os.environ,
            "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
            "CALLS": str(calls),
            "FAIL_ON": fail_on,
        }
        return subprocess.run(
            ["bash", str(tmp_path / "tests" / "all.sh"), *args],
            capture_output=True,
            text=True,
            env=env,
            check=False,
            timeout=30,
        )

    run.calls = lambda: calls.read_text().splitlines()
    return run


def test_a_green_run_passes_every_suite_and_counts_them(seam):
    done = seam()
    assert done.returncode == 0
    assert done.stdout.splitlines() == [
        *(f"PASS {s}" for s in SUITES),
        "5 of 5 suites passed",
    ]


def test_a_failing_suite_prints_its_output_and_stops_the_run(seam):
    done = seam(fail_on="lock --check")
    assert done.returncode == 1
    assert "FAIL uv lock --check\nstub output for lock --check" in done.stdout
    assert done.stdout.splitlines()[-1] == (
        "3 of 5 suites passed, 1 failed: uv lock --check"
    )
    assert "run pytest -q" not in seam.calls()


def test_list_prints_the_five_suites_and_runs_none(seam):
    done = seam("--list")
    assert done.returncode == 0
    assert done.stdout.splitlines() == SUITES
    assert seam.calls() == []


def test_changed_runs_the_whole_seam_and_says_it_widened(seam):
    done = seam("--changed", "origin/main")
    assert done.returncode == 0
    assert len(seam.calls()) == 5
    assert done.stdout.splitlines()[-1] == (
        "5 of 5 suites passed (widened: the whole suite runs in seconds)"
    )


def test_a_failing_shellcheck_fails_the_seam(seam):
    cmd = "run shellcheck --severity=error tests/all.sh"
    done = seam(fail_on=cmd)
    assert done.returncode == 1
    assert f"FAIL uv {cmd}" in done.stdout
    assert done.stdout.splitlines()[-1] == (
        f"2 of 5 suites passed, 1 failed: uv {cmd}"
    )


def test_shellcheck_covers_every_tracked_shell_file():
    root = SCRIPT.parent.parent
    tracked = subprocess.run(
        ["git", "ls-files", "*.sh"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    listed = subprocess.run(
        ["bash", str(SCRIPT), "--list"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.splitlines()
    covered = next(s for s in listed if "shellcheck" in s).split()
    assert tracked
    assert set(tracked) <= set(covered)


@pytest.mark.parametrize(
    "args",
    [
        ["--bogus"],
        ["--changed"],
        ["--changed", ""],
        ["--changed", "--list"],
        ["--list", "x"],
    ],
)
def test_a_bad_flag_exits_2_with_a_usage_line(seam, args):
    done = seam(*args)
    assert done.returncode == 2
    assert "usage: tests/all.sh [--list] [--changed <base>]" in done.stderr
    assert seam.calls() == []
