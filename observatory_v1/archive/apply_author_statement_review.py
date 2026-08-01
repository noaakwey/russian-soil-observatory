#!/usr/bin/env python3
"""Apply a human-reviewed author-statement decision log.

The literal statement rows are never deleted.  The denormalized fields on
``profile`` are rebuilt exclusively from accepted rows, so a rejected OCR or
neighbouring-pit match cannot silently remain visible as an author fact.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


VALID = {"accepted", "flagged"}
FIELDS = {"author_soil_type_raw", "author_profile_formula_raw"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    decisions = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    if not decisions or any({"statement_id", "review_status", "reason"} - set(row) for row in decisions):
        raise SystemExit("Input requires statement_id,review_status,reason")
    if any(row["review_status"] not in VALID for row in decisions):
        raise SystemExit(f"review_status must be one of {sorted(VALID)}")

    with sqlite3.connect(args.db) as con:
        existing = {row[0] for row in con.execute("SELECT statement_id FROM profile_author_statement")}
        missing = [row["statement_id"] for row in decisions if row["statement_id"] not in existing]
        if missing:
            raise SystemExit(f"Unknown statement ids: {missing}")
        if not args.dry_run:
            con.executemany("UPDATE profile_author_statement SET review_status=? WHERE statement_id=?",
                            [(row["review_status"], row["statement_id"]) for row in decisions])
            # The profile columns are convenience fields.  Exact statements,
            # with their evidence and all alternatives, stay in the statement
            # table; only accepted values may appear on the profile row.
            for field in FIELDS:
                con.execute(f"UPDATE profile SET {field}=NULL")
                con.execute(f"""
                    UPDATE profile
                    SET {field}=(
                        SELECT pas.raw_value
                        FROM profile_author_statement pas
                        WHERE pas.profile_id=profile.profile_id
                          AND pas.field_name=? AND pas.review_status='accepted'
                        ORDER BY pas.statement_id
                        LIMIT 1
                    )
                    WHERE EXISTS (
                        SELECT 1 FROM profile_author_statement pas
                        WHERE pas.profile_id=profile.profile_id
                          AND pas.field_name=? AND pas.review_status='accepted'
                    )
                """, (field, field))
            con.commit()
        counts = dict(con.execute("SELECT review_status,COUNT(*) FROM profile_author_statement GROUP BY review_status"))
        materialized = dict(con.execute("""
            SELECT field_name,COUNT(*) FROM (
              SELECT 'author_soil_type_raw' AS field_name FROM profile WHERE author_soil_type_raw IS NOT NULL
              UNION ALL
              SELECT 'author_profile_formula_raw' FROM profile WHERE author_profile_formula_raw IS NOT NULL
            ) GROUP BY field_name
        """))
    print(json.dumps({"reviewed": len(decisions), "statuses": counts,
                      "profile_convenience_fields": materialized}, ensure_ascii=False))


if __name__ == "__main__":
    main()
