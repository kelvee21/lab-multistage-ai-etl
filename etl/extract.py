"""Readers for the two shapes of source file.

both give back plain dicts with provenance, so nothing downstream needs to know
which file a number came from. anything we cannot read goes to quarantine with a
reason or becomes a note in the report. we never drop it and never guess.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional

import openpyxl
from openpyxl.utils import get_column_letter

from .normalize import day_from_sheet, iso_date, norm_label, norm_text, parse_qty, parse_tx_date

EPS = 1e-6


class ExtractionError(Exception):
    """a file or sheet the contract needs is missing or unreadable."""


def _quarantine(reason: str, src: dict, sheet: str, **fields) -> dict:
    return {
        "reason": reason,
        "fact": src["fact"],
        "source_id": src["id"],
        "source_file": src["file"],
        "source_sheet": sheet,
        **fields,
    }


def _note(level: str, src_id: str, sheet: str, message: str) -> dict:
    return {"level": level, "source_id": src_id, "source_sheet": sheet, "message": message}


class ExtractionResult:
    def __init__(self) -> None:
        self.rows: list[dict] = []
        self.quarantines: list[dict] = []
        self.notes: list[dict] = []
        # per source id: {sheet_name: kind}
        self.sheets: dict[str, dict[str, str]] = {}


def extract_all(contract: dict, raw_dir: Path) -> ExtractionResult:
    result = ExtractionResult()
    for src in contract["sources"]:
        path = raw_dir / src["file"]
        if not path.exists():
            raise ExtractionError(
                f"source {src['id']!r}: file not found in {raw_dir}: {src['file']}"
            )
        if src["grid"] == "day":
            _extract_day_grid(src, path, result, contract["branch_headers"])
        else:
            _extract_transactions(src, path, result)
    return result


# --------------------------------------------------------------------------- #
# day tab sources: production / dispatch / waste / returns
# --------------------------------------------------------------------------- #

def _extract_day_grid(src, path, result, all_branch_headers):
    day_cfg = src["day_sheet"]
    ignore_sheets = {norm_text(k) for k in (src.get("ignore_sheets") or {})}
    aliases = {norm_text(k): norm_text(v) for k, v in (src.get("branch_aliases") or {}).items()}
    ignore_cols = {norm_text(k) for k in (src.get("ignore_columns") or {})}
    aggregate_items = {norm_text(x) for x in (src.get("aggregate_rows") or [])}
    row_total_header = norm_text(src.get("row_total_column") or "")

    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        sheet_info = result.sheets.setdefault(src["id"], {})
        for sheet_name in wb.sheetnames:
            ws = wb[sheet_name]
            if norm_text(sheet_name) in ignore_sheets:
                sheet_info[sheet_name] = "ignored_by_contract"
                continue
            day, fixed = day_from_sheet(
                sheet_name, day_cfg["regex"], day_cfg.get("fix_letter_O", False)
            )
            if day is None:
                sheet_info[sheet_name] = "unknown_sheet"
                result.quarantines.append(_quarantine(
                    "unknown_sheet", src, sheet_name,
                    detail="sheet name does not match the day pattern",
                ))
                continue
            if fixed:
                result.notes.append(_note(
                    "info", src["id"], sheet_name,
                    f"letter-O typo resolved: {sheet_name!r} parsed as day {day}",
                ))
            date = iso_date(src["period"]["year"], src["period"]["month"], day)
            if date is None:  # e.g. a 31st typed into a 30-day month
                sheet_info[sheet_name] = "bad_date"
                result.quarantines.append(_quarantine(
                    "bad_date", src, sheet_name,
                    detail=f"day {day} does not exist in {src['period']}",
                ))
                continue

            sheet_result = _read_day_sheet(
                src, ws, date,
                branch_headers={norm_text(h) for h in all_branch_headers},
                aliases=aliases,
                ignore_cols=ignore_cols,
                ignore_reasons=src.get("ignore_columns") or {},
                aggregate_items=aggregate_items,
                row_total_header=row_total_header,
                header_search_rows=src.get("header_search_rows", 3),
            )
            rows, quars, notes, values_seen = sheet_result
            sheet_info[sheet_name] = (
                "day_sheet_with_values" if values_seen else "day_sheet_no_recorded_values"
            )
            result.rows.extend(rows)
            result.quarantines.extend(quars)
            result.notes.extend(notes)
    finally:
        wb.close()


def _read_day_sheet(src, ws, date, branch_headers, aliases, ignore_cols,
                    ignore_reasons, aggregate_items, row_total_header,
                    header_search_rows):
    """Read one day tab.

    gives back (rows, quarantines, notes, values_seen).

    rules, all declared in the contract:
    - column A is the row number, never data. the header can sit lower, the
      dispatch 22nd tab has a number above it.
    - a known branch header loads. a typo header loads under the contract name
      and every use is noted. anything else unexpected is quarantined per value.
      a header with no text gets a note.
    - derived columns (row total, price, money, the side variance table) are
      ignored by contract, with a note naming them when they hold something.
    - the TOTAL row never becomes a product. values typed into its branch cells
      are quarantined.
    - if the contract gives us the sheet's own TOTAL column we compare it to
      the sum we parsed and note the rows that disagree.
    """
    rows: list[dict] = []
    quars: list[dict] = []
    notes: list[dict] = []
    item_header = norm_text(src["item_header"])

    grid = [tuple(r) for r in ws.iter_rows(values_only=True)]
    header_row_idx = None
    for idx, row in enumerate(grid[: max(header_search_rows, 1)]):
        if any(norm_text(cell) == item_header for cell in row):
            header_row_idx = idx
            break
    if header_row_idx is None:
        return rows, [_quarantine(
            "unparsable_row", src, ws.title,
            detail=f"no {item_header!r} header in the first {header_search_rows} rows",
        )], notes, False

    header = grid[header_row_idx]
    item_col = next(i for i, cell in enumerate(header) if norm_text(cell) == item_header)

    branch_cols: dict[int, str] = {}
    ignored_cols: dict[int, str] = {}
    unmapped: dict[int, str] = {}
    unnamed: list[int] = []
    used_aliases: set[str] = set()

    for i in range(item_col + 1, len(header)):
        text = norm_text(header[i])
        if not text:
            unnamed.append(i)
            continue
        canon = aliases.get(text, text)
        if canon in branch_headers:
            branch_cols[i] = canon
            if canon != text:
                used_aliases.add(f"{text} -> {canon}")
        elif text in ignore_cols:
            ignored_cols[i] = text
        else:
            unmapped[i] = text

    if unmapped:
        quars.append(_quarantine(
            "unmapped_column", src, ws.title,
            detail="headers outside the contract branch list: " + ", ".join(unmapped.values()),
        ))

    total_col = next((i for i, t in ignored_cols.items() if t == row_total_header), None)

    ignored_value_counts: dict[int, int] = {}
    unnamed_value_counts: dict[int, int] = {}
    row_total_mismatches: list[str] = []
    values_seen = False

    for row in grid[header_row_idx + 1:]:
        product = norm_text(row[item_col] if item_col < len(row) else None)

        def cell_at(i):
            return row[i] if i < len(row) else None

        for i in ignored_cols:
            if cell_at(i) is not None:
                ignored_value_counts[i] = ignored_value_counts.get(i, 0) + 1
        for i in unnamed:
            if cell_at(i) is not None:
                unnamed_value_counts[i] = unnamed_value_counts.get(i, 0) + 1

        if product == "":
            branch_cells_nonblank = any(
                cell_at(i) is not None and str(cell_at(i)).strip() != ""
                for i in branch_cols
            )
            if branch_cells_nonblank or any(cell_at(i) is not None for i in unmapped):
                quars.append(_quarantine(
                    "missing_product", src, ws.title,
                    detail="value present without an item name",
                ))
            continue

        if any(cell_at(i) is not None for i in unmapped):
            for i in unmapped:
                if cell_at(i) is not None:
                    quars.append(_quarantine(
                        "unmapped_column", src, ws.title,
                        product=product,
                        detail=f"value in an unmapped column {unmapped[i]!r} "
                               f"(column {get_column_letter(i + 1)})",
                    ))

        if product in aggregate_items:
            # Aggregate row: never a product. a value typed into its branch
            # cells is quarantined so it stays visible. the derived columns on
            # this row are already out, see ignore_columns.
            for i in branch_cols:
                value = cell_at(i)
                if value is None or (isinstance(value, str) and value.strip() == ""):
                    continue
                quars.append(_quarantine(
                    "aggregate_row_value", src, ws.title,
                    product=product, branch=branch_cols[i],
                    detail=f"stray value {value!r} inside an aggregate row",
                ))
            continue

        row_sum = 0.0
        row_had_value = False
        for i, branch in sorted(branch_cols.items()):
            qty, err = parse_qty(cell_at(i))
            if err:
                quars.append(_quarantine(
                    "non_numeric_qty", src, ws.title,
                    product=product, branch=branch, detail=str(err),
                ))
                continue
            if qty is None:
                continue  # blank cell: not recorded
            if qty < 0:
                quars.append(_quarantine(
                    "negative_qty", src, ws.title,
                    product=product, branch=branch, detail=f"qty {qty}",
                ))
                continue
            row_sum = round(row_sum + qty, 6)
            row_had_value = True
            rows.append({
                "fact": src["fact"], "source_id": src["id"], "date": date,
                "product": product, "branch": branch, "qty": qty,
                "amount": None, "partner": None, "operation": None,
                "source_file": src["file"], "source_sheet": ws.title,
            })
        if row_had_value:
            values_seen = True

        if row_had_value and total_col is not None:
            total, total_err = parse_qty(cell_at(total_col))
            if total is not None and total_err is None:
                if abs(round(total - row_sum, 6)) > EPS:
                    row_total_mismatches.append(
                        f"{product} (branch sum {row_sum} vs sheet total {total})"
                    )

    for i, count in ignored_value_counts.items():
        header_text = ignored_cols[i]
        reason = ignore_reasons.get(header_text, "")
        notes.append(_note(
            "info", src["id"], ws.title,
            f"ignored derived column {header_text!r} (column "
            f"{get_column_letter(i + 1)}) held {count} value(s) -- excluded by "
            f"contract: {reason}",
        ))
    for i, count in unnamed_value_counts.items():
        notes.append(_note(
            "anomaly", src["id"], ws.title,
            f"unnamed column {get_column_letter(i + 1)} held {count} value(s); "
            "not loaded: no header exists to give it meaning",
        ))
    if used_aliases:
        notes.append(_note(
            "info", src["id"], ws.title,
            "branch alias applied for this sheet's header(s): " + ", ".join(used_aliases),
        ))
    if row_total_mismatches:
        examples = "; ".join(row_total_mismatches[:3])
        notes.append(_note(
            "anomaly", src["id"], ws.title,
            f"{len(row_total_mismatches)} row(s) where the sheet's own "
            f"{row_total_header!r} column disagrees with the sum of the branch "
            f"cells: {examples}",
        ))

    return rows, quars, notes, values_seen


# --------------------------------------------------------------------------- #
# transaction sources: the two weekly sales workbooks
# --------------------------------------------------------------------------- #

def _extract_transactions(src, path, result):
    target = src["sheet"]
    ignore_sheets = {norm_text(k) for k in (src.get("ignore_sheets") or {})}
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        if target not in wb.sheetnames:
            raise ExtractionError(
                f"source {src['id']!r}: contract-required sheet {target!r} not in {src['file']}"
            )
        sheet_info = result.sheets.setdefault(src["id"], {})
        for sheet_name in wb.sheetnames:
            if sheet_name != target and norm_text(sheet_name) in ignore_sheets:
                sheet_info[sheet_name] = "ignored_by_contract"

        rows, quars, data_quars = _read_transactions(
            src, wb[target], src.get("header_search_rows", 3)
        )
        sheet_info[target] = "transactions"
        result.rows.extend(rows)
        result.quarantines.extend(quars)
        result.notes.append(_note(
            "info", src["id"], target,
            f"read {len(rows) + data_quars} data rows from {target!r}; {len(rows)} accepted",
        ))
    finally:
        wb.close()


def _read_transactions(src, ws, header_search_rows=3):
    """Find the header row (the sales grids start with a blank row, so it is on
    row 2), map the contract columns, then read the rows below it."""
    rows_iter = ws.iter_rows(values_only=True)
    grid = [tuple(r) for r in ws.iter_rows(values_only=True)]

    required = [f for f in ("date", "product", "branch", "qty")
                if src["columns"].get(f) is not None]
    header_idx = None
    positions: dict[str, Optional[int]] = {}
    within = grid[: max(header_search_rows, 1)]
    for idx, row in enumerate(within):
        cell_lookup = {
            norm_text(cell): i for i, cell in enumerate(row) if cell is not None
        }
        mapping: dict[str, Optional[int]] = {}
        missing = []
        for fieldx, header_name in src["columns"].items():
            idx_hit = None if header_name is None else cell_lookup.get(norm_text(header_name))
            mapping[fieldx] = idx_hit
            if idx_hit is None and fieldx in required:
                missing.append(header_name)
        if not missing:
            header_idx = idx
            positions = mapping
            break
    if header_idx is None:
        raise ExtractionError(
            f"source {src['id']!r}: required columns "
            f"{[src['columns'][f] for f in required]} not found in the first "
            f"{header_search_rows} rows of {ws.title!r}"
        )

    colmap = positions

    rows: list[dict] = []
    quars: list[dict] = []
    operations = src.get("operation_accept") or None
    accept = {op.upper() for op in operations} if operations else None
    fmt = src["date_format"]

    for row in grid[header_idx + 1:]:
        if not row or all(cell is None for cell in row):
            continue

        def field(field_name):
            idx = colmap.get(field_name)
            return row[idx] if idx is not None and idx < len(row) else None

        if accept is not None:
            operation = norm_label(field("operation"))
            if operation.upper() not in accept:
                quars.append(_quarantine(
                    "operation_not_sale", src, ws.title,
                    detail=f"operation {operation!r} is outside the contract's accepted set",
                ))
                continue

        date, date_err = parse_tx_date(field("date"), fmt)
        if date is None:
            quars.append(_quarantine("bad_date", src, ws.title, detail=str(date_err)))
            continue

        product = norm_text(field("product"))
        if product == "":
            quars.append(_quarantine(
                "missing_product", src, ws.title, date=date,
                detail="transaction without an item name",
            ))
            continue

        branch = norm_text(field("branch"))
        if branch == "":
            quars.append(_quarantine(
                "missing_branch", src, ws.title, date=date, product=product,
                detail="transaction without a location/branch",
            ))
            continue

        qty, qty_err = parse_qty(field("qty"))
        if qty_err:
            quars.append(_quarantine(
                "non_numeric_qty", src, ws.title, date=date, product=product,
                branch=branch, detail=str(qty_err),
            ))
            continue
        if qty is None:
            quars.append(_quarantine(
                "missing_quantity", src, ws.title, date=date, product=product,
                branch=branch, detail="transaction without a quantity",
            ))
            continue
        if qty < 0:
            quars.append(_quarantine(
                "negative_qty", src, ws.title, date=date, product=product,
                branch=branch, detail=f"qty {qty}",
            ))
            continue

        amount, amount_err = parse_qty(field("amount"))
        if (amount_err is None) and (amount is not None) and amount < 0:
            quars.append(_quarantine(
                "negative_amount", src, ws.title, date=date,
                product=product, branch=branch, detail=f"amount {amount}",
            ))
            amount = None  # row is good data; only the amount is rejected
        elif amount_err:
            quars.append(_quarantine(
                "amount_non_numeric", src, ws.title, date=date,
                product=product, branch=branch, detail=str(amount_err),
            ))
            amount = None

        rows.append({
            "fact": src["fact"], "source_id": src["id"], "date": date,
            "product": product, "branch": branch, "qty": qty,
            "amount": amount, "partner": norm_label(field("partner")) or None,
            "operation": norm_label(field("operation")) or None,
            "source_file": src["file"], "source_sheet": ws.title,
        })

    data_reasons = {
        "bad_date", "missing_product", "missing_branch", "missing_quantity",
        "non_numeric_qty", "negative_qty", "operation_not_sale",
    }
    return rows, quars, sum(1 for q in quars if q["reason"] in data_reasons)
