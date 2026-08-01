#!/usr/bin/env python3
"""Promote legacy explicit-profile OCR rows after provenance re-audit.

These records already retain a table cell candidate and an explicit profile
label whose coordinate is stated in the same source phrase.  They were once
labelled ``flagged`` by a conservative staging script; that label obscured a
direct row-to-coordinate proof in the analysis export.  This migration is
idempotent and affects no document-level-only observations.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


SQL = """
SELECT m.measurement_id
FROM measurement m
JOIN profile p ON p.profile_id=m.profile_id
JOIN site s ON s.site_id=m.site_id
JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id
WHERE m.qa_status='flagged'
  AND m.evidence_locator LIKE '%explicit_profile_label_to_coordinate%'
  AND m.evidence_locator LIKE '%table_candidate_id%'
  AND p.notes='Explicit pit label and author-reported coordinate in one source phrase.'
  AND s.country_code='RU'
  AND s.spatial_confidence IN ('exact','reported')
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        ids = [row[0] for row in con.execute(SQL)]
        if not args.dry_run:
            con.executemany("UPDATE measurement SET qa_status='accepted' WHERE measurement_id=?", [(item,) for item in ids])
            con.commit()
    print(json.dumps({'eligible_explicit_profile_rows': len(ids), 'promoted': 0 if args.dry_run else len(ids)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
