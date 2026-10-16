"""warehouse and cli tests: schema, csv, running it twice."""
from __future__ import annotations

import csv
import json
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from etl.contract import load_contract
from etl.extract import extract_all
from etl.load import load_warehouse
from etl.validate import gate
from tests.helpers import (
    SALES_HEADER_SEP, base_contract, make_day_workbook, make_sales_workbook, tx_row,
)

ITEMS = [
    ("MULTIGRAIN LOAF", {"K'KIRO": 6, "CHIC": 1}),
    ("WHITE LOAF", {"RBERO": 2}),
]


def _pipeline(tmp_path):
    contract = base_contract()
    make_day_workbook(tmp_path, "PROD.xlsx", {"1ST JUNE": ITEMS, "2ND JUNE": "empty"})
    make_sales_workbook(
        tmp_path, "SALES.xlsx", SALES_HEADER_SEP,
        [tx_row(item="BS MULTIGRAIN LOAF"), tx_row(doc=2, qty=2, amount=8000,
                                                   item="BS MULTIGRAIN LOAF")],
    )
    extraction = extract_all(contract, tmp_path)
    gated = gate(extraction, contract)
    processed = tmp_path / "processed"
    warehouse = load_warehouse(gated, processed, contract["branch_headers"])
    return contract, gated, processed, warehouse


def test_warehouse_schema_and_counts(tmp_path):
    contract, gated, processed, warehouse = _pipeline(tmp_path)

    conn = sqlite3.connect(processed / "brood_warehouse.sqlite")
    try:
        tables = {t[0] for t in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"dim_branch", "dim_product", "fact_production", "fact_dispatch",
                "fact_waste", "fact_returns", "fact_sales"} <= tables
        prod = list(conn.execute(
            "SELECT d.name, b.name, qty FROM fact_production f "
            "JOIN dim_product d USING(product_id) JOIN dim_branch b USING(branch_id)"
        ))
        assert len(prod) == 3  # two rows for MULTIGRAIN, one for WHITE LOAF
        assert all(r[2] > 0 for r in prod)
        sales = list(conn.execute(
            "SELECT qty, amount, tx_count FROM fact_sales"
        ))
        assert sales == [(3.0, 12000.0, 2)]
    finally:
        conn.close()
    assert warehouse["branches"] >= len(contract["branch_headers"])


def test_csv_exports(tmp_path):
    contract, gated, processed, _ = _pipeline(tmp_path)
    path = processed / "csv" / "fact_production.csv"
    with path.open(encoding="utf-8-sig", newline="") as fh:
        rows = list(csv.DictReader(fh))
    assert [r["product"] for r in rows].count("MULTIGRAIN LOAF") == 2
    assert rows[0]["date"] == "2026-06-01"


def test_idempotent_rebuild(tmp_path):
    contract, gated, processed, _ = _pipeline(tmp_path)
    _pipeline(tmp_path)  # rebuild over the same inputs

    conn = sqlite3.connect(processed / "brood_warehouse.sqlite")
    try:
        assert list(conn.execute("SELECT COUNT(*) FROM fact_production"))[0][0] == 3
        assert list(conn.execute("SELECT COUNT(*) FROM fact_sales"))[0][0] == 1
        assert list(conn.execute("SELECT COUNT(*) FROM dim_product"))[0][0] == \
            len({r["product"] for r in gated.accepted})
    finally:
        conn.close()


def test_cli_run_end_to_end(tmp_path):
    contract = base_contract()
    contract_path = tmp_path / "contract.json"
    contract_path.write_text(json.dumps(contract), encoding="utf-8")
    make_day_workbook(tmp_path, "PROD.xlsx", {"1ST JUNE": ITEMS, "2ND JUNE": "empty"})
    make_sales_workbook(
        tmp_path, "SALES.xlsx", SALES_HEADER_SEP,
        [tx_row(item="BS MULTIGRAIN LOAF"),
         tx_row(doc=2, qty=2, amount=8000, item="BS MULTIGRAIN LOAF"),
         tx_row(doc=3, item="BS CHAPATI", operation="Return")],  # one bad row on purpose
    )
    out_dir = tmp_path / "data"
    repo_root = Path(__file__).resolve().parents[1]
    cmd = [sys.executable, "-m", "etl", "run", "--contract", str(contract_path),
           "--raw", str(tmp_path), "--out", str(out_dir), "--quiet"]
    for _ in range(2):  # second run proves idempotency from the command line too
        proc = subprocess.run(cmd, capture_output=True, text=True, cwd=repo_root)
        if proc.returncode != 0:  # surface the CLI's stderr in the failure message
            pytest.fail(f"etl run failed:\n{proc.stdout}\n{proc.stderr}")

    db = out_dir / "processed" / "brood_warehouse.sqlite"
    assert db.exists()
    report = json.loads((out_dir / "processed" / "validation_report.json")
                        .read_text(encoding="utf-8"))
    assert report["facts"]["production"]["rows_loaded"] == 3
    assert report["quarantine_events_total"] == 1  # the deliberate Return row
    quarantined_csv = out_dir / "processed" / "quarantine"
    assert (quarantined_csv / "sales.csv").exists()
    assert (out_dir / "processed" / "csv" / "fact_sales.csv").exists()


def test_real_contract_loads():
    contract = load_contract(Path(__file__).resolve().parents[1] / "outputs" /
                             "extraction_contract.json")
    assert contract["version"] and len(contract["sources"]) == 6
