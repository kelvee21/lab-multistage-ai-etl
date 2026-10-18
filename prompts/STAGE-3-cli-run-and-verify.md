# stage 3 - run it, check it, write the evidence

ux type: a cli ai (the brief suggests Claude Code CLI or Gemini CLI). plain
powershell works too and is what the run log records.
input: the `etl/` package from stage 2 plus the real files in `data/raw/`.
output: a full run, the pytest result, measured timings, the validation report,
and `runs/RUN-LOG.md`.

this is the stage that decides whether the other two did anything real.

## the prompt i used

```
ROLE
You are a meticulous data-engineer reviewer working in a terminal.

GOAL
Run and verify the BROOD DataOps ETL end-to-end, produce run evidence, and
report discrepancies honestly.

CONTEXT
- python -m etl run --raw data/raw --out data/processed is the entry point.
- The contract (outputs/extraction_contract.json) is authority; if code
  contradicts contract, the CONTRACT wins — report the bug, don't patch over it.
- data/raw holds real business files: never print or copy row data into any
  output file; summaries (counts, dates, percentages, quarantines) only.
- Privacy: nothing from data/raw or data/processed may be committed or pasted
  into chat — file paths and counts are fine.

TASKS, in order
1. Create/refresh venv; pip install -r requirements.txt.
2. python -m pytest -q  → must be green; paste the tail.
3. python -m etl run --raw data/raw --out data/processed with `Measure-Command`
   (or `time`) → capture total seconds.
4. Read data/processed/validation_report.json and report:
   per fact — rows in, rows loaded, quarantines by reason, duplicates,
   unknown sheets, date coverage and any gaps for the expected range.
5. Re-run step 3 → counts must be identical (idempotency check).
6. Spot-check correctness WITHOUT trusting the pipeline: three independent
   checks you choose yourself (e.g. compare one day-tab's total to the
   database's total for that date; count sheet names the pipeline ignored and
   confirm they are genuinely not day sheets).
7. Write runs/RUN-LOG.md: commands as run, pytest tail, timings (seconds),
   the per-fact summary table, the idempotency result, your three checks with
   results, and any anomalies left open. No row data.

REPORT FORMAT
Markdown, sections exactly: Commands / Tests / Timings / Counts / Idempotency
/ Independent checks / Open anomalies. Every number you cite must come from the
run you just did — if you couldn't verify something, write "not verified".
```

## how i got there

1. **first try.** *"run my pipeline and tell me if it works."* it printed rows
   from the real files into the terminal and called it a success while two tabs
   had gone unread.
2. **second try.** row data banned from any output, per source counts required.
   good, but it paraphrased the report instead of quoting it, so i could not tell
   what was measured from what was remembered.
3. **third try, the one above.** fixed section names, the second run for
   idempotency, three checks that may not use `etl.*`, and a "not verified"
   escape hatch.

step 6 is the part i care about. a check that imports my own extract module is
not a check, it just runs my bug twice. the three in the run log were written
from scratch against the raw files.

## what came out of it

- `runs/RUN-LOG.md` with counts, timings and the three checks.
- `data/processed/validation_report.json`, not committed.
- the row total cross check in `etl/extract.py`. the sheets carry their own
  TOTAL column, so comparing it against the sum i parsed is free evidence. it
  found 0 real mismatches once the GDYEAR alias was in, and 551 false ones when
  i compared against the wrong total column, which is exactly what i wanted it
  to prove.
