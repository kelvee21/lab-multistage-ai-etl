"""Build the sqlite star schema and the csv exports.

we delete the database and make it again on every run, so running twice on the
same files gives the same numbers. that is a tested property.
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from .validate import GateResult

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE dim_branch (
    branch_id INTEGER PRIMARY KEY,
    name      TEXT NOT NULL UNIQUE
);

CREATE TABLE dim_product (
    product_id INTEGER PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE
);

CREATE TABLE fact_production (
    date_        TEXT NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES dim_product(product_id),
    branch_id    INTEGER NOT NULL REFERENCES dim_branch(branch_id),
    qty          REAL NOT NULL,
    source_id    TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    PRIMARY KEY (date_, product_id, branch_id)
);

CREATE TABLE fact_dispatch (
    date_        TEXT NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES dim_product(product_id),
    branch_id    INTEGER NOT NULL REFERENCES dim_branch(branch_id),
    qty          REAL NOT NULL,
    source_id    TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    PRIMARY KEY (date_, product_id, branch_id)
);

CREATE TABLE fact_waste (
    date_        TEXT NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES dim_product(product_id),
    branch_id    INTEGER NOT NULL REFERENCES dim_branch(branch_id),
    qty          REAL NOT NULL,
    source_id    TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    PRIMARY KEY (date_, product_id, branch_id)
);

CREATE TABLE fact_returns (
    date_        TEXT NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES dim_product(product_id),
    branch_id    INTEGER NOT NULL REFERENCES dim_branch(branch_id),
    qty          REAL NOT NULL,
    source_id    TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    PRIMARY KEY (date_, product_id, branch_id)
);

CREATE TABLE fact_sales (
    date_        TEXT NOT NULL,
    product_id   INTEGER NOT NULL REFERENCES dim_product(product_id),
    branch_id    INTEGER NOT NULL REFERENCES dim_branch(branch_id),
    qty          REAL NOT NULL,
    amount       REAL,
    partner      TEXT,
    tx_count     INTEGER NOT NULL,
    source_id    TEXT NOT NULL,
    source_sheet TEXT NOT NULL,
    PRIMARY KEY (date_, product_id, branch_id)
);

CREATE INDEX idx_fact_dates ON fact_production(date_);
CREATE INDEX idx_fact_dates2 ON fact_dispatch(date_);
CREATE INDEX idx_fact_dates3 ON fact_waste(date_);
CREATE INDEX idx_fact_dates4 ON fact_returns(date_);
CREATE INDEX idx_fact_dates5 ON fact_sales(date_);
"""

CSV_HEADER = {
    "production": ["date", "product", "branch", "qty", "source_sheet"],
    "dispatch": ["date", "product", "branch", "qty", "source_sheet"],
    "waste": ["date", "product", "branch", "qty", "source_sheet"],
    "returns": ["date", "product", "branch", "qty", "source_sheet"],
    "sales": ["date", "product", "branch", "qty", "amount", "partner", "tx_count", "source_sheet"],
}


def load_warehouse(gate_result: GateResult, out_dir: Path, branch_headers: list) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    db_path = out_dir / "brood_warehouse.sqlite"
    if db_path.exists():
        db_path.unlink()  # rebuild every time: same input -> same counts

    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(SCHEMA)
        cur = conn.cursor()

        # ---- dimensions ------------------------------------------------- #
        # branch universe = the contract branch headers plus every branch we
        # saw in an accepted row. the two POS locations only exist in sales.
        branches = sorted({h for h in branch_headers} |
                          {r["branch"] for r in gate_result.accepted if r["branch"]})
        branch_ids = {name: i + 1 for i, name in enumerate(branches)}
        cur.executemany(
            "INSERT INTO dim_branch (branch_id, name) VALUES (?, ?)",
            [(branch_ids[name], name) for name in branches],
        )

        products = sorted({r["product"] for r in gate_result.accepted})
        product_ids = {name: i + 1 for i, name in enumerate(products)}
        cur.executemany(
            "INSERT INTO dim_product (product_id, name) VALUES (?, ?)",
            [(product_ids[name], name) for name in products],
        )

        # ---- facts ------------------------------------------------------- #
        grid_rows = [
            r for r in gate_result.accepted
            if r["fact"] in ("production", "dispatch", "waste", "returns")
        ]
        cur.executemany(
            "INSERT INTO fact_production (date_, product_id, branch_id, qty, source_id, source_sheet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _grid_tuples(grid_rows, "production", product_ids, branch_ids),
        )
        cur.executemany(
            "INSERT INTO fact_dispatch (date_, product_id, branch_id, qty, source_id, source_sheet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _grid_tuples(grid_rows, "dispatch", product_ids, branch_ids),
        )
        cur.executemany(
            "INSERT INTO fact_waste (date_, product_id, branch_id, qty, source_id, source_sheet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _grid_tuples(grid_rows, "waste", product_ids, branch_ids),
        )
        cur.executemany(
            "INSERT INTO fact_returns (date_, product_id, branch_id, qty, source_id, source_sheet) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            _grid_tuples(grid_rows, "returns", product_ids, branch_ids),
        )

        sales_rows = [r for r in gate_result.accepted if r["fact"] == "sales"]
        cur.executemany(
            "INSERT INTO fact_sales (date_, product_id, branch_id, qty, amount, partner, "
            "tx_count, source_id, source_sheet) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            [
                (
                    r["date"], product_ids[r["product"]], branch_ids[r["branch"]],
                    r["qty"], r["amount"] if r.get("amount_seen", True) else None,
                    r.get("partner"), r.get("tx_count", 1), r["source_id"], r["source_sheet"],
                )
                for r in sales_rows
            ],
        )
        conn.commit()
    finally:
        conn.close()

    csv_dir = write_csvs(gate_result, out_dir)
    return {
        "warehouse": str(db_path),
        "branches": len(branches),
        "products": len(products),
        "csv_dir": str(csv_dir),
        "rows_by_fact": gate_result.by_fact,
    }


def _grid_tuples(rows, fact, product_ids, branch_ids):
    for r in rows:
        if r["fact"] != fact:
            continue
        yield (
            r["date"], product_ids[r["product"]], branch_ids[r["branch"]],
            r["qty"], r["source_id"], r["source_sheet"],
        )


def write_csvs(gate_result: GateResult, out_dir: Path) -> Path:
    csv_dir = out_dir / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    header_map = CSV_HEADER
    by_fact: dict[str, list[dict]] = {}
    for r in gate_result.accepted:
        by_fact.setdefault(r["fact"], []).append(r)
    for fact, rows in by_fact.items():
        path = csv_dir / f"fact_{fact}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=header_map[fact])
            writer.writeheader()
            for r in sorted(rows, key=lambda x: (x["date"], x["product"], x["branch"] or "")):
                out = {
                    "date": r["date"], "product": r["product"], "branch": r["branch"],
                    "qty": r["qty"], "source_sheet": r["source_sheet"],
                }
                if fact == "sales":
                    out.update({
                        "amount": r.get("amount"),
                        "partner": r.get("partner"),
                        "tx_count": r.get("tx_count", 1),
                    })
                writer.writerow(out)
    return csv_dir
