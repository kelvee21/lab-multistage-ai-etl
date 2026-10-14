"""BROOD DataOps ETL - bakery excel exports into one sqlite warehouse.

starting the package. rules live in outputs/extraction_contract.json and the
code only follows them. blank cell = not recorded, never 0. a row we cannot read
goes to quarantine/ with a reason instead of disappearing.

  contract  load and check the contract json, fail fast
  normalize text / number / date cleaning
"""
