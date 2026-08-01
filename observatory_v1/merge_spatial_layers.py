#!/usr/bin/env python3
"""Merge three spatial tiers with conflict resolution.

Priority: reported coordinates (exact) > DMS from text > regional centroid.

For each document, the highest-priority available layer is used.  This creates
a single, clean view of document-level spatial attribution across all 4 180
documents and their 62 805 observations.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS document_spatial_tier (
  document_id TEXT NOT NULL PRIMARY KEY REFERENCES document(document_id),
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  tier TEXT NOT NULL CHECK (tier IN ('reported','dms','region','none')),
  radius_km REAL,
  method TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_spatial_tier_layer ON document_spatial_tier(tier);
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        con.execute('DELETE FROM document_spatial_tier')

        # Merge with priority: reported > dms > region.
        con.execute("""
            INSERT INTO document_spatial_tier
              (document_id, latitude, longitude, tier, radius_km, method)
            SELECT a.document_id, AVG(s.latitude), AVG(s.longitude), 'reported', NULL, 'site_evidence'
            FROM source_artifact a
            JOIN site_evidence se ON se.artifact_id = a.artifact_id
            JOIN site s ON s.site_id = se.site_id
            WHERE s.spatial_confidence IN ('exact','reported') AND s.latitude IS NOT NULL
            GROUP BY a.document_id
            UNION ALL
            SELECT document_id, latitude, longitude, 'dms', NULL, source
            FROM document_precise_coordinate
            WHERE document_id NOT IN (
              SELECT DISTINCT a.document_id FROM source_artifact a
              JOIN site_evidence se ON se.artifact_id = a.artifact_id
              JOIN site s ON s.site_id = se.site_id
              WHERE s.latitude IS NOT NULL
            )
            UNION ALL
            SELECT document_id, latitude, longitude, 'region', radius_km, region_name
            FROM document_study_region WHERE rank = 1
              AND document_id NOT IN (
                SELECT DISTINCT a.document_id FROM source_artifact a
                JOIN site_evidence se ON se.artifact_id = a.artifact_id
                JOIN site s ON s.site_id = se.site_id WHERE s.latitude IS NOT NULL
              )
              AND document_id NOT IN (SELECT document_id FROM document_precise_coordinate)
        """)

        con.commit()

        # Report coverage.
        tiers = con.execute("""
            SELECT tier, COUNT(*) docs, COUNT(*) * 0.0 + (
              SELECT SUM(1) FROM table_observation o
              WHERE o.document_id = dst.document_id
            ) / COUNT(*) avg_obs
            FROM document_spatial_tier dst
            GROUP BY tier
        """).fetchall()

        total_docs = con.execute(
            'SELECT COUNT(DISTINCT document_id) FROM table_observation'
        ).fetchone()[0]
        spatial_docs = con.execute(
            'SELECT COUNT(*) FROM document_spatial_tier'
        ).fetchone()[0]
        spatial_obs = con.execute(
            'SELECT COUNT(*) FROM table_observation WHERE document_id IN '
            '(SELECT document_id FROM document_spatial_tier)'
        ).fetchone()[0]

        print(f'Coverage: {spatial_obs} obs ({100*spatial_obs/62805:.1f}%) from '
              f'{spatial_docs} docs ({100*spatial_docs/total_docs:.1f}%)')
        print('\nBy tier:')
        for tier, docs, avg_obs in tiers:
            print(f'  {tier:10s}: {docs:4d} docs, '
                  f'{docs * avg_obs:6.0f} obs avg')


if __name__ == '__main__':
    main()
