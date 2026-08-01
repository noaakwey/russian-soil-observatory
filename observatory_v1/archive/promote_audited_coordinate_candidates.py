#!/usr/bin/env python3
"""Promote only explicitly audited coordinate candidates to reported sites."""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute(
        """CREATE TABLE IF NOT EXISTS site_coordinate_candidate (
            site_id TEXT NOT NULL REFERENCES site(site_id),
            candidate_id TEXT NOT NULL REFERENCES location_candidate(candidate_id),
            link_reason TEXT NOT NULL,
            PRIMARY KEY(site_id,candidate_id)
        )"""
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--category", required=True)
    parser.add_argument("--role", choices=("field_object", "soil_study_context"), default="field_object")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    selected = [row for row in csv.DictReader(args.audit.open(encoding="utf-8")) if row["category"] == args.category]
    stats = {"selected": len(selected), "promoted": 0, "missing_candidate": 0,
             "reused_existing_site": 0, "ambiguous_existing_site": 0}
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        for row in selected:
            candidate = con.execute(
                """SELECT lc.latitude,lc.longitude,lc.context_text,a.artifact_id
                     FROM location_candidate lc JOIN extraction e ON e.extraction_id=lc.extraction_id
                     JOIN source_artifact a ON a.artifact_id=e.artifact_id
                    WHERE lc.candidate_id=? AND lc.status='unreviewed'""",
                (row["candidate_id"],),
            ).fetchone()
            if not candidate:
                stats["missing_candidate"] += 1
                continue
            lat, lon, context, artifact_id = candidate
            existing = con.execute(
                """SELECT DISTINCT s.site_id FROM site s
                   JOIN site_evidence se ON se.site_id=s.site_id
                   JOIN source_artifact sa ON sa.artifact_id=se.artifact_id
                   WHERE sa.document_id=(SELECT document_id FROM source_artifact WHERE artifact_id=?)
                     AND s.spatial_confidence IN ('exact','reported')
                     AND abs(s.latitude-?) < 0.000001 AND abs(s.longitude-?) < 0.000001""",
                (artifact_id, lat, lon),
            ).fetchall()
            if len(existing) > 1:
                stats["ambiguous_existing_site"] += 1
                continue
            site_id = existing[0][0] if existing else f"site:{row['candidate_id']}"
            precision = row.get("precision_hint", "explicit_coordinate")
            is_context = args.role == "soil_study_context"
            name = (f"Reported soil-study context {lat:.6f}, {lon:.6f}" if is_context
                    else f"Reported field object {lat:.6f}, {lon:.6f}")
            source = (
                f"Explicit author-reported {precision} coordinate; country validated; audited {row['category']}. "
                + ("Study/soil context, not an automatic sample or row-level measurement."
                   if is_context else "Field-object location, not an automatic row-level measurement.")
            )
            if not args.dry_run:
                if existing:
                    stats["reused_existing_site"] += 1
                else:
                    con.execute(
                        """INSERT INTO site(site_id,country_code,name,latitude,longitude,spatial_precision_m,spatial_confidence,geometry_source)
                           VALUES(?, 'RU', ?, ?, ?, NULL, 'reported', ?)""",
                        (site_id, name, lat, lon, source),
                    )
                    con.execute(
                        """INSERT INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                           VALUES(?,?,?,'coordinates')""",
                        (site_id, artifact_id, json.dumps({
                            "candidate_id": row["candidate_id"], "audit_category": row["category"],
                            "source_context": context,
                        }, ensure_ascii=False)),
                    )
                con.execute(
                    """INSERT OR IGNORE INTO site_coordinate_candidate(site_id,candidate_id,link_reason)
                       VALUES(?,?,?)""",
                    (site_id, row["candidate_id"], f"same_document_exact_coordinate+audited_{row['category']}"),
                )
                con.execute("UPDATE location_candidate SET status='accepted' WHERE candidate_id=?", (row["candidate_id"],))
            stats["promoted"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
