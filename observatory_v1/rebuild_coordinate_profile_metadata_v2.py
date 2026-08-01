#!/usr/bin/env python3
"""Retire superseded coordinate-profile claims before the stricter v2 pass.

Only derived assertions from the former extractor are removed.  The source
text, profile evidence, and all non-v1 author statements remain untouched.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        affected = [row[0] for row in con.execute(
            "SELECT DISTINCT profile_id FROM profile_author_statement "
            "WHERE extractor IN ('extract_coordinate_first_profile_metadata:v1','extract_coordinate_first_profile_metadata:v2')"
        )]
        claims = con.execute(
            "SELECT COUNT(*) FROM profile_author_statement "
            "WHERE extractor IN ('extract_coordinate_first_profile_metadata:v1','extract_coordinate_first_profile_metadata:v2')"
        ).fetchone()[0]
        if not args.dry_run:
            con.execute("DELETE FROM profile_author_statement WHERE extractor IN (?,?)",
                        ('extract_coordinate_first_profile_metadata:v1', 'extract_coordinate_first_profile_metadata:v2'))
            for field in ('author_soil_type_raw', 'author_profile_formula_raw'):
                for profile_id in affected:
                    remaining = con.execute(
                        "SELECT raw_value FROM profile_author_statement "
                        "WHERE profile_id=? AND field_name=? "
                        "ORDER BY CASE review_status WHEN 'accepted' THEN 0 WHEN 'unreviewed' THEN 1 ELSE 2 END, statement_id "
                        "LIMIT 1", (profile_id, field)).fetchone()
                    con.execute(f"UPDATE profile SET {field}=? WHERE profile_id=?",
                                (remaining[0] if remaining else None, profile_id))
            con.commit()
    print(json.dumps({'affected_profiles': len(affected), 'superseded_derived_claims': claims}, ensure_ascii=False))


if __name__ == '__main__':
    main()
