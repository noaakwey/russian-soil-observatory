#!/usr/bin/env python3
"""Consolidate duplicate parser sites for one document and exact coordinate.

Only same-document, same-coordinate `reported`/`exact` sites are eligible.
Every retired ID is retained in ``site_merge`` and all source evidence is
copied to the canonical site before any foreign keys are redirected.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


RANK = {"exact": 2, "reported": 1}


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS site_merge (
        retired_site_id TEXT PRIMARY KEY,
        canonical_site_id TEXT NOT NULL,
        document_id TEXT NOT NULL REFERENCES document(document_id),
        merge_reason TEXT NOT NULL,
        merged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    stats = {"duplicate_clusters": 0, "retired_sites": 0, "skipped_cross_document_site": 0}
    audit: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if args.apply:
            ensure_schema(con)
        rows = con.execute("""
            SELECT DISTINCT d.document_id,s.site_id,s.latitude,s.longitude,
                   s.spatial_confidence,s.spatial_precision_m,
                   (SELECT count(*) FROM profile p WHERE p.site_id=s.site_id) AS profiles,
                   (SELECT count(*) FROM sample sm WHERE sm.site_id=s.site_id) AS samples,
                   (SELECT count(*) FROM measurement m WHERE m.site_id=s.site_id) AS measurements
            FROM site s JOIN site_evidence se ON se.site_id=s.site_id
            JOIN source_artifact a ON a.artifact_id=se.artifact_id
            JOIN document d ON d.document_id=a.document_id
            WHERE s.spatial_confidence IN ('exact','reported')
        """).fetchall()
        by_coordinate: dict[tuple[str, float, float], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            by_coordinate[(row['document_id'], round(row['latitude'], 7), round(row['longitude'], 7))].append(row)
        doc_count = {r['site_id']: r['n'] for r in con.execute("""
            SELECT se.site_id,count(DISTINCT a.document_id) n
            FROM site_evidence se JOIN source_artifact a ON a.artifact_id=se.artifact_id
            GROUP BY se.site_id
        """)}
        for (document_id, latitude, longitude), group in sorted(by_coordinate.items()):
            ids = {r['site_id'] for r in group}
            if len(ids) < 2:
                continue
            if any(doc_count[site_id] != 1 for site_id in ids):
                stats['skipped_cross_document_site'] += 1
                continue
            stats['duplicate_clusters'] += 1
            ranked = sorted(group, key=lambda r: (
                r['measurements'] + r['samples'] + r['profiles'], RANK[r['spatial_confidence']],
                -(r['spatial_precision_m'] or 1e99), r['site_id']), reverse=True)
            canonical = ranked[0]['site_id']
            for duplicate in ranked[1:]:
                retired = duplicate['site_id']
                audit.append({"document_id": document_id, "latitude": latitude, "longitude": longitude,
                              "canonical_site_id": canonical, "retired_site_id": retired,
                              "canonical_confidence": ranked[0]['spatial_confidence'],
                              "retired_confidence": duplicate['spatial_confidence'],
                              "canonical_profiles": ranked[0]['profiles'], "retired_profiles": duplicate['profiles'],
                              "canonical_measurements": ranked[0]['measurements'], "retired_measurements": duplicate['measurements']})
                stats['retired_sites'] += 1
                if args.apply:
                    con.execute("""INSERT OR REPLACE INTO site_merge
                        (retired_site_id,canonical_site_id,document_id,merge_reason)
                        VALUES(?,?,?,?)""", (retired, canonical, document_id,
                        'same document and same author-reported coordinate; parser-variant duplicate'))
                    con.execute("""INSERT OR IGNORE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind)
                        SELECT ?,artifact_id,evidence_text,evidence_kind FROM site_evidence WHERE site_id=?""",
                        (canonical, retired))
                    for table in ('profile', 'sample', 'measurement'):
                        con.execute(f"UPDATE {table} SET site_id=? WHERE site_id=?", (canonical, retired))
                    con.execute("DELETE FROM site_evidence WHERE site_id=?", (retired,))
                    con.execute("DELETE FROM site WHERE site_id=?", (retired,))
        if args.apply:
            con.commit()
    if args.output:
        fields = ['document_id','latitude','longitude','canonical_site_id','retired_site_id',
                  'canonical_confidence','retired_confidence','canonical_profiles','retired_profiles',
                  'canonical_measurements','retired_measurements']
        with args.output.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
