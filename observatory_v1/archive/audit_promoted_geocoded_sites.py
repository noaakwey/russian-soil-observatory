#!/usr/bin/env python3
"""Independently audit already promoted administrative context sites.

Older promotion passes predate the strict name-to-geocoder check.  This audit
does not delete any evidence; it classifies each published centroid so exports
can hide a bad geocoder match while preserving the source record for review.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path

from audit_geocode_quality import name_matches
from promote_geocoded_places import is_study_context


SQL = """
SELECT s.site_id,s.name,s.region,s.latitude,s.longitude,s.spatial_precision_m,
       pc.candidate_id,pc.place_text,pc.context_text,pg.display_name,pg.geometry_kind,
       d.document_id,d.corpus
FROM site s
JOIN place_candidate pc ON s.site_id='site:place:' || pc.candidate_id
JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
JOIN extraction e ON e.extraction_id=pc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE s.spatial_confidence='geocoded'
ORDER BY d.document_id,s.site_id
"""


def status(row: dict[str, object]) -> str:
    if not name_matches(str(row["place_text"] or ""), str(row["display_name"] or "")):
        return "geocoder_name_mismatch"
    if str(row["geometry_kind"]) != "boundary_centroid":
        return "not_administrative_boundary"
    if not is_study_context(str(row["context_text"] or "")):
        return "context_insufficient"
    return "verified_geocoded_study_context"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(row) for row in con.execute(SQL)]
    for row in rows:
        row["audit_status"] = status(row)
    fields = ["site_id","candidate_id","document_id","corpus","place_text","display_name",
              "latitude","longitude","spatial_precision_m","geometry_kind","audit_status","context_text"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows([{field: row.get(field) for field in fields} for row in rows])
    counts = Counter(str(row["audit_status"]) for row in rows)
    print(json.dumps({"sites": len(rows), "status": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
