#!/usr/bin/env python3
"""Promote a hand-reviewed list of named-locality study contexts.

This is intentionally not an automatic settlement geocoder.  A locality can
be a town centre while the field lies kilometres away, and a common village
name can resolve to the wrong region.  The review CSV is therefore the only
authority for promotion.  Resulting records are explicitly low-precision
``geocoded`` contexts, never reported sampling coordinates.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    decisions = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    required = {"candidate_id", "reason"}
    if not decisions or any(required - set(row) or not row["reason"].strip() for row in decisions):
        raise SystemExit("Input requires non-empty candidate_id,reason columns")

    stats = {"selected": len(decisions), "promoted": 0, "missing_or_not_reviewable": 0,
             "has_reported_coordinate": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        for decision in decisions:
            row = con.execute(
                """SELECT pc.candidate_id,pc.place_text,pc.administrative_level,pc.context_text,
                          pg.display_name,pg.country_code,pg.latitude,pg.longitude,pg.geometry_kind,
                          pg.spatial_precision_m,pg.source_url,e.artifact_id
                   FROM place_candidate pc
                   JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
                   JOIN extraction e ON e.extraction_id=pc.extraction_id
                   WHERE pc.candidate_id=? AND pc.status='unreviewed'
                     AND pc.administrative_level='settlement'
                     AND pg.status='accepted' AND pg.country_code='RU'
                     AND pg.geometry_kind IN ('centroid','boundary_centroid','point')""",
                (decision["candidate_id"],),
            ).fetchone()
            if not row:
                stats["missing_or_not_reviewable"] += 1
                continue
            reported = con.execute(
                """SELECT EXISTS(
                       SELECT 1 FROM site_evidence se
                       JOIN source_artifact a ON a.artifact_id=se.artifact_id
                       JOIN site s ON s.site_id=se.site_id
                       WHERE a.document_id=(SELECT a2.document_id FROM source_artifact a2
                                            JOIN extraction e2 ON e2.artifact_id=a2.artifact_id
                                            WHERE e2.extraction_id=(SELECT extraction_id FROM place_candidate
                                                                    WHERE candidate_id=?))
                         AND s.spatial_confidence IN ('reported','exact')
                   )""",
                (row["candidate_id"],),
            ).fetchone()[0]
            if reported:
                stats["has_reported_coordinate"] += 1
                continue
            site_id = f"site:place:{row['candidate_id']}"
            if not args.dry_run:
                con.execute(
                    """INSERT INTO site(site_id,country_code,name,region,latitude,longitude,
                                            spatial_precision_m,spatial_confidence,geometry_source)
                       VALUES(?, 'RU', ?, ?, ?, ?, ?, 'geocoded',
                              'Nominatim locality centroid; reviewed study-area context; not a reported sampling coordinate.')
                       ON CONFLICT(site_id) DO NOTHING""",
                    (site_id, row["place_text"], row["display_name"], row["latitude"], row["longitude"],
                     row["spatial_precision_m"]),
                )
                con.execute(
                    """INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                       VALUES(?,?,?,'location_text')""",
                    (site_id, row["artifact_id"], row["context_text"]),
                )
                con.execute(
                    """INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                       VALUES(?,?,?,'geocoding')""",
                    (site_id, row["artifact_id"], json.dumps({
                        "provider": "Nominatim", "source_url": row["source_url"],
                        "geometry_kind": row["geometry_kind"],
                        "precision_m": row["spatial_precision_m"],
                        "review_reason": decision["reason"],
                        "meaning": "locality centroid; study context; not sampling coordinate",
                    }, ensure_ascii=False)),
                )
                con.execute("UPDATE place_candidate SET status='accepted' WHERE candidate_id=?", (row["candidate_id"],))
            stats["promoted"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
