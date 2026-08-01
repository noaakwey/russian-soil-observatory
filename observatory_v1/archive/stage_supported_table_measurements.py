#!/usr/bin/env python3
"""Stage analytically usable OCR-table observations without overstating certainty.

An OCR value is linked only when its *same document* contains exactly one
explicitly reported Russian coordinate.  The resulting rows are deliberately
``flagged`` rather than ``accepted``: the site link is document-single-site,
not a row-level coordinate label.  This makes the tier useful for analysis
while keeping it separable from fully verified observations.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from normalize_measurement_candidates import convert


def token(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def plausible(value: float, unit: str | None) -> bool:
    if value < 0 or value > 1_000_000:
        return False
    if unit == "pH":
        return 0 <= value <= 14
    if unit == "%":
        return value <= 100
    if unit == "g/cm3":
        return 0.05 <= value <= 3.5
    return True


NON_MEASUREMENT_MARKERS = re.compile(
    r"correlation|coefficient|significance|p[- ]?value|regression|"
    r"initial concentration|absorption band|intensity ratio|"
    r"classification|frequency|quartile|median|standard deviation|"
    r"eigenvalue|factor loading|variance|probability",
    re.I,
)


def observation_reason(rec: dict, value: float, unit: str | None) -> str | None:
    """Reject numeric table cells that are not soil-property observations."""
    header = rec["property_header_raw"] or ""
    row = rec["row_label_raw"] or ""
    if NON_MEASUREMENT_MARKERS.search(header) or NON_MEASUREMENT_MARKERS.search(row):
        return "non_measurement_table"
    # Reference/citation rows and rows containing only correlation-like values
    # are not observations at the document's study site.
    if re.search(r"\[\d{1,3}\]", row):
        return "reference_row"
    property_id = rec["property_id"]
    ranges = {
        "ph_h2o": (2.5, 10.5),
        "ph_kcl": (2.5, 10.5),
        "bulk_density": (0.7, 2.2),
        "sand": (0.0, 100.0),
        "silt": (0.0, 100.0),
        "clay": (0.0, 100.0),
        "soil_organic_carbon": (0.0, 250.0),
        "total_nitrogen": (0.0, 50.0),
        "available_phosphorus": (0.0, 1000.0),
    }
    if property_id in ranges:
        low, high = ranges[property_id]
        if not low <= value <= high:
            return "property_out_of_plausible_range"
    return None


SQL = """
WITH single_reported_site AS (
  SELECT d.document_id, MIN(se.site_id) AS site_id
  FROM document d
  JOIN source_artifact evidence ON evidence.document_id=d.document_id
  JOIN site_evidence se ON se.artifact_id=evidence.artifact_id
  JOIN site s ON s.site_id=se.site_id
  WHERE s.country_code='RU' AND s.spatial_confidence IN ('exact','reported')
  GROUP BY d.document_id
  HAVING COUNT(DISTINCT se.site_id)=1
)
SELECT t.candidate_id, t.artifact_id, t.row_index, t.column_index,
       t.property_id, t.property_header_raw, t.value_num, t.unit_raw,
       t.row_label_raw, t.horizon_label, t.depth_top_cm, t.depth_bottom_cm,
       d.document_id, one.site_id, pd.canonical_unit
