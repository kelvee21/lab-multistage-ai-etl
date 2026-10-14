"""Cleaning helpers. conservative: if we are not sure, we quarantine."""
from __future__ import annotations

import calendar
import re
import datetime as dt
from typing import Optional, Tuple

WHITESPACE = re.compile(r"\s+")


def norm_text(value: object) -> str:
    """trim, collapse spaces inside, uppercase. None gives ''."""
    if value is None:
        return ""
    return WHITESPACE.sub(" ", str(value)).strip().upper()


def norm_label(value: object) -> str:
    """trim and collapse spaces, keep the case. for free text like Partner."""
    if value is None:
        return ""
    return WHITESPACE.sub(" ", str(value)).strip()


def parse_qty(value: object) -> Tuple[Optional[float], Optional[str]]:
    """give back (value, error).

    (float, None)  we read the number
    (None, None)   cell is blank = not recorded
    (None, detail) we cannot read it, caller must quarantine it
    """
    if value is None:
        return None, None
    if isinstance(value, bool):
        return None, f"unexpected boolean {value!r}"
    if isinstance(value, (int, float)):
        return round(float(value), 6), None
    if isinstance(value, str):
        text = value.strip()
        if text == "":
            return None, None
        collapsed = text.replace(" ", "")
        if re.fullmatch(r"\d+", collapsed):
            return float(collapsed), None
        if re.fullmatch(r"\d+,\d{3}", collapsed):  # thousands separator: 247,200
            return float(collapsed.replace(",", "")), None
        return None, f"cannot parse number {text!r}"
    return None, f"unexpected cell type {type(value).__name__} ({value!r})"


def parse_tx_date(value: object, fmt: str) -> Tuple[Optional[str], Optional[str]]:
    """sales grid dates. real excel date, or text in the contract's format."""
    if value is None:
        return None, "empty date cell"
    if isinstance(value, dt.datetime):
        return value.date().isoformat(), None
    if isinstance(value, dt.date):
        return value.isoformat(), None
    if isinstance(value, str):
        try:
            return dt.datetime.strptime(value.strip(), fmt).date().isoformat(), None
        except ValueError:
            return None, f"not a {fmt} date: {value.strip()!r}"
    return None, f"unexpected date type {type(value).__name__} ({value!r})"


def day_from_sheet(
    sheet_name: str, regex: str, fix_letter_o: bool
) -> Tuple[Optional[int], bool]:
    """day number from a day tab name.

    gives back (day, was_fixed). (None, False) means not a day tab.
    the letter-O rule only exists for the real 1OTH JUNE typo. it swaps O for 0
    and runs the same pattern again, nothing else gets a second chance.
    """
    match = re.match(regex, sheet_name, re.IGNORECASE)
    if match:
        return int(match.group(1)), False
    if fix_letter_o and "O" in sheet_name:
        candidate = sheet_name.replace("O", "0")
        match = re.match(regex, candidate, re.IGNORECASE)
        if match:
            return int(match.group(1)), True
    return None, False


def iso_date(year: int, month: int, day: int) -> Optional[str]:
    """iso date for a contract period. gives None on a day that does not exist."""
    last = calendar.monthrange(year, month)[1]
    if not 1 <= day <= last:
        return None
    return f"{year:04d}-{month:02d}-{day:02d}"
