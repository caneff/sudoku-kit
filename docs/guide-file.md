# The guide file, version 1

The guide file holds every word of a solve guide. The `/solve-guide` skill
writes it after reading the step record. `solve-guide --guide <file>` checks
it against the step record and draws it as `guide.html`
(`sudoku_kit.guide_html`). The library draws the grids from the step record,
so a grid never shows an elimination the search did not prove. The words can
still be wrong, but they never change what a grid shows.

A guide file for a published puzzle is a solution path. Keep it outside
this repo and never publish it (`AGENTS.md`). The example below is for an
invented board.

## Shape

A JSON object:

- `version`: `1`.
- `entries`: an ordered list. Each entry is a key idea or a fill stretch and
  covers a run of steps from `first` to `last`, both counted from 1 as the
  step record lists them. Together the entries cover every step of the record
  exactly once, in order: entry 1 starts at step 1, each entry starts at the
  step after the previous one ends, and the last entry ends at the record's
  last step. A record with no steps takes an empty list.

A **key idea** entry:

- `type`: `"key"`.
- `first`, `last`: its run of steps.
- `heading`: its heading, without a number. The library numbers key ideas
  1..N in file order and writes `Key idea <k>: <heading>`.
- `paragraphs`: a list of strings, each one paragraph of explanation.
- `break_in` (optional): `true` on the break-in. At most one entry has it;
  the library shows the break-in label on that entry.
- `explains` (optional): a non-empty list of the step numbers in the run that
  the idea explains. The grid strikes out and marks only those steps. The
  run's other steps are applied to the candidates without being drawn and
  listed under the idea in a collapsed "Also in this stretch", one line per
  step as a fill's list writes them. Omitted, the idea explains its whole run.
- `marks` (optional): extra marks drawn on the idea's grid, each an object
  with a `type` and cells named as `r<row>c<column>`:
  `{"type": "arrow", "from": "r1c1", "to": "r2c2"}`,
  `{"type": "circle", "cell": "r1c1"}`,
  `{"type": "label", "cell": "r1c1", "text": "pair"}` and
  `{"type": "highlight", "cell": "r1c1"}`.

A **fill** entry:

- `type`: `"fill"`.
- `first`, `last`: its run of steps.
- `sentence`: one sentence summing up the stretch.

The library writes the collapsed list under a fill sentence itself, one line
per step. Each line gives the claim, then its named constraints in words, such
as `r1c2 = 3, from row 1 and white dot r1c1-r1c2`.

A field the version does not name is refused, so a misspelt field fails
loudly rather than going missing from the page.

## What the library draws

- A key idea is one row: its grid on the left and its text on the right. The
  grid shows the candidates before the run's first step, strikes out what the
  run's steps remove, and marks the cells those steps use or change. It draws
  candidates only in marked cells. Every other cell shows its placed digit or
  stays blank.
- A fill stretch is its sentence over the collapsed list of step lines.
- The page opens with the title, the original image when given, the rules
  text and the starting grid. A stuck record ends with the stuck-point grid.

## Refusals

The command writes no `guide.html` and exits 2, naming the problem, when the
guide file:

- is not JSON, or is not an object with `version` 1 and an `entries` list;
- has an entry of another type, a field the type does not take, a missing
  field, or a field of the wrong kind;
- skips, repeats or reorders a step, or reaches past the record's last step;
- flags more than one break-in;
- explains a step outside its own run, or repeats one, or gives an empty list;
- has a mark of another type, a field the type does not take, or a cell
  outside the grid.

Without `--guide` the command still checks the rules file and runs the
search, but it writes no guide and says so.

## Example

For a 4x4 board whose record has five steps:

```json
{
  "version": 1,
  "entries": [
    {"type": "fill", "first": 1, "last": 2,
     "sentence": "Row 1's singles place the first two digits."},
    {"type": "key", "first": 3, "last": 4, "break_in": true,
     "heading": "The white dot on r1c1-r1c2",
     "paragraphs": [
       "The dot needs two consecutive digits.",
       "With 1 and 4 placed in the row, the pair must be 2 and 3."
     ]},
    {"type": "fill", "first": 5, "last": 5,
     "sentence": "The last cell of the box follows."}
  ]
}
```
