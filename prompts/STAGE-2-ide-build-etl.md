# stage 2 - ide assistant writes the etl

ux type: an ide with ai (the brief suggests VS Code with Copilot).
input: `outputs/extraction_contract.json`, which is stage 1's output, plus this
prompt.
output: the `etl/` package, which is stage 3's input.

not one mega prompt. when something breaks later i want to know which stage it
broke in, and a single 2000 line prompt cannot tell me that.

## the prompt i used

```
ROLE
You are a senior data engineer pair-programming with me in an IDE.

GOAL
Implement a small, correct, quarantine-first ETL in Python 3.12+.

CONTEXT
- Repo skeleton is in place. You may see tests/ and docs/PLAN.md for intent.
- The single source of truth for file/table rules is
  outputs/extraction_contract.json (produced by an earlier AI stage; treat its
  statements as requirements, not suggestions).
- Sources: .xlsx workbooks laid out as "one tab per day" (tab names like
  "3RD JUNE", "11th june", "12th") plus weekly sales sheets. They are messy:
  headers that move, stray summary tabs, numbers with trailing spaces and
  polished branch/product spelling variants.
- Privacy: data/raw/ and data/processed/ are gitignored. Tests must NOT read
  data/raw; they build synthetic workbooks with openpyxl instead.

FORMAT — build exactly these modules:
- etl/contract.py   : load + validate the contract JSON (fail fast, clear errors)
- etl/extract.py    : read workbooks per contract; yield raw rows with provenance
                      (source_file, source_sheet); unknown sheets → quarantine
- etl/normalize.py  : clean dates (or parse from sheet names), trim/upper-case
                      spellings, coerce qty ('2 ', '2,0' → 2.0), build
                      dim_product/dim_branch
- etl/validate.py   : the logic gate between AI stages — quarantine reasons:
                      unparsable_row, missing_product, non_numeric_qty,
                      negative_qty, bad_date, unknown_sheet, duplicate_key;
                      produce data/processed/validation_report.json
- etl/load.py       : rebuild SQLite star schema + per-fact CSVs (UTF-8-sig)
- etl/__main__.py   : `python -m etl run [--contract …] --raw … --out …`
                      prints count summary (IDs and totals only — NEVER row data,
                      so logs stay safe to share)

RULES
- Nothing is silently dropped: every unreadable row lands in quarantine/<fact>.csv
  with a machine-readable reason.
- Nothing is invented: no lookups of product names, no currency conversions,
  no default branches where a source has none (leave NULL and flag).
- An idempotent run rebuilds the warehouse from scratch — same data, same counts.
- Keep imports stdlib + openpyxl only. No new dependencies.

FIRST STEP
Restate the contract's per-fact rules in one short paragraph each, flag anything
ambiguous instead of guessing, then wait for my go — that paragraph becomes the
code's module docstrings so the reasoning is preserved.
```

## how i got there

1. **first try.** *"build an ETL for my bakery excel files."* it guessed what the
   columns meant, gave production a branch column it does not have, and
   hardcoded the tab names.
2. **second try.** role, contract as authority, the module list spelled out,
   quarantine-first. better, but it quietly threw non numeric rows away instead
   of writing them down.
3. **third try, the one above.** nothing dropped and nothing invented moved up
   into RULES, it has to restate the rules and flag ambiguity before it starts,
   and row data is banned from any output.

that last one mattered more than i expected. asking for the restatement first
caught two places where i had described a rule badly, and i fixed the contract
instead of letting the assistant guess.

## the rule that decided the disagreements

when the code and the contract did not match, the contract won and the code was
the bug. i did not "fix" code to match something i had only half read, because
that is how an invented rule gets into a pipeline.
