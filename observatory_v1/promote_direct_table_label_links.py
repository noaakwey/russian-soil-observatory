#!/usr/bin/env python3
"""Promote audited OCR cells only when their field label resolves to one coordinate.

Input is the read-only output of ``audit_table_label_coordinate_linkage.py``.
Unlike the document-single-site staging layer, these measurements are accepted:
the same named pit/profile occurs in both the table row and coordinate evidence.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sqlite3
from pathlib import Path

from normalize_measurement_candidates import convert
from stage_supported_table_measurements import observation_reason, plausible


def token(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--audit", type=Path, required=True)
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    rows = list(csv.DictReader(a.audit.open(encoding="utf-8")))
    stats = {"audited_rows": len(rows), "promoted": 0, "missing": 0, "normalization_rejected": 0, "plausibility_rejected": 0}
    with sqlite3.connect(a.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        for audit in rows:
            record = con.execute(
                """SELECT t.candidate_id,t.artifact_id,t.row_index,t.column_index,t.property_id,t.property_header_raw,
                          t.value_num,t.value_text,t.unit_raw,t.row_label_raw,t.horizon_label,t.depth_top_cm,t.depth_bottom_cm,
                          pd.canonical_unit,lc.candidate_id,lc.context_text
                     FROM table_measurement_candidate t
                     JOIN property_definition pd ON pd.property_id=t.property_id
                     JOIN location_candidate lc ON lc.candidate_id=?
                    WHERE t.candidate_id=?""",
                (audit["coordinate_candidate_id"], audit["candidate_id"]),
            ).fetchone()
            if not record:
                stats["missing"] += 1; continue
            (candidate_id, artifact_id, row_index, column_index, property_id, header, value_num, value_text,
             unit_raw, row_label, horizon_label, top, bottom, canonical_unit, coordinate_id, coordinate_context) = record
            value, normalized_unit, status, _warning = convert(value_num, unit_raw, canonical_unit, property_id)
            if status not in {"exact", "converted"}:
                stats["normalization_rejected"] += 1; continue
            rec = {"property_id": property_id, "property_header_raw": header, "row_label_raw": row_label}
            if not plausible(value, normalized_unit) or observation_reason(rec, value, normalized_unit):
                stats["plausibility_rejected"] += 1; continue
            site_id = f"site:{coordinate_id}"
            label = row_label or audit["matching_labels"]
            row_token = token(candidate_id)
            profile_id = f"profile:direct_table:{site_id}:{row_token}"
            horizon_id = f"horizon:direct_table:{site_id}:{row_token}" if horizon_label or top else None
            sample_id = f"sample:direct_table:{row_token}"
            analysis_id = f"analysis:direct_table:{row_token}"
            measurement_id = f"measurement:direct_table:{row_token}"
            evidence = json.dumps({"table_candidate_id": candidate_id, "row_index": row_index, "column_index": column_index,
                                   "row_label": row_label, "matching_field_label": audit["matching_labels"],
                                   "coordinate_candidate_id": coordinate_id, "coordinate_context": coordinate_context,
                                   "spatial_linkage": "direct_table_label_to_coordinate_label"}, ensure_ascii=False)
            if not a.dry_run:
                con.execute("INSERT INTO profile(profile_id,site_id,profile_label,notes) VALUES(?,?,?,?) ON CONFLICT(profile_id) DO NOTHING",
                            (profile_id, site_id, label, "Direct OCR-table label ↔ coordinate-label link; independently audited."))
                if horizon_id:
                    con.execute("INSERT INTO horizon(horizon_id,profile_id,horizon_label,depth_top_cm,depth_bottom_cm) VALUES(?,?,?,?,?) ON CONFLICT(horizon_id) DO NOTHING",
                                (horizon_id, profile_id, horizon_label, top, bottom))
                con.execute("INSERT INTO sample(sample_id,site_id,profile_id,horizon_id,sample_label,depth_top_cm,depth_bottom_cm,notes) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(sample_id) DO NOTHING",
                            (sample_id, site_id, profile_id, horizon_id, label, top, bottom, "Direct OCR row-to-coordinate label linkage."))
                con.execute("INSERT INTO sample_evidence(sample_id,artifact_id,extraction_id,evidence_text) VALUES(?,?,NULL,?) ON CONFLICT(sample_id,artifact_id) DO UPDATE SET evidence_text=excluded.evidence_text",
                            (sample_id, artifact_id, evidence))
                con.execute("INSERT INTO laboratory_analysis(analysis_id,sample_id,analysis_label,method_raw,evidence_artifact_id,evidence_extraction_id) VALUES(?,?,?,NULL,?,NULL) ON CONFLICT(analysis_id) DO NOTHING",
                            (analysis_id, sample_id, "Direct OCR table observation", artifact_id))
                con.execute("""INSERT INTO measurement(measurement_id,site_id,profile_id,horizon_id,property_id,value_num,value_text,unit_raw,unit_normalized,method_raw,qa_status,evidence_artifact_id,evidence_extraction_id,evidence_locator)
                               VALUES(?,?,?,?,?,?,?,?,?,NULL,'accepted',?,NULL,?) ON CONFLICT(measurement_id) DO NOTHING""",
                            (measurement_id, site_id, profile_id, horizon_id, property_id, value, value_text, unit_raw, normalized_unit, artifact_id, evidence))
                con.execute("INSERT INTO laboratory_analysis_measurement(analysis_id,measurement_id) VALUES(?,?) ON CONFLICT(analysis_id,measurement_id) DO NOTHING", (analysis_id, measurement_id))
                con.execute("UPDATE table_measurement_candidate SET status='accepted' WHERE candidate_id=?", (candidate_id,))
            stats["promoted"] += 1
        if not a.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
