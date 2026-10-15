"""BROOD DataOps ETL - bakery excel exports into one sqlite warehouse.

rules live in outputs/extraction_contract.json, the code only follows them.
blank cell = not recorded, never 0. row we cannot read goes to quarantine/ with
a reason. unit of the numbers and the BS prefix question are still open, so we
store what the file says.

  contract  load and check the contract json, fail fast
  normalize text / number / date cleaning
  extract   readers for the day tabs and the sales grid
  validate  the gate: dedupe, count, quarantine, write the report
  load      sqlite star schema + one csv per fact
  __main__  python -m etl run
"""

__version__ = "1.0.0"
