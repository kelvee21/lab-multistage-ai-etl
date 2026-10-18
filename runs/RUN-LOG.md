# run log

stage 3 evidence. every number came out of a run i did on the real workbooks in
`data/raw/`.

what goes in this file: counts of rows, timings, table and column names. what
does not: quantities, revenue sums, real rows. those stay in
`data/processed/`, which is gitignored.

environment: windows 11, python 3.13 in `.venv`, openpyxl 3.1.5, pytest 9.1.1.
contract `v1.1.0`.

## commands

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --disable-pip-version-check -r requirements.txt
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m etl run
.\.venv\Scripts\python.exe -m etl run          # again, idempotency
```

## tests

```
26 passed in 2.6s
```

the suite builds its own workbooks with openpyxl and never reads `data/raw/`, so
this runs on a machine that has never seen the bakery files. no network, no key.

## timings

| run | extract | gate | load | total | wall clock |
|---|---|---|---|---|---|
| 1 | 14.3 s | 0.1 s | 0.4 s | 14.8 s | 15.5 s |
| 2 | | | | | 15.0 s |

extract is the whole cost. 6 workbooks, 123 tabs, opened read only. the gate and
the load together are under a second.

## counts

| source | rows in | rows loaded | quarantines |
|---|---|---|---|
| production | 8616 | 8616 | none |
| dispatch | 10148 | 10147 | `missing_product` 1, `aggregate_row_value` 1 |
| waste | 1232 | 1232 | none |
| returns | 0 | 0 | none |
| sales_sep | 3689 | 366 keys | `operation_not_sale` 1 |
| sales_oct | 1789 | 323 keys | `bad_date` 1 |

ran it again and got the same numbers. the warehouse is deleted and rebuilt every
run so that is a real check.

| table | rows |
|---|---|
| fact_production | 8616 |
| fact_dispatch | 10147 |
| fact_waste | 1232 |
| fact_returns | 0 |
| fact_sales | 689 |
| dim_branch | 16 |
| dim_product | 161 |

20684 fact rows. the 16 branches are the 14 grid branches plus SAWA CITI HQ and
BBROOD TOWN, which only show up in sales.

sales go in as transactions and come out as keys, 3688 september rows and 1788
october rows become 366 + 323, each with a `tx_count`.

notes in the report: 370 info, 95 anomaly. the info ones are the ignored derived
columns counting their values, the letter-O fix and the GDYEAR alias. the 95
anomalies are empty header cells above real numbers, not loaded, counted so they
are not invisible.

## still to do on this stage

write three checks that do not import `etl/`, then finish this log.
