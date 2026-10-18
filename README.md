# brood dataops - multi stage ai workflow

lab for applied ai and prompt engineering: chain outputs between at least two
ai ux types. the data is real bakery operations excel, one tab per day, kept on
my machine and never committed.

## the chain

3 stages. each one takes the file the stage before it made.

1. chat ai in the browser. i paste a few cell samples, it writes
   `outputs/extraction_contract.json`. every file, tab, column and ignore rule
   is in that json, plus the questions it refused to answer.
2. the ide assistant reads that json and writes `etl/`. the json is the spec, so
   the assistant does not get to decide anything on its own.
3. a cli agent, or just powershell, runs pytest and `python -m etl run`, then
   writes `runs/RUN-LOG.md` with the numbers.

between stage 2 and stage 3 sits `etl/validate.py`. plain python, no model. it
dedupes, quarantines and counts. that logic step is why i trust the numbers.

diagram in `docs/diagram.md`.

## run

```powershell
.\run.ps1              # makes .venv on first run, then runs the pipeline
.\run.ps1 tests        # pytest instead
```

or by hand:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m etl run
```

python 3.12+. requirements are openpyxl and pytest, nothing else. pytest builds
its own small workbooks so it runs without `data/raw`, which means a reviewer
with no bakery files still gets all 26 tests green.

what a run leaves behind:

```
data/processed/brood_warehouse.sqlite   dim_branch, dim_product,
                                        fact_production|dispatch|waste|returns|sales
data/processed/csv/fact_*.csv           one csv per fact
data/processed/quarantine/*.csv         every rejected row and why
data/processed/validation_report.json   counts, notes, anomalies, runtime
```

## the three stages

### stage 1, the contract

`outputs/extraction_contract.json`. i dumped the tabs with
`tools/inspect_workbook.py` and pasted short samples into a chat ai. the prompt
is `prompts/STAGE-1-chat-profile-and-contract.md`, written as role / goal /
context / format, and it keeps my bad first draft so the iteration is visible.

what came back: conventions, 14 branch headers, one entry per source,
`ignore_columns` each with the reason written next to it, the TOTAL row rule,
the row total cross check, and `open_questions` for everything that would have
been a guess.

### stage 2, the code

`etl/`. prompt in `prompts/STAGE-2-ide-build-etl.md`. the rule i gave it was that
the contract wins, so when the code and the json disagreed i treated the json as
the bug report instead of working around it.

```
etl/contract.py   load and check the json, fail fast
etl/normalize.py  text, number and date cleaning
etl/extract.py    day tab reader + sales grid reader
etl/validate.py   the gate: dedupe, quarantine, counts, report
etl/load.py       sqlite star schema + csv
etl/__main__.py   python -m etl run
```

### stage 3, run and check

`runs/RUN-LOG.md`. prompt in `prompts/STAGE-3-cli-run-and-verify.md`. i ran
pytest, ran the pipeline twice to prove it is idempotent, read the validation
report, then wrote three checks from scratch with no `etl` imports so i was not
grading my own homework.

counts and seconds only in that log, no business numbers.

## things that turned out to matter

- **blank is not 0.** an empty cell means nobody wrote anything. putting a 0
  there invents data. a tab where every product row is blank loads 0 rows and
  says so in the report.
- **the letter O tab.** one tab is called `1OTH JUNE`. `fix_letter_O` swaps O for
  0 and retries the same pattern once, nothing else gets a second chance.
- **GDYEAR.** the waste 14th tab types `G YEAR` as `GDYEAR`. it is in the right
  column so it maps by alias, and every use is noted in the report.
- **ignore_columns.** row totals, prices and the dispatch variance table are not
  branches. dropped by contract with a reason written next to each one, and every
  tab that held values in them gets a note so the drop is not silent.
- **TOTAL rows.** the aggregate row at the bottom of a tab is not a product. if
  someone typed a number in its branch cells it becomes a quarantine.
- **row total cross check.** where the sheet carries its own TOTAL column i
  compare it against the sum i parsed. rows that disagree become anomaly notes.
- **unnamed columns.** an empty header sitting above real numbers gets a note and
  is not loaded. no header means no column meaning.
- **sales repeat.** the same item at the same branch on the same day can be sold
  many times. the gate sums those and keeps a `tx_count`. only the day grids
  dedupe, and there a second row for the same key is a quarantine.

## still open

i did not guess these and neither does the pipeline.

- the unit of the day tab numbers. pieces, crates or kilos, nothing in the files
  says. stored exactly as recorded.
- `BS MULTIGRAIN LOAF` in sales and `MULTIGRAIN LOAF` in production. probably the
  same bread but i cannot prove it from the data, so `dim_product` keeps both.
- returns loads 0 rows. all 6 tabs are blank with a typed 0 in every TOTAL cell.
  either nothing came back or it gets written down somewhere else.
- the sales files say 2023, the june files say 2026. recorded as found.
- production has no tab at all for the 26th to the 30th. the report shows the gap.
- 95 empty header cells sit above real numbers. not loaded, counted as
  anomalies.

## data

`data/raw/` and `data/processed/` are gitignored. the bakery numbers do not
leave this folder. committed files carry counts, timings and column names only.

next month is copying the workbooks into `data/raw` and adding contract entries.
the readers key off the contract, not off file names in the code. see
`docs/adaptability.md`.

## where the brief is answered

`docs/LAB-BRIEF.md` maps every line of the brief to the file that answers it.
`docs/PLAN.md` is the plan plus what changed while i was building.
`docs/TIMELINE.md` is my week.
