#!/usr/bin/env python3
"""Recover a table only when OCR split its header and body into neighbours.

Table crops occasionally contain a two-row header as one JSON artifact and
the data matrix as the immediately following artifact.  Treating either crop
alone loses information; guessing across an article would be unsafe.  This
stage therefore links only adjacent artifacts in the same document and page
with the same column count, where the first has recognised property headers
and the second has numeric data rows.

The result remains an ``unreviewed`` table candidate.  ``table_candidate_header_link``
records both raw artifacts so a reviewer can inspect the actual header and the
actual value cell independently.
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


NUMBER = re.compile(r"^\s*(-?\d+(?:[.,]\d+)?)(?:\s*(?:±|\+/-)\s*\d+(?:[.,]\d+)?)?\s*$")


def artifact_order(path: str) -> tuple[int, int]:
    """Extract page and OCR-crop number from a raw JSON filename."""
    match = re.search(r"_p(\d+)(?:-\d+)?_t(\d+)\.json$", path)
    return (int(match.group(1)), int(match.group(2))) if match else (10**9, 10**9)


def artifact_matrix(con: sqlite3.Connection, artifact_id: str) -> list[list[str]]:
    cells: dict[int, dict[int, str]] = defaultdict(dict)
    for row, col, text in con.execute(
        "SELECT row_index,column_index,text_raw FROM table_cell WHERE artifact_id=? ORDER BY row_index,column_index",
        (artifact_id,),
    ):
        cells[row][col] = text
    return [[cells[row].get(col, "") for col in range(max(cells[row], default=-1) + 1)]
            for row in sorted(cells)]


def header_map(matrix: list[list[str]]) -> dict[int, tuple[str, str]]:
    if not matrix:
        return {}
    width = max(map(len, matrix), default=0)
    result = {}
    for col in range(width):
        text = " ".join(row[col] for row in matrix if col < len(row) and row[col].strip()).strip()
        prop = property_for(text)
        if prop:
            result[col] = (prop, text)
    return result


def clean_header_fragment(text: str) -> bool:
    """Reject a would-be header that visibly contains a vector of data.

    Chemical formulae (H2O, CaCO3) are stripped first: their subscripts are
    part of the name, not a measurement.  A remaining digit means the OCR crop
    has mixed values into the header and must be held for manual review.
    """
    simplified = re.sub(r"(?:H[₂2]O|CaCO[₃3]|CaSO[₄4]|P[₂2]O[₅5]|K[₂2]O)", "", text, flags=re.I)
    return not bool(re.search(r"\d", simplified))


def numeric_value(text: str) -> tuple[float | None, str | None]:
    match = NUMBER.match(text or "")
    if not match:
        return None, None
    return num(match.group(1)), text.strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--corpus", default="pochvovedenie")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats: Counter[str] = Counter()
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            con.execute("""CREATE TABLE IF NOT EXISTS table_candidate_header_link (
                candidate_id TEXT PRIMARY KEY REFERENCES table_measurement_candidate(candidate_id),
                header_artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
                value_artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
                linkage_rule TEXT NOT NULL
            )""")
        docs = con.execute("SELECT document_id FROM document WHERE corpus=? ORDER BY document_id", (args.corpus,)).fetchall()
        for (document_id,) in docs:
            artifacts = con.execute("""SELECT artifact_id,source_path,page_start,page_end
                FROM source_artifact WHERE document_id=? AND artifact_type='table_json'
                AND source_path NOT LIKE '%#article=%' ORDER BY source_path""", (document_id,)).fetchall()
            artifacts = sorted(artifacts, key=lambda r: artifact_order(r[1]))
            for head, body in zip(artifacts, artifacts[1:]):
                head_id, head_path, head_start, head_end = head
                body_id, body_path, body_start, body_end = body
                head_page, head_no = artifact_order(head_path)
                body_page, body_no = artifact_order(body_path)
                if head_page != body_page or body_no != head_no + 1:
                    continue
                hmatrix = artifact_matrix(con, head_id)
                bmatrix = artifact_matrix(con, body_id)
                headers = header_map(hmatrix)
                if not headers or not bmatrix or len(hmatrix) > 3:
                    continue
                if any(not clean_header_fragment(raw_header) for _pid, raw_header in headers.values()):
                    stats["rejected_mixed_header_data"] += 1
                    continue
                width = max(map(len, hmatrix), default=0)
                if width != max(map(len, bmatrix), default=0):
                    continue
                # A body must actually provide values under at least one
                # recognized header.  This excludes caption/header neighbours.
                if not any(numeric_value(row[col] if col < len(row) else "")[0] is not None
                           for row in bmatrix for col in headers):
                    continue
                stats["linked_fragments"] += 1
                for row_index, row in enumerate(bmatrix):
                    row_text = " | ".join(value for value in row if value)
                    depth = DEPTH.search(row_text)
                    table_depth = next((TABLE_DEPTH.match(value) for value in row if TABLE_DEPTH.match(value)), None)
                    horizon = HORIZON.search(row_text)
                    labels = [value for col, value in enumerate(row)
                              if col not in headers and value and numeric_value(value)[0] is None]
                    row_label = " | ".join(labels) or None
                    for col, (property_id, raw_header) in headers.items():
                        value, raw = numeric_value(row[col] if col < len(row) else "")
                        if value is None:
                            continue
                        candidate_id = f"{body_id}:split-header:{head_id}:r{row_index}:c{col}"
                        if not args.dry_run:
                            con.execute("""INSERT INTO table_measurement_candidate
                                (candidate_id,artifact_id,row_index,column_index,property_id,property_header_raw,
                                 value_num,value_text,unit_raw,row_label_raw,horizon_label,depth_top_cm,depth_bottom_cm,status)
                                VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,?,'unreviewed')
                                ON CONFLICT(candidate_id) DO NOTHING""",
                                (candidate_id, body_id, row_index, col, property_id, raw_header, value,
                                 HEADER_UNIT.search(raw_header).group(0) if HEADER_UNIT.search(raw_header) else None,
                                 row_label, horizon.group(1) if horizon else None,
                                 num(depth.group(1)) if depth else (float(table_depth.group(1)) if table_depth else None),
                                 num(depth.group(2)) if depth else (float(table_depth.group(2)) if table_depth else None)))
                            con.execute("""INSERT INTO table_candidate_header_link
                                (candidate_id,header_artifact_id,value_artifact_id,linkage_rule)
                                VALUES(?,?,?,'adjacent_same_page_same_width')
                                ON CONFLICT(candidate_id) DO UPDATE SET
                                  header_artifact_id=excluded.header_artifact_id,value_artifact_id=excluded.value_artifact_id,
                                  linkage_rule=excluded.linkage_rule""", (candidate_id, head_id, body_id))
                        stats["candidates"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(dict(stats), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
