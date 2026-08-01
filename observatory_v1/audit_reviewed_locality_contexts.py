#!/usr/bin/env python3
"""Audit provenance and precision boundaries of reviewed locality contexts."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT s.site_id,s.spatial_confidence,s.geometry_source,pc.place_text,pg.status,
                   pg.country_code,pg.geometry_kind,se1.evidence_text AS location_text,
                   se2.evidence_text AS geocoding_text,a.source_path
            FROM site s JOIN place_candidate pc ON s.site_id='site:place:'||pc.candidate_id
            JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
            LEFT JOIN site_evidence se1 ON se1.site_id=s.site_id AND se1.evidence_kind='location_text'
            LEFT JOIN site_evidence se2 ON se2.site_id=s.site_id AND se2.evidence_kind='geocoding'
            LEFT JOIN source_artifact a ON a.artifact_id=se1.artifact_id
            WHERE s.geometry_source LIKE 'Nominatim locality centroid; reviewed study-area context%'
            ORDER BY s.site_id
        """).fetchall()
    issues: list[dict[str, str]] = []
    for row in rows:
        flags: list[str] = []
        if row["spatial_confidence"] != "geocoded": flags.append("wrong_spatial_confidence")
        if row["status"] != "accepted" or row["country_code"] != "RU": flags.append("unaccepted_or_non_ru_geocode")
        if row["geometry_kind"] not in {"centroid", "boundary_centroid", "point"}: flags.append("invalid_geometry_kind")
        if not row["location_text"]: flags.append("missing_article_evidence")
        if not row["geocoding_text"] or "review_reason" not in row["geocoding_text"]: flags.append("missing_review_reason")
        if not row["source_path"] or not Path(row["source_path"]).is_file(): flags.append("missing_source_text")
        if flags: issues.append({"site_id": row["site_id"], "issues": ";".join(flags)})
    report = {"reviewed_locality_context_sites": len(rows), "invariant_violations": issues,
              "ready": not issues,
              "meaning": "all listed records are low-precision locality contexts, not author-reported sampling coordinates"}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
