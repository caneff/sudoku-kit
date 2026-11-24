# The guide file, version 1

The guide file holds every word of a solve guide. The `/solve-guide` skill
writes it after reading the step record. `solve-guide --guide <file>` checks
it against the step record and draws it as `guide.html`
(`sudoku_kit.guide_file` checks it, `sudoku_kit.guide_html` draws it). The
library draws the grids from the step record, so a grid never shows an
elimination the search did not prove. The words can still be wrong, but they
never change what a grid shows.

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
  1..N in file order and writes the number in a badge, `Key idea <k>` beside
  it, and the heading below.
- `paragraphs`: a list of strings, each one paragraph of explanation.
- `break_in` (optional): `true` on the break-in. At most one entry has it;
  the library shows the break-in label on that entry.
- `explains` (optional): a non-empty list of the step numbers in the run that
  the idea explains. The grid strikes out and marks only those steps. The
  run's other steps are taken off the idea's starting candidates without
  being drawn, whether they come before or after the explained ones, and
  listed under the idea in a collapsed "Also in this stretch", in lines
  as a fill's list writes them. Omitted, the idea explains its whole run.
- `marks` (optional): extra marks drawn on the idea's grid, each an object
  with a `type` and cells named as `r<row>c<column>`:
  `{"type": "arrow", "from": "r1c1", "to": "r2c2"}`,
  `{"type": "circle", "cell": "r1c1"}`,
  `{"type": "label", "cell": "r1c1", "text": "pair"}` and
  `{"type": "highlight", "cell": "r1c1"}`. A label never prints over a pencil
  mark: in a cell that draws pencil marks it takes the widest run of empty
  pencil-mark spots in one row, squeezed to fit, or sits just outside the
  cell when every spot is drawn.
- `supposition` (optional): the idea argues "suppose this cell were X". An
  object with `assume`, `forces` and `breaks`. `assume` is `{"cell": "r1c1",
  "digit": 4}`, a digit the idea's explained steps eliminate. `forces` is a
  list of `{"cell", "digit"}` in the order the assumption forces them (it may
  be empty). `breaks` is a non-empty list of the cells where the assumption
  clashes. The library draws a second grid beside the idea's own with no
  pencil marks: the givens, the assumed and forced digits in their own
  colour, the forced ones numbered in order, and the clash cells circled.
  Every digit drawn must be among the idea's starting candidates in its cell.
- `early_removals` (optional): digits the idea's words rule out before the
  step record does, a list of `{"cell": "r1c2", "digits": [4]}`, each a cell
  and a non-empty list of digits 1 to the board size. Each digit must be a
  candidate in its cell after the idea's run of steps, with the early
  removals before it (this idea's earlier ones and every earlier idea's)
  already taken off, and must not be the cell's solution digit: the rules
  file's stored `solution` (or `solution_outside`) when it has one, else the
  digit the step record solves the cell to. The idea's grid strikes them out
  as it strikes its explained steps' removals and marks their cells as
  changed; every later grid, the stuck-point grid included, starts without
  them, so a later step that removes the same digit draws nothing for it.

A **fill** entry:

- `type`: `"fill"`.
- `first`, `last`: its run of steps.
- `sentence`: one sentence summing up the stretch.

The library writes the collapsed list under a fill sentence itself, one line
per run of steps from the same constraints, such as
`r1c12 lose 4; r1c3 is 3, from row 1`, or from one solved cell clearing its
houses, such as `The 4 in r2c2: r2c134, r134c2 and r1c1 lose 4.` Its "Show
all N steps" button still counts the steps. Print hides the list.

A field the version does not name is refused, so a misspelt field fails
loudly rather than going missing from the page.

## What the library draws

- A key idea is one card, never split across a printed page: its grid about
  16rem wide on top and its text below, so about 1 to 2 print per A4 page. The
  grid shows the idea's starting candidates: those before the run's first
  step, less what the run's unexplained steps remove (none when it has no
  `explains`), each digit's pencil mark in the same spot in every cell. It
  strikes out what the explained steps remove (grey, with a red slash) and
  marks the
  cells those steps use or change. It also strikes out the idea's early
  removals and marks their cells, and starts without every earlier idea's. It draws candidates only in marked cells.
  Every other cell shows its placed digit or stays blank.
- A fill stretch is its sentence over the list of step lines, collapsed
  behind a "Show all N steps" button.
- The page opens with the title, the original image when given, the rules
  text and the starting grid. A stuck record ends with the stuck-point grid.

## Refusals

The command writes no `guide.html` and exits 2, naming the problem, when the
guide file fails one of the checks below. A file that is wrong whatever the
step record holds (all but the coverage, supposition-digit and early-removal
digit checks) is refused before the search; the others after it. Either way a `guide.html`
an earlier run left is removed. The guide file:

- is not JSON, or is not an object with `version` 1 (the integer) and an
  `entries` list;
- has an entry of another type, a field the type does not take, a missing
  field, or a field of the wrong kind;
- skips, repeats or reorders a step, or reaches past the record's last step;
- flags more than one break-in;
- explains a step outside its own run, or repeats one, or gives an empty list;
- has a mark of another type, a field the type does not take, or a cell
  outside the grid;
- has a supposition that is not an object with `assume`, `forces` and
  `breaks`, names a cell outside the grid or a digit outside 1 to the board
  size, or has an empty `breaks`;
- has a supposition whose assumed digit the idea's explained steps do not
  eliminate, or that draws a digit which is not among the idea's starting
  candidates in its cell. The message names the cell and digit;
- has an early removal that is not an object with `cell` and `digits`, names
  a cell outside the grid, or has an empty `digits` or a digit outside 1 to
  the board size;
- has an early removal whose digit is not a candidate in its cell after the
  idea's steps and the early removals before it, is the cell's solution
  digit, or falls in a cell whose solution digit neither the rules file nor
  the step record gives. The message names the key idea, its entry, the cell
  and the digit.

Without `--guide` the command still checks the rules file and runs the
search, but it writes no guide, removes a `guide.html` an earlier run left,
and says so.

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
