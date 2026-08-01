#!/usr/bin/env python3
"""Materialize every OCR-table value without inventing a sampling location.

The operational ``measurement`` relation intentionally requires a site.  This
script fills the complementary complete layer: every header-grounded table
cell becomes a ``table_observation`` with its raw value, normalization result,
cell locator, source artifact, and the *strength* of any document-level
spatial context.  A single coordinate in a paper is retained as context, not
silently promoted to a row-level GPS point.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from collections import Counter
from pathlib import Path


DDL_PATH = Path(__file__).with_name("schema.sql")


def token(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:24]


def candidate_measurements(con: sqlite3.Connection) -> dict[str, str]:
    """Map existing spatial/strict measurements back to their table cell."""
    result: dict[str, str] = {}
    for measurement_id, locator in con.execute(
        "SELECT measurement_id,evidence_locator FROM measurement WHERE evidence_locator IS NOT NULL"
    ):
        try:
            candidate_id = json.loads(locator).get("table_candidate_id")
        except (TypeError, json.JSONDecodeError):
            candidate_id = None
        if candidate_id:
            result[str(candidate_id)] = str(measurement_id)
    return result


QUERY = """
WITH reported_sites AS (
  SELECT a.document_id,
         COUNT(DISTINCT s.site_id) AS site_count,
         MIN(s.site_id) AS only_site_id
  FROM source_artifact a
  JOIN site_evidence se ON se.artifact_id=a.artifact_id
  JOIN site s ON s.site_id=se.site_id
  WHERE s.country_code='RU' AND s.spatial_confidence IN ('exact','reported')
  GROUP BY a.document_id
)
SELECT t.candidate_id,t.artifact_id,a.document_id,t.row_index,t.column_index,
       t.property_id,t.property_header_raw,t.value_num,t.value_text,t.unit_raw,
       n.value_normalized,n.unit_normalized,
       COALESCE(n.normalization_status,'missing_value'),n.warning,
       t.row_label_raw,t.horizon_label,t.depth_top_cm,t.depth_bottom_cm,
       COALESCE(rs.site_count,0),rs.only_site_id
FROM table_measurement_candidate t
JOIN source_artifact a ON a.artifact_id=t.artifact_id
LEFT JOIN table_measurement_candidate_normalization n ON n.candidate_id=t.candidate_id
LEFT JOIN reported_sites rs ON rs.document_id=a.document_id
WHERE NOT EXISTS (
  SELECT 1 FROM table_observation existing WHERE existing.candidate_id=t.candidate_id
)
ORDER BY t.candidate_id
"""


def qa_status(normalization: str, linked_measurement: bool) -> str:
    if linked_measurement:
        return "flagged"  # Detailed QA lives on the linked operational record.
    return {
        "exact": "normalized",
        "converted": "normalized",
        "missing_unit": "unit_missing",
        "incompatible": "unit_incompatible",
    }.get(normalization, "missing_value")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    args = parser.parse_args()

    stats: Counter[str] = Counter()
    schema = DDL_PATH.read_text(encoding="utf-8")
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        # ``executescript`` is idempotent; it supplies the table, indexes and
        # view when upgrading an existing database.
        con.executescript(schema)
        linked = candidate_measurements(con)
        cur = con.execute(QUERY)
        for index, row in enumerate(cur, start=1):
            (
                candidate_id, artifact_id, document_id, row_index, column_index,
                property_id, header, value_num, value_text, unit_raw,
                value_normalized, unit_normalized, normalization, warning,
                row_label, horizon_label, depth_top, depth_bottom,
                site_count, only_site_id,
            ) = row
            if site_count == 0:
                spatial_linkage, context_site = "no_reported_coordinate", None
            elif site_count == 1:
                spatial_linkage, context_site = "document_single_reported_coordinate", only_site_id
            else:
                spatial_linkage, context_site = "document_multiple_reported_coordinates", None
            operational_id = linked.get(candidate_id)
            if operational_id:
                spatial_linkage = "row_profile_verified"
            locator = json.dumps({
                "table_candidate_id": candidate_id,
                "row_index": row_index,
                "column_index": column_index,
                "property_header": header,
                "row_label": row_label,
                "spatial_linkage": spatial_linkage,
                "source_kind": "header_grounded_ocr_table_cell",
            }, ensure_ascii=False, separators=(",", ":"))
            observation_id = f"table-observation:{token(candidate_id)}"
            con.execute(
                """INSERT INTO table_observation(
                  observation_id,candidate_id,document_id,artifact_id,row_index,column_index,
                  property_id,property_header_raw,value_num_raw,value_text_raw,unit_raw,
                  value_normalized,unit_normalized,normalization_status,normalization_warning,
                  row_label_raw,horizon_label_raw,depth_top_cm,depth_bottom_cm,
                  context_site_id,spatial_linkage,operational_measurement_id,qa_status,evidence_locator
                ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                ON CONFLICT(candidate_id) DO UPDATE SET
                  document_id=excluded.document_id, artifact_id=excluded.artifact_id,
                  row_index=excluded.row_index, column_index=excluded.column_index,
                  property_id=excluded.property_id, property_header_raw=excluded.property_header_raw,
                  value_num_raw=excluded.value_num_raw, value_text_raw=excluded.value_text_raw,
                  unit_raw=excluded.unit_raw, value_normalized=excluded.value_normalized,
                  unit_normalized=excluded.unit_normalized, normalization_status=excluded.normalization_status,
                  normalization_warning=excluded.normalization_warning,
                  row_label_raw=excluded.row_label_raw, horizon_label_raw=excluded.horizon_label_raw,
                  depth_top_cm=excluded.depth_top_cm, depth_bottom_cm=excluded.depth_bottom_cm,
                  context_site_id=excluded.context_site_id, spatial_linkage=excluded.spatial_linkage,
                  operational_measurement_id=excluded.operational_measurement_id,
                  qa_status=excluded.qa_status, evidence_locator=excluded.evidence_locator,
                  updated_at=CURRENT_TIMESTAMP""",
                (
                    observation_id, candidate_id, document_id, artifact_id, row_index, column_index,
                    property_id, header, value_num, value_text, unit_raw,
                    value_normalized, unit_normalized, normalization, warning,
                    row_label, horizon_label, depth_top, depth_bottom,
                    context_site, spatial_linkage, operational_id,
                    qa_status(normalization, bool(operational_id)), locator,
                ),
            )
            stats["observations"] += 1
            stats[f"normalization_{normalization}"] += 1
            stats[f"spatial_{spatial_linkage}"] += 1
            if operational_id:
                stats["linked_operational_measurement"] += 1
            if index % args.batch_size == 0:
                con.commit()
        con.commit()
        total = con.execute("SELECT COUNT(*) FROM table_observation").fetchone()[0]
        source_total = con.execute("SELECT COUNT(*) FROM table_measurement_candidate").fetchone()[0]
    if total != source_total:
        raise SystemExit(f"coverage failure: table_observation={total}, candidates={source_total}")
    print(json.dumps({"source_candidates": source_total, "table_observations": total,
                      "stats": dict(stats)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
