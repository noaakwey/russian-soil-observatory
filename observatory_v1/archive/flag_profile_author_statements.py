#!/usr/bin/env python3
"""Flag extraction boundary errors without deleting author-text evidence.

The profile statement layer is intentionally evidence preserving.  This
post-extraction QC therefore never deletes a literal fragment: it flags known
parser-boundary failures and removes only the denormalized convenience value on
``profile``.  Reviewers can still inspect the original text in
``profile_author_statement``.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


RULES = [
    (
        "profile_vial_podzol_text_boundary",
        "author_soil_type_raw",
        "%profile vial podzol on a terrace of the Khoseda-Yu River%",
        "Sentence boundary/parser error: this is surrounding prose, not a literal soil-type statement.",
    ),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    flagged: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        columns = {row[1] for row in con.execute("PRAGMA table_info(profile_author_statement)")}
        if "review_status" not in columns and not args.dry_run:
            con.execute("ALTER TABLE profile_author_statement ADD COLUMN review_status TEXT NOT NULL DEFAULT 'unreviewed'")
        for rule, field_name, pattern, reason in RULES:
            rows = con.execute("""SELECT statement_id,profile_id,raw_value
                FROM profile_author_statement WHERE field_name=? AND raw_value LIKE ?""",
                (field_name, pattern)).fetchall()
            for statement_id, profile_id, raw_value in rows:
                flagged.append({"statement_id": statement_id, "profile_id": profile_id,
                                "rule": rule, "reason": reason})
                if not args.dry_run:
                    con.execute("UPDATE profile_author_statement SET review_status='flagged' WHERE statement_id=?", (statement_id,))
                    con.execute(f"UPDATE profile SET {field_name}=NULL WHERE profile_id=? AND {field_name}=?",
                                (profile_id, raw_value))
        if not args.dry_run:
            con.commit()
    print(json.dumps({"flagged": flagged, "count": len(flagged)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
