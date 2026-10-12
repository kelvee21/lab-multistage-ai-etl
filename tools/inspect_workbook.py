"""Dump xlsx sheets as text so the extraction rules come from the files.

stdlib only (zipfile + ElementTree), so it runs anywhere python runs.

  python tools/inspect_workbook.py PATH [--rows 8] [--cols 14] [--out FILE]
"""
from __future__ import annotations

import argparse
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pr": "http://schemas.openxmlformats.org/package/2006/relationships",
}


def _col_letters(ref: str) -> tuple[int, int]:
    """'BC12' -> (column index 0, row index 0)."""
    m = re.match(r"([A-Z]+)(\d+)", ref or "")
    if not m:
        return 0, 0
    col = 0
    for ch in m.group(1):
        col = col * 26 + (ord(ch) - 64)
    return col - 1, int(m.group(2)) - 1


class Workbook:
    def __init__(self, path: Path) -> None:
        self.zf = zipfile.ZipFile(path)
        self.shared: list[str] = []
        if "xl/sharedStrings.xml" in self.zf.namelist():
            root = ET.fromstring(self.zf.read("xl/sharedStrings.xml"))
            for si in root.findall("m:si", NS):
                self.shared.append("".join(t.text or "" for t in si.iter("{%s}t" % NS["m"])))
        wroot = ET.fromstring(self.zf.read("xl/workbook.xml"))
        rels = ET.fromstring(self.zf.read("xl/_rels/workbook.xml.rels"))
        targets = {}
        for rel in rels.findall("pr:Relationship", NS):
            targets[rel.get("Id")] = rel.get("Target")
        self.sheets: list[tuple[str, str]] = []
        for sh in wroot.findall(".//m:sheet", NS):
            rid = sh.get("{%s}id" % NS["r"])
            target = targets.get(rid, "")
            if not target.startswith("/"):
                target = "xl/" + target
            else:
                target = target.lstrip("/")
            self.sheets.append((sh.get("name") or "?", target))

    def cell_text(self, c: ET.Element) -> str:
        t = c.get("t", "n")
        v = c.find("m:v", NS)
        if v is None:
            inline = c.find("m:is", NS)
            return "".join(x.text or "" for x in inline.iter("{%s}t" % NS["m"])) if inline is not None else ""
        raw = v.text or ""
        if t == "s":
            try:
                return self.shared[int(raw)]
            except (ValueError, IndexError):
                return "<bad-shared:" + raw + ">"
        return raw

    def dump_sheet(self, first_rows: int, first_cols: int) -> str:
        rows_out: list[str] = []
        try:
            root = ET.fromstring(self.zf.read(self._current))
        except KeyError:
            return "  <sheet part missing>"
        data = root.find("m:sheetData", NS)
        if data is None:
            return "  <no sheetData>"
        for row in data.findall("m:row", NS)[:first_rows]:
            cells: dict[int, str] = {}
            for c in row.findall("m:c", NS):
                col, _ = _col_letters(c.get("r", ""))
                if col < first_cols:
                    txt = self.cell_text(c).replace("\n", "\\n")
                    cells[col] = txt[:24]
            width = max(cells.keys(), default=-1) + 1
            items = [cells.get(i, "") for i in range(max(width, first_cols))]
            if any(x.strip() for x in items):
                rows_out.append("   " + " | ".join(items))
        return "\n".join(rows_out) if rows_out else "   <empty in window>"

    def dump(self, first_rows: int, first_cols: int) -> str:
        out = []
        for name, part in self.sheets:
            self._current = part
            out.append(f"=== SHEET: {name!r}")
            out.append(self.dump_sheet(first_rows, first_cols))
        return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx")
    ap.add_argument("--rows", type=int, default=8)
    ap.add_argument("--cols", type=int, default=14)
    ap.add_argument("--out", help="write dump to this file instead of stdout")
    args = ap.parse_args()
    wb = Workbook(Path(args.xlsx))
    dump = wb.dump(args.rows, args.cols)
    header = (
        f"# {args.xlsx}\n"
        f"sheets: {len(wb.sheets)}\n"
        "names: " + ", ".join(n for n, _ in wb.sheets) + "\n\n"
    )
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(header + dump, encoding="utf-8")
        print(f"wrote {args.out} ({len(header + dump)} chars, {len(wb.sheets)} sheets)")
    else:
        sys.stdout.write(header + dump + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
