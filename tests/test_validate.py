"""gate tests: dedupe, sales aggregation, report shape."""
from __future__ import annotations

import pytest

from etl.contract import ContractError, load_contract
from etl.extract import extract_all
from etl.validate import gate
from tests.helpers import (
    SALES_HEADER_SEP, base_contract, day_only_contract, make_day_workbook,
    make_sales_workbook, sales_only_contract, tx_row,
)


def test_contract_rejects_missing_and_broken(tmp_path):
    with pytest.raises(ContractError):
        load_contract(tmp_path / "nope.json")
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    with pytest.raises(ContractError):
        load_contract(bad)


def test_duplicate_keys_quarantined_not_dropped(tmp_path):
    contract = day_only_contract()
    # same product twice in one tab, so the (date, product, branch) key repeats
    items = [("MULTIGRAIN LOAF", {"K'KIRO": 6}), ("MULTIGRAIN LOAF", {"K'KIRO": 9})]
    make_day_workbook(tmp_path, "PROD.xlsx", {"1ST JUNE": items})
    result = gate(extract_all(contract, tmp_path), contract)

    assert len(result.accepted) == 1
    assert result.accepted[0]["qty"] == 6  # first one wins
    dups = [q for q in result.quarantines if q["reason"] == "duplicate_key"]
    assert len(dups) == 1 and dups[0]["product"] == "MULTIGRAIN LOAF"


def test_transactions_aggregate_by_key(tmp_path):
    contract = sales_only_contract()
    rows = [
        tx_row(item="BS ALMOND CROISSANT", location="SAWA CITI HQ", qty=1, amount=1500),
        tx_row(doc=2, item="BS ALMOND CROISSANT", location="SAWA CITI HQ", qty=2, amount=3000),
        tx_row(doc=3, item="BS ALMOND CROISSANT", location="BBROOD TOWN", qty=1, amount=1500),
    ]
    make_sales_workbook(tmp_path, "SALES.xlsx", SALES_HEADER_SEP, rows)
    result = gate(extract_all(contract, tmp_path), contract)

    sales = [r for r in result.accepted if r["fact"] == "sales"]
    assert len(sales) == 2  # one per branch, same product and date summed
    hq = next(r for r in sales if r["branch"] == "SAWA CITI HQ")
    assert hq["qty"] == 3 and hq["amount"] == 4500 and hq["tx_count"] == 2
    other = next(r for r in sales if r["branch"] == "BBROOD TOWN")
    assert other["qty"] == 1 and other["tx_count"] == 1


def test_operation_outside_contract_quarantined(tmp_path):
    contract = sales_only_contract()
    rows = [
        tx_row(item="BS TIN BROWN"),
        tx_row(doc=2, item="BS CHAPATI", operation="Return"),
        tx_row(doc=3, item="BS TIN BROWN", operation=None),
    ]
    make_sales_workbook(tmp_path, "SALES.xlsx", SALES_HEADER_SEP, rows)
    extracted = extract_all(contract, tmp_path)
    gated = gate(extracted, contract)

    ops = [q for q in gated.quarantines if q["reason"] == "operation_not_sale"]
    assert len(ops) == 2  # 'Return' and the blank one, neither is a confirmed sale
    assert all(r["product"] == "BS TIN BROWN" for r in gated.accepted)


def test_bad_dates_and_missing_branch(tmp_path):
    contract = sales_only_contract()
    rows = [
        tx_row(date="31.02.2023"),
        tx_row(doc=2, date="23.09.2023", location=""),
        tx_row(doc=3, date="23.09.2023"),
    ]
    make_sales_workbook(tmp_path, "SALES.xlsx", SALES_HEADER_SEP, rows)
    gated = gate(extract_all(contract, tmp_path), contract)

    reasons = {q["reason"] for q in gated.quarantines}
    assert "bad_date" in reasons and "missing_branch" in reasons
    assert len(gated.accepted) == 1


def test_report_counts_and_coverage(tmp_path):
    contract = base_contract()
    make_day_workbook(
        tmp_path, "PROD.xlsx", {"1ST JUNE": [("MULTIGRAIN LOAF", {"HQ": 9})], "2ND JUNE": "empty"}
    )
    make_sales_workbook(
        tmp_path, "SALES.xlsx", SALES_HEADER_SEP, [tx_row(), tx_row(doc=2, qty=2, amount=8000)]
    )
    gated = gate(extract_all(contract, tmp_path), contract)

    source = next(s for s in gated.report["sources"] if s["id"] == "production")
    assert source["rows_loaded"] == 1
    assert source["date_coverage"]["dates_with_data"] == 1
    assert source["date_coverage"]["days_with_no_recorded_values"] == 1

    sales_entry = next(s for s in gated.report["sources"] if s["id"] == "sales_sep")
    assert sales_entry["date_coverage"]["min_date"] == "2023-09-22"
    assert gated.by_fact["sales"]["rows_loaded"] == 1
    assert gated.by_fact["production"]["rows_loaded"] == 1
