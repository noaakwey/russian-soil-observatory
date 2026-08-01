#!/usr/bin/env python3
"""Remove only implausible labels from document-level prose descriptors.

The profile and its primary-text evidence are retained.  A flag records why
the convenience label was cleared, so downstream users never confuse a word
fragment (for example ``а``) with an author-assigned pit identifier.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


VALID = re.compile(
    r"^(?:\d{1,4}|[A-Za-zА-Яа-я]{1,8}-?\d+[A-Za-zА-Яа-я]?(?:[-–][A-Za-zА-Яа-я0-9]+)*|\d+[A-Za-zА-Яа-я]{1,8}(?:[-–][A-Za-zА-Яа-я0-9]+)*)$"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    flagged: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        if not args.dry_run:
            con.execute("""CREATE TABLE IF NOT EXISTS profile_quality_flag (
              profile_id TEXT NOT NULL REFERENCES profile(profile_id),
              flag_code TEXT NOT NULL,
              detail TEXT NOT NULL,
              flagged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
              PRIMARY KEY(profile_id,flag_code)
            )""")
        rows = con.execute("""SELECT profile_id,profile_label FROM profile
            WHERE profile_id LIKE 'profile:prose:%' AND profile_label IS NOT NULL""").fetchall()
        for profile_id, label in rows:
            if VALID.fullmatch(label.strip()):
                continue
            flagged.append({"profile_id": profile_id, "raw_label": label})
            if not args.dry_run:
                con.execute("""INSERT OR IGNORE INTO profile_quality_flag(profile_id,flag_code,detail)
                    VALUES(?,?,?)""", (profile_id, "invalid_prose_label",
                    f"Cleared non-identifier prose label: {label!r}; profile evidence retained."))
                con.execute("UPDATE profile SET profile_label=NULL WHERE profile_id=?", (profile_id,))
        if not args.dry_run:
            con.commit()
    print(json.dumps({"flagged": flagged, "count": len(flagged)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
