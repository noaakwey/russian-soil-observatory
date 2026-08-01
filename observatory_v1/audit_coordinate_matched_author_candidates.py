#!/usr/bin/env python3
"""Produce review rows where a text candidate repeats a profile's coordinate.

No values are promoted.  This is a stronger queue than document-level
matching: the candidate excerpt must itself print the same coordinate as one
and only one existing profile with the same explicit label.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

from audit_profile_context_coordinate import coords


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    stats = {"candidates_scanned": 0, "candidate_profile_matches": 0,
             "coordinate_matched_unique_profiles": 0, "already_present": 0}
    selected: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT c.candidate_id,c.document_id,c.field_name,c.profile_label_raw,c.raw_value,
                   c.evidence_text,c.linkable,a.source_path AS candidate_path
            FROM document_author_statement_candidate c
            JOIN source_artifact a ON a.artifact_id=c.artifact_id
            WHERE c.profile_label_raw IS NOT NULL
        """).fetchall()
        for row in rows:
            stats["candidates_scanned"] += 1
            profiles = con.execute("""
                SELECT DISTINCT p.profile_id,p.profile_label,p.author_soil_type_raw,p.author_profile_formula_raw,
                       s.latitude,s.longitude,a.source_path
                FROM profile p
                JOIN site s ON s.site_id=p.site_id
                JOIN profile_evidence pe ON pe.profile_id=p.profile_id
                JOIN source_artifact a ON a.artifact_id=pe.artifact_id
                WHERE a.document_id=? AND lower(p.profile_label)=lower(?)
                  AND s.spatial_confidence IN ('exact','reported')
            """, (row["document_id"], row["profile_label_raw"])).fetchall()
            if len(profiles) != 1:
                continue
            stats["candidate_profile_matches"] += 1
            profile = profiles[0]
            evidence_coords = coords(row["evidence_text"])
            if not any(abs(lat - profile["latitude"]) < 1e-6 and abs(lon - profile["longitude"]) < 1e-6
                       for lat, lon, _start, _end in evidence_coords):
                continue
            stats["coordinate_matched_unique_profiles"] += 1
            existing = profile[row["field_name"]]
            stats["already_present"] += int(existing is not None)
            selected.append({
                "candidate_id": row["candidate_id"], "profile_id": profile["profile_id"],
                "profile_label": profile["profile_label"], "field_name": row["field_name"],
                "raw_value": row["raw_value"], "already_present": int(existing is not None),
                "linkable": row["linkable"], "document_id": row["document_id"],
                "candidate_path": row["candidate_path"], "latitude": profile["latitude"],
                "longitude": profile["longitude"], "evidence_text": row["evidence_text"],
            })
    fields = ["candidate_id", "profile_id", "profile_label", "field_name", "raw_value",
              "already_present", "linkable", "document_id", "candidate_path", "latitude", "longitude", "evidence_text"]
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(selected)
    print(json.dumps({**stats, "selected": len(selected)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
