#!/usr/bin/env python3
"""Promote a small, human-reviewed list of administrative study contexts.

The output is intentionally low-precision ``geocoded`` context, never an
author-reported sampling coordinate.  Every promotion remains tied to both
the literal article fragment and cached Nominatim boundary response.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

from audit_geocode_quality import tier


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    decisions = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    if not decisions or any({"candidate_id", "reason"} - set(row) for row in decisions):
        raise SystemExit("Input requires candidate_id,reason")
    stats = {"selected": len(decisions), "promoted": 0, "not_eligible": 0, "missing": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        for decision in decisions:
            row = con.execute("""
                SELECT pc.candidate_id,pc.place_text,pc.context_text,pg.display_name,pg.geometry_kind,
                       pg.spatial_precision_m,pg.latitude,pg.longitude,pg.source_url,e.artifact_id
                FROM place_candidate pc JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
                JOIN extraction e ON e.extraction_id=pc.extraction_id
                WHERE pc.candidate_id=? AND pc.status='unreviewed'
                  AND pg.status='accepted' AND pg.country_code='RU'
            """, (decision["candidate_id"],)).fetchone()
            if not row:
                stats["missing"] += 1
                continue
            audit_row = dict(row)
            audit_row["administrative_level"] = con.execute(
                "SELECT administrative_level FROM place_candidate WHERE candidate_id=?", (row["candidate_id"],)
            ).fetchone()[0]
            if tier(audit_row) != "candidate_geocoded_study_context":
                stats["not_eligible"] += 1
                continue
            site_id = f"site:place:{row['candidate_id']}"
            if not args.dry_run:
                con.execute("""
                    INSERT INTO site(site_id,country_code,name,region,latitude,longitude,spatial_precision_m,spatial_confidence,geometry_source)
                    VALUES(?, 'RU', ?, ?, ?, ?, ?, 'geocoded',
                           'Nominatim administrative boundary centroid; reviewed study-area context; not a reported sampling coordinate.')
                    ON CONFLICT(site_id) DO NOTHING
                """, (site_id,row["place_text"],row["display_name"],row["latitude"],row["longitude"],row["spatial_precision_m"]))
                con.execute("""
                    INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                    VALUES(?,?,?,'location_text')
                """, (site_id,row["artifact_id"],row["context_text"]))
                con.execute("""
                    INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                    VALUES(?,?,?,'geocoding')
                """, (site_id,row["artifact_id"],json.dumps({
                    "provider":"Nominatim", "source_url":row["source_url"],
                    "geometry_kind":row["geometry_kind"], "precision_m":row["spatial_precision_m"],
                    "review_reason":decision["reason"],
                    "meaning":"administrative centroid/boundary; not sampling coordinate",
                },ensure_ascii=False)))
                con.execute("UPDATE place_candidate SET status='accepted' WHERE candidate_id=?", (row["candidate_id"],))
            stats["promoted"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats,ensure_ascii=False))


if __name__ == "__main__":
    main()
