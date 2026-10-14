"""Reader for the day tab shape of source file.

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
        _extract_day_grid(src, path, result, contract["branch_headers"])
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
