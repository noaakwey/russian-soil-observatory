#!/usr/bin/env python3
"""Stage literal ``mean ± spread`` OCR cells from header-grounded tables.

The ordinary table pass deliberately accepts only a scalar number.  Scientific
tables frequently report a mean and error (``4.6 ± 1.0``); ignoring these rows
needlessly loses measurements, while silently dropping the error is equally
wrong.  This additive pass retains the entire string in ``value_text`` and
uses its first number only as a sortable candidate value.  It never changes
the operational measurement layer.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

from extract_table_measurement_candidates import HEADER_UNIT, TABLE_DEPTH, property_for
from ingest_pochvovedenie_text import DEPTH, HORIZON, num


MEAN_SD = re.compile(
    r"^\s*(-?\d+(?:[.,]\d+)?)\s*(?:±|\+/-)\s*(\d+(?:[.,]\d+)?)\s*(.*?)\s*$"
)
SCALAR = re.compile(r"^\s*-?\d+(?:[.,]\d+)?\s*(?:%|[A-Za-zА-Яа-я/³]+)?\s*$")


def matrix(con: sqlite3.Connection, artifact_id: str) -> dict[int, dict[int, str]]:
    result: dict[int, dict[int, str]] = defaultdict(dict)
    for row, col, text, rowspan in con.execute(
        "SELECT row_index,column_index,text_raw,rowspan FROM table_cell WHERE artifact_id=? ORDER BY row_index,column_index",
        (artifact_id,),
    ):
        for target in range(row, row + rowspan):
            result[target].setdefault(col, text)
    return result


def is_numeric(text: str) -> bool:
    return bool(MEAN_SD.match(text or "") or SCALAR.match(text or ""))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--corpus", default="pochvovedenie")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats: Counter[str] = Counter()
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        artifacts = con.execute("""SELECT a.artifact_id
            FROM source_artifact a JOIN document d ON d.document_id=a.document_id
            WHERE d.corpus=? AND a.artifact_type='table_json' AND a.source_path NOT LIKE '%#article=%'""",
            (args.corpus,)).fetchall()
        for no, (artifact_id,) in enumerate(artifacts, start=1):
            cells = matrix(con, artifact_id)
            columns = {col for row in cells.values() for col in row}
            ordered = sorted(cells)
            if not columns or not ordered:
                continue
            threshold = max(2, len(columns) // 3)
            data_start = next((row for row in ordered if sum(is_numeric(value) for value in cells[row].values()) >= threshold), None)
            if data_start is None:
                continue
            headers: dict[int, tuple[str, str]] = {}
            for col in columns:
                raw_header = " ".join(cells[row].get(col, "") for row in ordered if row < data_start).strip()
                property_id = property_for(raw_header)
                if property_id:
                    headers[col] = (property_id, raw_header)
            if not headers:
                continue
            stats["tables"] += 1
            for row in ordered:
                if row < data_start:
                    continue
                values = cells[row]
                row_text = " | ".join(values.values())
                depth = DEPTH.search(row_text)
                horizon = HORIZON.search(row_text)
                depth_cell = next((TABLE_DEPTH.match(value) for value in values.values() if TABLE_DEPTH.match(value)), None)
                labels = [value for col, value in sorted(values.items()) if col not in headers and not is_numeric(value)]
                row_label = " | ".join(labels) or None
                for col, (property_id, raw_header) in headers.items():
                    raw = values.get(col, "")
                    match = MEAN_SD.match(raw)
                    if not match:
                        continue
                    candidate_id = f"{artifact_id}:tm-stat:r{row}:c{col}"
                    if not args.dry_run:
                        con.execute("""INSERT INTO table_measurement_candidate
                          (candidate_id,artifact_id,row_index,column_index,property_id,property_header_raw,
                           value_num,value_text,unit_raw,row_label_raw,horizon_label,depth_top_cm,depth_bottom_cm,status)
                          VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'unreviewed')
                          ON CONFLICT(candidate_id) DO NOTHING""",
                          (candidate_id, artifact_id, row, col, property_id, raw_header, num(match.group(1)), raw,
                           match.group(3).strip() or (HEADER_UNIT.search(raw_header).group(0) if HEADER_UNIT.search(raw_header) else None),
                           row_label, horizon.group(1) if horizon else None,
                           num(depth.group(1)) if depth else (float(depth_cell.group(1)) if depth_cell else None),
                           num(depth.group(2)) if depth else (float(depth_cell.group(2)) if depth_cell else None)))
                    stats["candidates"] += 1
            if no % 100 == 0 and not args.dry_run:
                con.commit()
        if not args.dry_run:
            con.commit()
    print(json.dumps(dict(stats), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
