"""Load and check the extraction contract.

strict on purpose. a contract with a typo in a rule has to stop the run, not
extract an empty warehouse and call it a success.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

SOURCE_GRIDS = ("day", "transactions")


class ContractError(Exception):
    """contract file missing, broken json, or a rule that does not make sense."""


def load_contract(path: Path) -> dict:
    try:
        with path.open("r", encoding="utf-8") as fh:
            contract = json.load(fh)
    except FileNotFoundError as exc:
        raise ContractError(f"contract file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ContractError(f"contract is not valid JSON: {path}: {exc}") from exc
    _validate(contract, path)
    return contract


def _validate(contract: dict, path: Path) -> None:
    problems: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            problems.append(msg)

    need(isinstance(contract, dict), f"{path}: contract must be a JSON object")
    if problems:
        return

    sources = contract.get("sources")
    need(isinstance(sources, list) and sources, f"{path}: 'sources' must be a non-empty list")
    if problems:
        return

    seen_ids: set[str] = set()
    branch_headers = contract.get("branch_headers")
    need(isinstance(branch_headers, list) and branch_headers, f"{path}: 'branch_headers' must be a non-empty list")

    for src in sources:
        sid = src.get("id")
        need(bool(sid), f"{path}: every source needs an 'id'")
        if sid:
            need(sid not in seen_ids, f"{path}: duplicate source id {sid!r}")
            seen_ids.add(sid)
        need(bool(src.get("file")), f"{path}: source {sid!r} needs 'file'")
        need(src.get("grid") in SOURCE_GRIDS, f"{path}: source {sid!r} needs grid in {SOURCE_GRIDS}")
        need(bool(src.get("fact")), f"{path}: source {sid!r} needs 'fact'")

        if src.get("grid") == "day":
            period = src.get("period") or {}
            year, month = period.get("year"), period.get("month")
            need(isinstance(year, int) and isinstance(month, int) and 1 <= month <= 12,
                 f"{path}: source {sid!r} needs period.year and period.month (1..12)")
            days = src.get("expected_days") or {}
            need(isinstance(days.get("from"), int) and isinstance(days.get("to"), int),
                 f"{path}: source {sid!r} needs expected_days.from/to as ints")
            day_sheet = src.get("day_sheet") or {}
            try:
                re.compile(day_sheet.get("regex", ""))
            except re.error:
                problems.append(f"{path}: source {sid!r} day_sheet.regex does not compile")

        elif src.get("grid") == "transactions":
            need(bool(src.get("sheet")), f"{path}: source {sid!r} needs 'sheet'")
            cols = src.get("columns") or {}
            for required in ("date", "product", "branch", "qty"):
                need(bool(cols.get(required)), f"{path}: source {sid!r} columns.{required} missing")
            need(bool(src.get("date_format")), f"{path}: source {sid!r} needs date_format")

    if problems:
        raise ContractError("\n".join(problems))
