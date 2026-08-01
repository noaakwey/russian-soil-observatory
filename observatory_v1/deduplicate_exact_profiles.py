#!/usr/bin/env python3
"""Consolidate only profiles with the same canonical site and printed label.

This is deliberately narrower than geographic deduplication: two profiles are
eligible only when they already point to one site, share an exact normalized
field identifier, and are parser-created coordinate profiles.  Evidence and
literal author statements are copied before foreign keys are redirected.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import defaultdict
from pathlib import Path


def norm(value: str | None) -> str:
    return "".join((value or "").casefold().split())


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS profile_merge (
        retired_profile_id TEXT PRIMARY KEY,
        canonical_profile_id TEXT NOT NULL REFERENCES profile(profile_id),
        site_id TEXT NOT NULL REFERENCES site(site_id),
        merge_reason TEXT NOT NULL,
        merged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")
    con.execute("""CREATE TABLE IF NOT EXISTS profile_merge_evidence (
        retired_profile_id TEXT NOT NULL,
        canonical_profile_id TEXT NOT NULL,
        artifact_id TEXT NOT NULL,
        extraction_id TEXT,
        evidence_kind TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        migrated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        PRIMARY KEY(retired_profile_id,artifact_id,evidence_kind,evidence_text)
    )""")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    stats = {'duplicate_clusters': 0, 'retired_profiles': 0}
    audit: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute('PRAGMA foreign_keys=ON')
        if args.apply:
            ensure_schema(con)
        rows = con.execute("""SELECT p.profile_id,p.site_id,p.profile_label,
              (SELECT count(*) FROM horizon h WHERE h.profile_id=p.profile_id) horizons,
              (SELECT count(*) FROM sample s WHERE s.profile_id=p.profile_id) samples,
              (SELECT count(*) FROM measurement m WHERE m.profile_id=p.profile_id) measurements,
              (SELECT count(*) FROM profile_author_statement ps WHERE ps.profile_id=p.profile_id) statements
            FROM profile p
            WHERE p.profile_label IS NOT NULL
              AND (p.profile_id LIKE 'profile:explicit_pit:%'
                   OR p.profile_id LIKE 'profile:coordinate_first_label:%'
                   OR p.profile_id LIKE 'profile:direct:%')""").fetchall()
        groups: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            label = norm(row['profile_label'])
            if label:
                groups[(row['site_id'], label)].append(row)
        for (site_id, label), group in sorted(groups.items()):
            if len(group) < 2:
                continue
            stats['duplicate_clusters'] += 1
            # Keep the richest object; in a tie coordinate-first evidence is
            # preferred because it contains the source-local coordinate span.
            ranked = sorted(group, key=lambda r: (
                r['horizons'] + r['samples'] + r['measurements'] + r['statements'],
                int(r['profile_id'].startswith('profile:coordinate_first_label:')),
                int(r['profile_id'].startswith('profile:explicit_pit:')),
                r['profile_id']), reverse=True)
            canonical = ranked[0]
            for duplicate in ranked[1:]:
                audit.append({'site_id': site_id, 'normalized_label': label,
                              'canonical_profile_id': canonical['profile_id'],
                              'retired_profile_id': duplicate['profile_id'],
                              'canonical_statements': canonical['statements'],
                              'retired_statements': duplicate['statements']})
                stats['retired_profiles'] += 1
                if not args.apply:
                    continue
                retired = duplicate['profile_id']
                con.execute("""INSERT OR REPLACE INTO profile_merge
                    (retired_profile_id,canonical_profile_id,site_id,merge_reason)
                    VALUES(?,?,?,?)""", (retired, canonical['profile_id'], site_id,
                    'same canonical site and same printed profile label; coordinate parser duplicate'))
                con.execute("""INSERT OR IGNORE INTO profile_evidence
                    (profile_id,artifact_id,extraction_id,evidence_text,evidence_kind)
                    SELECT ?,artifact_id,extraction_id,evidence_text,evidence_kind
                    FROM profile_evidence WHERE profile_id=?""", (canonical['profile_id'], retired))
                # ``profile_evidence`` has one row per artifact/kind.  Keep a
                # second parser's differently scoped snippet in an immutable
                # merge ledger rather than silently losing it to that key.
                con.execute("""INSERT OR IGNORE INTO profile_merge_evidence
                    (retired_profile_id,canonical_profile_id,artifact_id,extraction_id,evidence_kind,evidence_text)
                    SELECT ?,?,artifact_id,extraction_id,evidence_kind,evidence_text
                    FROM profile_evidence WHERE profile_id=?""",
                    (retired, canonical['profile_id'], retired))
                con.execute("""INSERT OR IGNORE INTO profile_author_statement
                    (statement_id,profile_id,field_name,raw_value,artifact_id,extraction_id,evidence_text,extractor,review_status)
                    SELECT 'merged:' || statement_id,?,field_name,raw_value,artifact_id,extraction_id,evidence_text,extractor,review_status
                    FROM profile_author_statement WHERE profile_id=?""", (canonical['profile_id'], retired))
                for table in ('horizon', 'sample', 'measurement'):
                    con.execute(f'UPDATE {table} SET profile_id=? WHERE profile_id=?', (canonical['profile_id'], retired))
                if con.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='profile_quality_flag'").fetchone():
                    con.execute("""INSERT OR IGNORE INTO profile_quality_flag(profile_id,flag_code,detail,flagged_at)
                        SELECT ?,flag_code,detail,flagged_at FROM profile_quality_flag WHERE profile_id=?""",
                        (canonical['profile_id'], retired))
                    con.execute('DELETE FROM profile_quality_flag WHERE profile_id=?', (retired,))
                con.execute("""UPDATE profile SET
                    author_soil_type_raw=COALESCE(author_soil_type_raw,(SELECT author_soil_type_raw FROM profile WHERE profile_id=?)),
                    author_profile_formula_raw=COALESCE(author_profile_formula_raw,(SELECT author_profile_formula_raw FROM profile WHERE profile_id=?)),
                    soil_classification=COALESCE(soil_classification,(SELECT soil_classification FROM profile WHERE profile_id=?)),
                    classification_system=COALESCE(classification_system,(SELECT classification_system FROM profile WHERE profile_id=?)),
                    land_use=COALESCE(land_use,(SELECT land_use FROM profile WHERE profile_id=?))
                    WHERE profile_id=?""", (retired, retired, retired, retired, retired, canonical['profile_id']))
                con.execute('DELETE FROM profile_author_statement WHERE profile_id=?', (retired,))
                con.execute('DELETE FROM profile_evidence WHERE profile_id=?', (retired,))
                con.execute('DELETE FROM profile WHERE profile_id=?', (retired,))
        if args.apply:
            con.commit()
    if args.output:
        fields = ['site_id','normalized_label','canonical_profile_id','retired_profile_id','canonical_statements','retired_statements']
        with args.output.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
