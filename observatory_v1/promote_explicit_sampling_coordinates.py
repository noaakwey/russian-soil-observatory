#!/usr/bin/env python3
"""Promote only newly extracted coordinates with explicit sampling evidence.

The companion audit classifies every source fragment.  This stage accepts the
strictest class only and retains all remaining coordinates as candidates for
later review; it never turns a city, district centre, or literature example
into a sampling point.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from audit_new_coordinate_context import classify


SQL = """
SELECT lc.candidate_id, lc.latitude, lc.longitude, lc.context_text, a.artifact_id
FROM location_candidate lc
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
JOIN extraction e ON e.extraction_id=lc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
WHERE lc.precision_hint LIKE ? AND lc.precision_hint LIKE ? AND lc.status='unreviewed'
  AND lv.country_code='RU' AND lv.result='inside'
ORDER BY lc.candidate_id
"""


def ensure_schema(con: sqlite3.Connection) -> None:
    """Record parser aliases without manufacturing duplicate operational sites."""
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
    parser.add_argument("--precision-prefix", default="russian_abbreviated_")
    parser.add_argument("--precision-suffix", default="", help="optional exact provenance suffix, e.g. _multiline")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = {"ru_candidates": 0, "explicit_sampling_context": 0, "not_explicit_sampling_context": 0, "promoted": 0}
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        stats["reused_existing_site"] = 0
        stats["ambiguous_existing_site"] = 0
        for candidate_id, lat, lon, context, artifact_id in con.execute(
            SQL, (args.precision_prefix + "%", "%" + args.precision_suffix)
        ):
            stats["ru_candidates"] += 1
            if classify(context or "") != "explicit_sampling_or_profile_context":
                stats["not_explicit_sampling_context"] += 1
                continue
            stats["explicit_sampling_context"] += 1
            existing = con.execute(
                """SELECT DISTINCT s.site_id FROM site s
                   JOIN site_evidence se ON se.site_id=s.site_id
                   JOIN source_artifact a ON a.artifact_id=se.artifact_id
                   WHERE a.document_id=(SELECT document_id FROM source_artifact WHERE artifact_id=?)
                     AND s.spatial_confidence IN ('exact','reported')
                     AND abs(s.latitude-?) < 0.000001 AND abs(s.longitude-?) < 0.000001""",
                (artifact_id, lat, lon),
            ).fetchall()
            if len(existing) > 1:
                stats["ambiguous_existing_site"] += 1
                continue
            site_id = existing[0][0] if existing else f"site:{candidate_id}"
            if not args.dry_run:
                if existing:
                    stats["reused_existing_site"] += 1
                else:
                    con.execute(
                        """INSERT INTO site(site_id,country_code,name,latitude,longitude,spatial_precision_m,spatial_confidence,geometry_source)
                           VALUES(?, 'RU', ?, ?, ?, NULL, 'reported', ?)""",
                        (site_id, f"Reported study point {lat:.6f}, {lon:.6f}", lat, lon,
                         "Explicit degree-minute/hemisphere coordinates; Natural Earth country check; sampling/profile context in source."),
                    )
                    con.execute(
                        """INSERT INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                           VALUES(?,?,?,'coordinates')""",
                        (site_id, artifact_id, context),
                    )
                con.execute(
                    """INSERT OR IGNORE INTO site_coordinate_candidate(site_id,candidate_id,link_reason)
                       VALUES(?,?, 'same_document_exact_coordinate+explicit_sampling_context')""",
                    (site_id, candidate_id),
                )
                con.execute("UPDATE location_candidate SET status='accepted' WHERE candidate_id=?", (candidate_id,))
            stats["promoted"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
