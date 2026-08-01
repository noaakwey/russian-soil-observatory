#!/usr/bin/env python3
"""Promote a manually audited literal author statement to one profile.

Input is deliberately explicit: each row names the profile, primary-text
artifact and the exact evidence excerpt.  The script refuses a statement that
cannot be traced to a reported/exact Russian coordinate-linked profile.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from extract_author_profile_metadata import ensure_schema


FIELDS = {"author_soil_type_raw", "author_profile_formula_raw"}


def ident(*parts: str) -> str:
    return "author-direct:" + hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:24]


def compact(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", "", value.casefold())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    required = {"profile_id", "field_name", "raw_value", "artifact_id", "evidence_text"}
    if not rows or any(set(row) < required for row in rows):
        raise SystemExit(f"Input must have columns: {sorted(required)}")
    promoted: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        for row in rows:
            field = row["field_name"].strip()
            raw = row["raw_value"].strip()
            evidence = row["evidence_text"].strip()
            if field not in FIELDS or not raw or not evidence or compact(raw) not in compact(evidence):
                raise SystemExit(f"Invalid literal statement for {row['profile_id']}")
            profile = con.execute("""SELECT p.profile_id,p.profile_label,p.author_soil_type_raw,
                                          p.author_profile_formula_raw,s.spatial_confidence
                                   FROM profile p JOIN site s ON s.site_id=p.site_id
                                   WHERE p.profile_id=?""", (row["profile_id"],)).fetchone()
            artifact = con.execute("SELECT artifact_id,artifact_type,source_path FROM source_artifact WHERE artifact_id=?",
                                   (row["artifact_id"],)).fetchone()
            if not profile or not artifact or artifact["artifact_type"] != "text":
                raise SystemExit(f"Missing profile or primary text artifact for {row['profile_id']}")
            if profile["spatial_confidence"] not in {"exact", "reported"}:
                raise SystemExit(f"Profile {row['profile_id']} has no reported/exact coordinate")
            source = Path(artifact["source_path"]).read_text(encoding="utf-8", errors="replace")
            # Both the profile label and literal statement must occur in the
            # primary source.  The excerpt itself remains the displayed proof.
            if profile["profile_label"] not in source or compact(raw) not in compact(source):
                raise SystemExit(f"Primary text does not confirm statement for {row['profile_id']}")
            statement_id = ident(row["profile_id"], field, raw, row["artifact_id"])
            record = {"statement_id": statement_id, "profile_id": row["profile_id"],
                      "field_name": field, "raw_value": raw, "artifact_id": row["artifact_id"],
                      "evidence_text": evidence, "profile_label": profile["profile_label"] or ""}
            promoted.append(record)
            if not args.dry_run:
                con.execute("""INSERT INTO profile_author_statement
                    (statement_id,profile_id,field_name,raw_value,artifact_id,extraction_id,evidence_text,extractor,review_status)
                    VALUES(:statement_id,:profile_id,:field_name,:raw_value,:artifact_id,NULL,:evidence_text,
                            'promote_direct_author_profile_statements:v1','accepted')
                    ON CONFLICT(profile_id,field_name,raw_value,artifact_id) DO NOTHING""", record)
                con.execute(f"UPDATE profile SET {field}=COALESCE({field},?) WHERE profile_id=?",
                            (raw, row["profile_id"]))
        if not args.dry_run:
            con.commit()
    print(json.dumps({"selected": len(rows), "promoted": len(promoted), "rows": promoted}, ensure_ascii=False))


if __name__ == "__main__":
    main()
