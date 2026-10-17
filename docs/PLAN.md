# plan - brood dataops

lab: multi stage ai workflow across ux types
module: applied ai and prompt engineering

written before the code, kept up to date as things changed. section 9 is what
i actually ended up doing differently.

## 1. the problem

B BROOD Bakery in Kigali keeps daily operations in hand made excel workbooks.
one tab per day. tab names typed by a person, so `3RD JUNE`, `11th june`, `12th`
and one tab called `1OTH JUNE`. headers that move, numbers with a trailing
space, branch names spelled a different way on different tabs, and a few extra
tabs sitting in the same file.

to answer any question about the month somebody copies the tabs into another
sheet by hand. that is the problem i picked.

## 2. the chain

| stage | ux type | what it gets | what it makes |
|---|---|---|---|
| 1 | chat ai in the browser | pasted cell samples | `outputs/extraction_contract.json` |
| 2 | ide assistant in vs code | the contract json | the `etl/` package |
| 3 | cli agent or powershell | the code + the real files | run, tests, `runs/RUN-LOG.md` |

three stages when the brief asks for two. each output is the next input, no
copy and paste of an answer, just a file.

## 3. why a contract and not just "read my excel"

a workbook like this has hundreds of small decisions in it. which row is the
header. does a blank cell mean zero or nothing. is the bottom TOTAL row a
product. which of the fifteen columns is a branch and which is a price.

if i let a model decide those while writing the code, the decision is invisible
and i can never check it later. putting them in a json file first means every
decision is written down, reviewable, and testable. the code then just follows
it. the json is the only place a rule can live.

## 4. sources in scope

| file | fact |
|---|---|
| `PRODUCTION REPORT JUNE 2026.xlsx` | production |
| `DISPATCH REPORT JUNE 2026.xlsx` | dispatch |
| `WASTE REPORT JUNE 2026.xlsx` | waste |
| `RETURNS  REPORT JUNE 2026.xlsx` | returns |
| `WEEKLY SALES REPORT 22 - 28 SEPTEMBER.xlsx` | sales |
| `WEEKLY SALES REPORT 13 - 19 OCTOBER.xlsx` | sales |

left out on purpose: the 5 zip archives (mixed desktop backups, up to 2 gb), the
powerpoint and docx briefings, the 1-10TH pos export, mixing charts, stock
sheets, finance packs.

## 5. target tables

```sql
dim_branch  (branch_id, name)
dim_product (product_id, name)

fact_production(date_, product_id, branch_id, qty, source_id, source_sheet)
fact_dispatch  (same shape)
fact_waste     (same shape)
fact_returns   (same shape)
fact_sales     (date_, product_id, branch_id, qty, amount, partner, tx_count, ...)
```

primary key on (date_, product_id, branch_id) so a duplicate insert fails
loudly instead of quietly doubling a number. `date_` is a text column holding
iso `YYYY-MM-DD`. csv copies go out per fact with a utf-8 bom so excel opens
them without mangling the apostrophes in `K'KIRO`.

## 6. the gate

this is the part the lab calls a logic step between ai stages, and it is the
part i would defend hardest. plain python in `etl/validate.py`, no model, no
network.

- dedupe per fact type
- every rejected row lands in `quarantine/<fact>.csv` with a machine readable
  reason
- `validation_report.json` with counts per source, date coverage, notes and
  anomalies
- stdout gets counts and paths only

no model can change a number at this point, so the warehouse only holds what a
deterministic check agreed to.

## 7. testing

`pytest`. the tests build small fake workbooks with openpyxl in a tmp folder, so
they need no bakery data, no network and no api key. they cover the day tab
reader, the sales reader, every quarantine reason, the dedupe rules, the sales
aggregation, the schema, the csv exports and running the cli twice.

## 8. privacy

`.gitignore` takes out `data/raw/`, `data/processed/` and `runs/*.log`. the
bakery's numbers do not get committed. what does get committed is counts,
timings and column names. no count in any doc is typed by hand, they all come
out of a run i did, and where i could not verify something the doc says so.

## 9. what changed while building

these are the as-built differences from the plan above.

- pandas went. openpyxl plus the stdlib was cleaner for cell by cell work and
  the tests got faster. `requirements.txt` is now two lines.
- the first contract probe only found 12 branch columns because i looked at a
  few tabs. sweeping every sheet found VISTA and C SHOP as well, so 14.
- `ignore_columns` got a reason next to every name. "ignore the total column"
  is not reviewable, "it is the sum of the branch cells on that row" is.
- the aggregate TOTAL row is now an explicit rule instead of an accident.
- the row total cross check came out of the independent checks, not out of the
  plan. the sheets carry their own TOTAL column, so comparing against it is
  free evidence that i read the row correctly.
- the sales reader needs a second look for the header because both weekly files
  start with a blank row. `header_search_rows` covers it.
- sales facts carry `partner` and `tx_count`. dropping partner would have
  quietly destroyed a column of the source.
- `etl/` sits at the repo root, not under `src/`, so `python -m etl run` works
  with no `PYTHONPATH`. i care more about a reviewer getting a clean first run
  than about the folder layout.
- `tools/inspect_workbook.py` and `run.ps1` are committed because i used them to
  write the contract and to bootstrap the venv.

## 10. build order

1. skeleton, gitignore, requirements, venv
2. go through the workbooks tab by tab and write down what is actually there
3. write the contract from those notes
4. build `etl/` against the contract
5. pytest green, then a real run
6. three checks written from scratch with no `etl` imports
7. diagram, docs, run log
8. go back over the brief line by line and walk the rubric
9. commits as i go
