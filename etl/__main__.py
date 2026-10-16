"""python -m etl run - extract, gate, load, report.

stdout only ever gets counts and paths. no business row goes into a log, so the
run output is safe to share.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import __version__
from .contract import ContractError, load_contract
from .extract import ExtractionError, extract_all
from .load import load_warehouse
from .validate import gate, write_quarantine_csvs, write_report

DEFAULT_ROOT = Path(__file__).resolve().parents[1]


def run(repo_root: Path, contract_path: Path, raw_dir: Path, out_dir: Path, quiet: bool = False) -> int:
    started = time.perf_counter()

    contract = load_contract(contract_path)
    if not quiet:
        print(f"contract:  {contract_path} (v{contract['version']})")
        print(f"sources:   {len(contract['sources'])}")

    extract_started = time.perf_counter()
    extraction = extract_all(contract, raw_dir)
    extract_seconds = time.perf_counter() - extract_started

    gate_started = time.perf_counter()
    gate_result = gate(extraction, contract)
    gate_seconds = time.perf_counter() - gate_started

    load_started = time.perf_counter()
    processed_dir = out_dir / "processed"
    warehouse = load_warehouse(gate_result, processed_dir, contract["branch_headers"])
    load_seconds = time.perf_counter() - load_started

    written_csvs = write_quarantine_csvs(gate_result, processed_dir)
    runtime_seconds = time.perf_counter() - started
    report_path = write_report(gate_result, processed_dir, runtime_seconds, contract["version"])

    if not quiet:
        print(f"\nextract: {extract_seconds:.1f}s | gate: {gate_seconds:.1f}s | "
              f"load: {load_seconds:.1f}s | total: {runtime_seconds:.1f}s")

        print("\nper source (rows seen -> accepted | quarantines by reason):")
        for entry in gate_result.report["sources"]:
            quars = entry["quarantines_by_reason"] or {"-": 0}
            quars_txt = ", ".join(f"{k}={v}" for k, v in sorted(quars.items()))
            print(f"  {entry['id']:<10} {entry['rows_in']:>6} -> {entry['rows_loaded']:>6} | {quars_txt}")

        print("\nper fact:")
        for fact, stats in gate_result.by_fact.items():
            print(f"  {fact:<10} rows={stats['rows_loaded']}")

        print(f"\ndimensions: branches={warehouse['branches']} products={warehouse['products']}")
        anomalies = sum(1 for n in gate_result.report["notes"] if n["level"] == "anomaly")
        infos = sum(1 for n in gate_result.report["notes"] if n["level"] == "info")
        print(f"notes:      info={infos} anomalies={anomalies}")
        print(f"warehouse:  {warehouse['warehouse']}")
        print(f"csv:        {warehouse['csv_dir']}")
        print(f"quarantine: {out_dir / 'processed' / 'quarantine'}")
        print(f"report:     {report_path}")
        if written_csvs:
            print(f"            (quarantine CSVs: {', '.join(written_csvs.values())})")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="etl", description="BROOD DataOps ETL")
    parser.add_argument("command", choices=["run"], help="only 'run' for now")
    parser.add_argument("--contract", default=str(DEFAULT_ROOT / "outputs" / "extraction_contract.json"))
    parser.add_argument("--raw", default=str(DEFAULT_ROOT / "data" / "raw"))
    parser.add_argument("--out", default=str(DEFAULT_ROOT / "data"))
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args(argv)

    # out holds processed/, data/raw stays untouched.
    try:
        return run(
            repo_root=DEFAULT_ROOT,
            contract_path=Path(args.contract),
            raw_dir=Path(args.raw),
            out_dir=Path(args.out),
            quiet=args.quiet,
        )
    except (ContractError, ExtractionError) as exc:
        print(f"etl: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
