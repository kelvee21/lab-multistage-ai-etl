# run log

the stage 3 evidence. every number below came out of a run i actually did on the
real workbooks in `data/raw/`.

what is allowed in this file: counts of rows, timings, table and column names.
what is not: quantities, revenue sums, rows of real data. those stay in
`data/processed/`, which is gitignored. the sales figures below are stated as
"agree" or "do not agree", never as numbers.

environment: windows 11, python 3.13 in `.venv`, openpyxl 3.1.5, pytest 9.1.1.
contract `v1.1.0`.

## commands

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m etl run          # first run
.\.venv\Scripts\python.exe -m etl run          # again, to prove it is idempotent
.\run.ps1                                       # same thing with the venv bootstrap
```

## tests

```
26 passed in 2.6s
```

the suite builds its own small workbooks with openpyxl and never reads
`data/raw/`, so this number is reproducible on a machine that has never seen the
bakery files. no network and no api key either.

## timings

| run | extract | gate | load | pipeline total | wall clock |
|---|---|---|---|---|---|
| 1 | 14.3 s | 0.1 s | 0.4 s | 14.8 s | 15.5 s |
| 2 | | | | | 15.0 s |
| 3 | | | | | 14.2 s |

extract is the whole cost. 6 workbooks, 123 tabs, opened read only and every
tab actually iterated. the gate and the load together are under a second.

wall clock moves by a second or two depending on what else the machine is doing.
i am giving the range i measured rather than one tidy number.

## counts

| source | rows in | rows loaded | quarantines |
|---|---|---|---|
| production | 8616 | 8616 | none |
| dispatch | 10148 | 10147 | `missing_product` 1, `aggregate_row_value` 1 |
| waste | 1232 | 1232 | none |
| returns | 0 | 0 | none, see below |
| sales_sep | 3689 | 366 keys | `operation_not_sale` 1 |
| sales_oct | 1789 | 323 keys | `bad_date` 1 |

rows 1 and 2 ran again and gave the same numbers. the warehouse is deleted and
rebuilt every run, so this is a real test and not a no-op.

warehouse after the run:

| table | rows |
|---|---|
| fact_production | 8616 |
| fact_dispatch | 10147 |
| fact_waste | 1232 |
| fact_returns | 0 |
| fact_sales | 689 |
| dim_branch | 16 |
| dim_product | 161 |

20684 fact rows in total. the 16 branches are the 14 grid branches plus the two
pos locations, SAWA CITI HQ and BBROOD TOWN, which only ever appear in sales.

the sales sources read transactions and load keys, so they go in as many rows
and come out as few. 3688 september rows and 1788 october rows become 366 + 323
keys, each with a `tx_count`.

the 4 quarantined rows, all of them:

| reason | file | tab | what was in it |
|---|---|---|---|
| `missing_product` | dispatch | 18th | a branch cell had a number but the row had no item name |
| `aggregate_row_value` | dispatch | 22nd | a value typed inside the TOTAL row |
| `operation_not_sale` | sales, september | Sales Report | the grid's own Total footer row |
| `bad_date` | sales, october | Sales Report | the grid's own Total footer row, empty date cell |

## date coverage

| source | day tabs seen | dates with data | gaps |
|---|---|---|---|
| production | 25 | 25 | the 1st to the 25th. there is no tab for the 26th to the 30th at all |
| dispatch | 30 | 30 | none |
| waste | 30 | 24 | 6 tabs with nothing recorded: 1st, 2nd, 3rd, 4th, 29th, 30th |
| returns | 6 | 0 | all 6 tabs blank |
| sales_sep | | 7 | 2023-09-22 to 2023-09-28 |
| sales_oct | | 7 | 2023-10-13 to 2023-10-19 |

the production gap is the one i got wrong first. my first look said the 20th to
the 25th tabs were empty. they are not, each of them has exactly one product
row in it. i corrected the note in the contract when i checked.

## notes in the report

370 info and 95 anomalies, all counts.

- the info notes are the ignored derived columns telling me how many values were
  in them, the letter-O fix firing, the GDYEAR alias, and per tab observations.
- the 95 anomalies are empty header cells sitting above real numbers. nothing is
  loaded from those, because no header means no meaning, and they are counted so
  they are not invisible.

## the three independent checks

written a second time from scratch against the raw files, importing nothing from
`etl/`. otherwise i would just be running my own bug twice. the script is
throwaway, the output is in `runs/independent-checks.log`.

**1. production 16th, recount straight off the tab.**
484 observations counted from the sheet, quantity sum `S`. in the warehouse, 484
rows with quantity sum `S`. match.

**2. row totals on the production file.**
every product row on every day tab, my parsed branch sum against the TOTAL cell
the sheet already carries: 1973 rows agree, 0 disagree.

this one is also what proved the contract right. doing it the sloppy way, without
the GDYEAR alias and against the wrong TOTAL column, gives 13 and 551 false
alarms. so the check is not just confirming the pipeline, it is confirming that
the contract pins down the decisions that matter.

**3. weekly sales, three readings.**
for both files: my recount of the raw grid, the warehouse totals, and the
workbook's own footer Total row. quantity and amount agree across all three, to
the digit. the figures stay out of this file, they are the bakery's money.

## efficiency

one month, 25 production tabs + 30 dispatch tabs + 30 waste tabs + 6 returns
tabs + 2 weekly sales files, becomes 20684 warehouse rows, the csv exports and a
quarantine per fact, rebuilt from scratch in about 14 seconds.

by hand that is 91 tabs to copy out, roughly 14 branch columns to line up per
tab, and every number retyped with whatever spelling that week used. i am not
going to put a made up hour count on it, it is hours every month and it is the
same hours again next month.

## left open on purpose

- returns loads 0 rows. all 6 tabs are blank and each row has a typed 0 in its
  TOTAL cell. either nothing came back in those six days or returns are recorded
  somewhere i was not given. the source stays in the run so the gap keeps showing
  up.
- 95 empty header cells above real numbers.
- production is missing the 26th to the 30th entirely. there is no tab in the
  file.
- the two weekly sales files carry 2023 dates. the june files say 2026. recorded
  as found, it is a question for the bakery not a bug to patch.
- the unit of the day tab numbers is unknown. pieces, crates or kilos.
