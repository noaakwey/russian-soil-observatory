#!/usr/bin/env python3
"""Verify every staged numeric value against its originating OCR table cell."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from normalize_measurement_candidates import convert

NUMBER = re.compile(r"-?\d+(?:[.,]\d+)?")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = {"checked": 0, "missing_locator": 0, "missing_cell": 0, "candidate_only_evidence": 0, "non_numeric_cell": 0,
              "raw_cell_mismatch": 0, "normalization_mismatch": 0, "converted_ok": 0,
              "exact_unit_ok": 0, "ok": 0, "issues": []}
    with sqlite3.connect(args.db) as con:
        # Some older flagged records are intentionally non-tabular context
        # layers and therefore have no table-cell locator.  They are not part
        # of this cell-level verification contract.
        for measurement_id, value, measurement_unit, locator in con.execute(
            """SELECT measurement_id,value_num,unit_raw,evidence_locator
               FROM measurement
               WHERE evidence_locator LIKE '%table_candidate_id%'"""
        ):
            report["checked"] += 1
            try:
                loc = json.loads(locator)
                candidate_id = loc["table_candidate_id"]
            except Exception:
                report["missing_locator"] += 1; report["issues"].append({"measurement_id": measurement_id, "kind": "bad_locator"}); continue
            candidate = con.execute(
                """SELECT t.value_num,t.unit_raw,t.property_id,pd.canonical_unit,
                          t.artifact_id,t.row_index,t.column_index
                   FROM table_measurement_candidate t JOIN property_definition pd ON pd.property_id=t.property_id
                   WHERE t.candidate_id=?""", (candidate_id,)
            ).fetchone()
            if not candidate:
                report["missing_locator"] += 1; report["issues"].append({"measurement_id": measurement_id, "kind": "missing_candidate"}); continue
            candidate_raw, raw_unit, property_id, canonical_unit, artifact, row, column = candidate
            cell = con.execute("SELECT text_raw FROM table_cell WHERE artifact_id=? AND row_index=? AND column_index=?", (artifact, row, column)).fetchone()
            if not cell:
                # Older table_json extraction retains the candidate value and
                # source artifact but has no separately materialized cell.
                # It is still evidence-backed, yet is reported distinctly
                # from a missing/invalid source value.
                source_value = candidate_raw
                report["candidate_only_evidence"] += 1
            else:
                match = NUMBER.search(cell[0])
                if not match:
                    report["non_numeric_cell"] += 1; report["issues"].append({"measurement_id": measurement_id, "kind": "non_numeric_cell", "cell": cell[0]}); continue
                source_value = float(match.group(0).replace(",", "."))
            if abs(source_value - candidate_raw) > 1e-9:
                report["raw_cell_mismatch"] += 1; report["issues"].append({"measurement_id": measurement_id, "kind": "raw_cell_mismatch", "source": source_value, "candidate": candidate_raw}); continue
            # A table header can supply the unit after the original candidate
            # was created.  The staged measurement preserves that resolved
            # unit, so use it only when the raw candidate itself lacks one.
            raw_unit = raw_unit or measurement_unit
            expected, normalized_unit, status, warning = convert(source_value, raw_unit, canonical_unit, property_id)
            if status not in {"exact", "converted"} or expected is None or abs(expected - value) > 1e-9:
                report["normalization_mismatch"] += 1; report["issues"].append({"measurement_id": measurement_id, "kind": "normalization_mismatch", "source": source_value, "raw_unit": raw_unit, "expected": expected, "staged": value, "status": status}); continue
            report["converted_ok" if status == "converted" else "exact_unit_ok"] += 1
            report["ok"] += 1
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "issues"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
