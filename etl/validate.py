"""The logic step between the ai stages: dedupe, count, quarantine, report.

nothing reaches the warehouse without passing these checks, and every row we
reject is kept with the reason. plain python on purpose, no model involved.
"""
from __future__ import annotations

import csv
import json
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

from .extract import ExtractionResult

QUARANTINE_COLUMNS = [
    "reason", "fact", "source_id", "source_file", "source_sheet",
    "date", "product", "branch", "detail",
]


class GateResult:
    def __init__(self) -> None:
        self.accepted: list[dict] = []
        self.quarantines: list[dict] = []   # from the readers + dedupe
        self.notes: list[dict] = []
        self.by_fact: dict[str, dict] = {}

    @property
    def quarantined_rows(self) -> int:
        return len(self.quarantines)


def gate(result: ExtractionResult, contract: dict) -> GateResult:
    """dedupe per fact type, then build the report."""
    gate_result = GateResult()
    gate_result.notes = list(result.notes)
    gate_result.quarantines = [
        {
            "reason": q["reason"], "fact": q["fact"], "source_id": q["source_id"],
            "source_file": q["source_file"], "source_sheet": q["source_sheet"],
            "date": q.get("date"), "product": q.get("product"),
            "branch": q.get("branch"), "detail": q.get("detail"),
        }
        for q in result.quarantines
    ]

    seen_keys: dict[str, dict] = {}
    tx_accumulator: dict[str, dict] = {}

    per_fact_in: dict = {src["id"]: 0 for src in contract["sources"]}

    for row in result.rows:
        sid = row["source_id"]
        per_fact_in[sid] += 1
        fact = row["fact"]
        if fact == "sales":
            # same date+product+branch can happen many times in a sales grid,
            # that is normal. sum it and keep how many rows went in.
            key = (row["date"], row["product"], row["branch"])
            acc = tx_accumulator.get(key)
            if acc is None:
                acc = {
                    "fact": "sales", "source_id": row["source_id"],
                    "date": row["date"], "product": row["product"],
                    "branch": row["branch"],
                    "qty": 0.0, "amount": 0.0, "amount_seen": False,
                    "partner": row.get("partner"), "tx_count": 0,
                    "source_file": row["source_file"], "source_sheet": row["source_sheet"],
                }
                tx_accumulator[key] = acc
            acc["qty"] = round(acc["qty"] + row["qty"], 6)
            if row.get("amount") is not None:
                acc["amount"] = round(acc["amount"] + row["amount"], 6)
                acc["amount_seen"] = True
            acc["tx_count"] += 1
            continue

        key = (fact, row["date"], row["product"], row["branch"])
        if key in seen_keys:
            gate_result.quarantines.append({
                "reason": "duplicate_key", "fact": fact, "source_id": row["source_id"],
                "source_file": row["source_file"], "source_sheet": row["source_sheet"],
                "date": row["date"], "product": row["product"], "branch": row["branch"],
                "detail": "another observation for this exact key was already accepted",
            })
            continue
        seen_keys[key] = row
        gate_result.accepted.append(row)
        continue

    gate_result.accepted.extend(tx_accumulator.values())

    # ---- per fact / per source numbers for the report ---------------------- #
    report_sources = []
    loaded_counter = Counter(row["source_id"] for row in gate_result.accepted)
    quar_counter: dict[str, Counter] = defaultdict(Counter)

    for src in contract["sources"]:
        sid = src["id"]
        counts = quar_counter[sid]
        for q in gate_result.quarantines:
            if q["source_id"] == sid:
                counts[q["reason"]] += 1
        entry = {
            "id": sid,
            "fact": src["fact"],
            "file": src["file"],
            "rows_in": per_fact_in.get(sid, 0) + sum(
                c for reason, c in counts.items()
                if reason in _data_row_reasons(src)
            ),
            "rows_loaded": loaded_counter[sid],
            "quarantines_by_reason": dict(counts),
            "sheet_kinds": dict(sorted(result.sheets.get(sid, {}).items())),
            "notes": [n["message"] for n in result.notes if n["source_id"] == sid],
        }
        if src["grid"] == "day":
            dates = sorted({row["date"] for row in gate_result.accepted if row["source_id"] == sid})
            expected = list(range(src["expected_days"]["from"], src["expected_days"]["to"] + 1))
            month_days = {
                f"{src['period']['year']:04d}-{src['period']['month']:02d}-{d:02d}"
                for d in expected
            }
            blanks = sorted(
                sheet for sheet, kind in result.sheets.get(sid, {}).items()
                if kind == "day_sheet_no_recorded_values"
            )
            entry["date_coverage"] = {
                "expected_days": len(expected),
                "day_sheets_seen": len(dict(result.sheets.get(sid, {}))),
                "dates_with_data": len(dates),
                "days_with_no_recorded_values": len(blanks),
                "blank_day_sheets": blanks,
            }
        elif src["grid"] == "transactions":
            dates = sorted({row["date"] for row in gate_result.accepted if row["source_id"] == sid})
            entry["date_coverage"] = {
                "dates_with_data": len(dates),
                "min_date": dates[0] if dates else None,
                "max_date": dates[-1] if dates else None,
            }
        report_sources.append(entry)

    gate_result.by_fact = {
        fact: {
            "rows_loaded": sum(1 for r in gate_result.accepted if r["fact"] == fact),
        }
        for fact in sorted({src["fact"] for src in contract["sources"]})
    }
    gate_result.report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sources": report_sources,
        "facts": gate_result.by_fact,
        "quarantine_events_total": len(gate_result.quarantines),
        "notes": [
            {"source_id": n["source_id"], "sheet": n["source_sheet"],
             "level": n["level"], "message": n["message"]}
            for n in result.notes
        ],
    }
    return gate_result


def _data_row_reasons(src: dict) -> set:
    """reasons where we threw away a data row this source actually had."""
    if src["grid"] == "transactions":
        return {
            "bad_date", "missing_product", "missing_branch", "missing_quantity",
            "non_numeric_qty", "negative_qty", "operation_not_sale",
        }
    return {"non_numeric_qty", "negative_qty", "missing_product"}


def write_quarantine_csvs(gate_result: GateResult, out_dir: Path) -> dict:
    """one csv per fact with every rejected row and why."""
    quar_dir = out_dir / "quarantine"
    quar_dir.mkdir(parents=True, exist_ok=True)
    written = {}
    by_fact = defaultdict(list)
    for q in gate_result.quarantines:
        by_fact[q["fact"]].append(q)
    for fact, events in sorted(by_fact.items()):
        path = quar_dir / f"{fact}.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=QUARANTINE_COLUMNS)
            writer.writeheader()
            for event in sorted(
                    events, key=lambda e: (e.get("date") or "", e.get("product") or "",
                                           e.get("branch") or "")):
                writer.writerow({col: event.get(col) for col in QUARANTINE_COLUMNS})
        written[fact] = str(path)
    return written


def write_report(gate_result: GateResult, out_dir: Path, runtime_seconds: float, contract_version: str) -> Path:
    report = dict(gate_result.report)
    report["runtime_seconds"] = round(runtime_seconds, 3)
    report["contract_version"] = contract_version
    path = out_dir / "validation_report.json"
    with path.open("w", encoding="utf-8") as fh:
        json.dump(report, fh, ensure_ascii=False, indent=2)
    return path
