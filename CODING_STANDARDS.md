# Coding standards

Conventions this repo keeps that no gate checks. `ruff check`, `ruff format`
and `pytest` already enforce style, imports and the lint rules in `ruff.toml`;
nothing here restates them.

1. **Raise a built-in `ValueError` or `TimeoutError` whose message names the
   offending input.** Callers catch built-in types and show the message to a
   person reading a failed link or solve. A custom exception class slips past
   an `except ValueError`, and a message without the bad value
   (`"invalid link"` instead of the link's first 60 characters, or the file
   that was empty) leaves that person nothing to fix.

2. **An encoder decodes its own output and compares it with the input document
   before returning it.** Compare against the document itself, never a copy
   rewritten through JSON: int keys and NaN survive the rewrite and break the
   link. A link that does not decode back to its document carries a
   different puzzle, and nothing downstream notices.

3. **A timeout is never a verdict.** A solve entry point that hits its time
   limit raises `TimeoutError` or returns status `"timeout"`, never "unique",
   "not unique" or "infeasible". A timed-out search reported as a verdict
   gets published as a proven property of a puzzle it never proved.

4. **Force a timeout in a test with `time_limit=0.0`, never a short real
   limit.** A 1 ms limit is a race the solver sometimes wins, so the test
   passes or fails by machine load and the timeout branch goes unwitnessed
   on a fast run.
