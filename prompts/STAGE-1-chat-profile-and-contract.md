# stage 1 - chat ai writes the extraction contract

ux type: chat ai in the browser (the brief suggests ChatGPT or Gemini Chat).
input: a few pasted cell samples. never the whole file, that is what floods the
context and gets a lazy answer.
output: `outputs/extraction_contract.json`, which is what stage 2 reads.

why a contract and not just "read my excel". these workbooks have hundreds of
small decisions in them. which row is the header, whether a blank cell means
zero, whether the bottom TOTAL row is a product, which column is a branch and
which is a price. if the model settles those while writing code then the
settling is invisible and i can never check it. in a json file every decision is
written down first, reviewable, and the code just follows it.

## the prompt i used

```
ROLE
You are a meticulous data-ops analyst profiling messy Excel exports from a
bakery (one tab per day of a month, plus weekly POS sales grids).

GOAL
Write an "extraction contract": a machine-readable JSON of every rule needed to
turn these workbooks into clean warehouse tables, WITHOUT inventing anything.

CONTEXT
Below are faithful samples of what the sheets look like. Facts you must
account for (verify against the samples, they are real):
- tab names typed by humans: "3RD JUNE", "11th june", "12th", "1ST  " and one
  tab named "1OTH JUNE" (letter O instead of digit 0);
- grid: column A is a row number, column B is the ITEM, then branch columns
  (HQ, K'KIRO, RBERO, NBOYE, CHIC, M'HIMA, N'RAMA, KGU, RMRA, K'IMENTI,
  G YEAR, FZONE, VISTA, C SHOP), then derived columns (TOTAL per row, PRICE /
  UNIT, TOTAL COST, and on dispatch tabs a side-by-side variance table);
- each tab ends with an aggregate row whose item says TOTAL;
- a stray value can sit above the header row (a dispatch "22nd" tab shows 4.0
  in column A above the header);
- some header cells are empty while numbers sit below them;
- on one waste tab the branch header G YEAR is typed "GDYEAR";
- weekly POS sales: transaction grid with columns Date (dd.mm.yyyy), Item,
  Location, Quantity, Sale amount (+ Partner/Operation columns in September,
  Purchase price columns in October); the sheet has a blank first row and ends
  in a "Total" footer row; the data years are 2023 even though the June files
  say 2026;
- blanks: many cells are empty; we do NOT know whether an empty cell is zero
  or "recorded nothing", and we must not guess.

FORMAT
Answer with exactly three parts:
1. "Reading checks" — 5 bullets confirming what you see in the samples
   (header row position, item/branch layout, aggregate rows, sales columns).
2. An "extraction_contract.json" draft with: version, conventions (text
   normalisation, blank-cell semantics, numeric rules, date rules, duplicate
   policies), branch_headers, then per-source entries (id, file, fact, grid,
   period/expected_days, day_sheet regex, item header, ignore_columns with a
   written reason each, aggregate_rows, header_search_rows; for sales: sheet
   name, columns map, date format, operation_accept), and open_questions.
3. "Risks you refused to resolve" — every place where you would be tempted to
   guess (unit of the numbers? brother-spellings? BS- prefix products?) and
   what business question each needs.

Follow-ups to expect: I may ask you to revise single rules (e.g. add an alias,
add an ignore column) - reissue only the changed contract sections, and say
explicitly what changed.
```

## how i got there

the brief wants the iteration visible, so here it is.

1. **first try, too vague.** *"look at my bakery excel screenshots and tell me
   how to turn them into a database."* it mapped columns off one screenshot,
   turned blanks into zeros everywhere, and wanted to tidy the branch spellings
   into full names it did not know.
2. **second try.** locked the role, listed what is actually in the files, asked
   for json and for open questions. much better, but it still wanted to drop
   rows it could not read.
3. **third try, the one above.** added the blank rule, required a written reason
   next to every ignored column, required quarantining instead of dropping, and
   asked for the risks section.

after that i still edited it by hand. the draft went in at v1.0.0, i added
VISTA and C SHOP after sweeping every tab instead of the first few, and the two
sales sources came in last, so the file that stage 2 reads is v1.1.0.

## rules this stage must not break

- no invented numbers, no currency conversion, no merging product names
- no "assume zero" for blanks
- no claiming a column means something when the file does not say so