FROM table_measurement_candidate t
JOIN source_artifact a ON a.artifact_id=t.artifact_id
JOIN document d ON d.document_id=a.document_id
JOIN single_reported_site one ON one.document_id=d.document_id
JOIN property_definition pd ON pd.property_id=t.property_id
WHERE t.status='unreviewed' AND t.value_num IS NOT NULL AND t.unit_raw IS NOT NULL
ORDER BY t.artifact_id, t.row_index, t.column_index
"""


def query_for(spatial_tier: str) -> str:
    if spatial_tier == "reported":
        return SQL
    # District/settlement geocodes are valuable contextual observations, but
    # never substitute for a reported sampling point.  Exclude a document as
    # soon as it contains any explicit point, even if it also names a region.
    return SQL.replace(
        "WHERE s.country_code='RU' AND s.spatial_confidence IN ('exact','reported')",
        """WHERE s.country_code='RU' AND s.spatial_confidence='geocoded'
    AND NOT EXISTS (
      SELECT 1 FROM source_artifact explicit_a
      JOIN site_evidence explicit_se ON explicit_se.artifact_id=explicit_a.artifact_id
      JOIN site explicit_s ON explicit_s.site_id=explicit_se.site_id
      WHERE explicit_a.document_id=d.document_id
        AND explicit_s.spatial_confidence IN ('exact','reported')
    )""",
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--spatial-tier", choices=("reported", "geocoded"), default="reported")
    parser.add_argument("--id-namespace", default="table",
                        help="Namespace for derived IDs. Use a new namespace when evaluating a rebuilt parser layer.")
    parser.add_argument("--review", type=Path,
                        help="Optional CSV whitelist: candidate_id,site_id,reason.")
    args = parser.parse_args()
    stats: Counter[str] = Counter()
    reviewed: dict[str, dict[str, str]] = {}
    if args.review:
        reviewed = {row["candidate_id"]: row for row in csv.DictReader(args.review.open(encoding="utf-8", newline=""))}
        if not reviewed or any(not row.get("site_id") or not row.get("reason") for row in reviewed.values()):
            raise SystemExit("--review requires non-empty candidate_id,site_id,reason")
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        query = query_for(args.spatial_tier)
        columns = [item[0] for item in con.execute(query).description]
        linkage = (
            "document_single_reported_coordinate"
            if args.spatial_tier == "reported"
            else "document_single_geocoded_district"
        )
        if reviewed:
            linkage = "reviewed_document_geocoded_context"
        for row in con.execute(query):
            rec = dict(zip(columns, row))
            review = reviewed.get(rec["candidate_id"])
            if reviewed and not review:
                continue
            if review and review["site_id"] != rec["site_id"]:
                stats["review_site_mismatch"] += 1
                continue
            normalized, normalized_unit, status, warning = convert(
                rec["value_num"], rec["unit_raw"], rec["canonical_unit"], rec["property_id"]
            )
            if status not in {"exact", "converted"}:
                stats[f"normalization_{status}"] += 1
                continue
            if not plausible(normalized, normalized_unit):
                stats["implausible_value"] += 1
                continue
            reason = observation_reason(rec, normalized, normalized_unit)
            if reason:
                stats[reason] += 1
                continue
            artifact_token = token(rec["artifact_id"])
            row_token = f"{artifact_token}:r{rec['row_index']}"
            profile_id = f"profile:{args.id_namespace}:{rec['site_id']}:{artifact_token}"
            horizon_id = (
                f"horizon:{args.id_namespace}:{rec['site_id']}:{row_token}"
                if rec["horizon_label"] or rec["depth_top_cm"] is not None else None
            )
            sample_id = f"sample:{args.id_namespace}:{rec['site_id']}:{row_token}"
            analysis_id = f"analysis:{args.id_namespace}:{rec['site_id']}:{row_token}"
            # A rebuilt header parser can legitimately assign a new property
            # to the same OCR row/column. Include it in the ID so evaluation
            # cannot overwrite a prior property's value through a collision.
            measurement_id = f"measurement:{args.id_namespace}:{token(rec['candidate_id'] + ':' + rec['property_id'])}"
            evidence = json.dumps({
                "table_candidate_id": rec["candidate_id"],
                "row_index": rec["row_index"],
                "column_index": rec["column_index"],
                "header": rec["property_header_raw"],
                "row_label": rec["row_label_raw"],
                "spatial_linkage": linkage,
                **({"review_reason": review["reason"]} if review else {}),
            }, ensure_ascii=False)
            con.execute(
                """INSERT INTO profile(profile_id,site_id,profile_label,notes) VALUES(?,?,?,?)
                   ON CONFLICT(profile_id) DO NOTHING""",
                (profile_id, rec["site_id"], "OCR table profile",
                 f"Single {args.spatial_tier} Russian location in this document; table row remains flagged."),
            )
            if horizon_id:
                con.execute(
                    """INSERT INTO horizon(horizon_id,profile_id,horizon_label,depth_top_cm,depth_bottom_cm)
                       VALUES(?,?,?,?,?) ON CONFLICT(horizon_id) DO UPDATE SET
                       horizon_label=excluded.horizon_label, depth_top_cm=excluded.depth_top_cm,
                       depth_bottom_cm=excluded.depth_bottom_cm""",
                    (horizon_id, profile_id, rec["horizon_label"], rec["depth_top_cm"], rec["depth_bottom_cm"]),
                )
            con.execute(
                """INSERT INTO sample(sample_id,site_id,profile_id,horizon_id,sample_label,depth_top_cm,depth_bottom_cm,notes)
                   VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(sample_id) DO UPDATE SET
                   horizon_id=excluded.horizon_id, sample_label=excluded.sample_label,
                   depth_top_cm=excluded.depth_top_cm, depth_bottom_cm=excluded.depth_bottom_cm""",
                (sample_id, rec["site_id"], profile_id, horizon_id, rec["row_label_raw"],
                 rec["depth_top_cm"], rec["depth_bottom_cm"],
                 f"OCR table row; site link is {linkage}."),
            )
            con.execute(
                """INSERT INTO sample_evidence(sample_id,artifact_id,extraction_id,evidence_text)
                   VALUES(?,?,NULL,?) ON CONFLICT(sample_id,artifact_id) DO UPDATE SET
                   evidence_text=excluded.evidence_text""",
                (sample_id, rec["artifact_id"], evidence),
            )
            con.execute(
                """INSERT INTO laboratory_analysis(analysis_id,sample_id,analysis_label,method_raw,evidence_artifact_id,evidence_extraction_id)
                   VALUES(?,?,?,NULL,?,NULL) ON CONFLICT(analysis_id) DO UPDATE SET
                   evidence_artifact_id=excluded.evidence_artifact_id""",
                (analysis_id, sample_id, "OCR table row", rec["artifact_id"]),
            )
            con.execute(
                """INSERT INTO measurement(measurement_id,site_id,profile_id,horizon_id,property_id,value_num,value_text,
                   unit_raw,unit_normalized,method_raw,qa_status,evidence_artifact_id,evidence_extraction_id,evidence_locator)
                   VALUES(?,?,?,?,?,?,NULL,?,?,NULL,'flagged',?,NULL,?)
                   ON CONFLICT(measurement_id) DO UPDATE SET value_num=excluded.value_num,
                   unit_raw=excluded.unit_raw, unit_normalized=excluded.unit_normalized,
                   qa_status='flagged', evidence_locator=excluded.evidence_locator""",
                (measurement_id, rec["site_id"], profile_id, horizon_id, rec["property_id"], normalized,
                 rec["unit_raw"], normalized_unit, rec["artifact_id"], evidence),
            )
            con.execute(
                """INSERT INTO laboratory_analysis_measurement(analysis_id,measurement_id) VALUES(?,?)
                   ON CONFLICT(analysis_id,measurement_id) DO NOTHING""",
                (analysis_id, measurement_id),
            )
            # The measurement stays visibly ``flagged`` because the spatial
            # link is document-level, but this OCR candidate itself has now
            # been consumed with a reproducible table-cell locator.  Leaving
            # it ``unreviewed`` caused double counting in the review queue and
            # repeated idempotent staging on every pipeline run.
            con.execute("UPDATE table_measurement_candidate SET status='accepted' WHERE candidate_id=?",
                        (rec['candidate_id'],))
            stats[f"staged_{args.spatial_tier}_flagged_measurements"] += 1
        con.commit()
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
