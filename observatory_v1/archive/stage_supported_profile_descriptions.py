#!/usr/bin/env python3
"""Create auditable *descriptive* profiles from prose at a unique reported site.

This stage deliberately does not create a profile merely because an article
mentions a soil class.  The sentence must explicitly describe a profile, pit,
section, or horizon and the document must contain exactly one Russian reported
coordinate.  The result is a study-level spatial linkage, not a claim that
every prose descriptor has an independently measured pit coordinate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


PROFILE_LANGUAGE = re.compile(
    r"\b(?:soil\s+(?:profile|pit)|profile\s*(?:no\.?|#)?\s*[A-Za-z0-9-]*|"
    r"soil\s+section|pedon|horizon\s+[A-Za-z0-9]+|"
    r"почвенн\w*\s+(?:профил|разрез)|(?:почвенн\w*\s+)?разрез\w*|"
    r"профил\w*\s+почв\w*|горизонт\w*\s+[A-Za-zА-Яа-я0-9]+)\b",
    re.I,
)

# A prose descriptor can be useful without a printed pit number.  What it
# cannot be is a one-letter tail of a Russian word accidentally consumed by a
# permissive ``разрез`` regex.  Keep only real numeric/alphanumeric labels;
# otherwise explicitly store an unlabelled descriptor.
PROFILE_LABEL = re.compile(
    r"^(?:\d{1,4}|[A-Za-zА-Яа-я]{1,8}-?\d+[A-Za-zА-Яа-я]?(?:[-–][A-Za-zА-Яа-я0-9]+)*|\d+[A-Za-zА-Яа-я]{1,8}(?:[-–][A-Za-zА-Яа-я0-9]+)*)$"
)


def valid_label(value: str | None) -> str | None:
    raw = (value or "").strip()
    return raw if PROFILE_LABEL.fullmatch(raw) else None

SQL = """
WITH single_reported_site AS (
  SELECT d.document_id, MIN(se.site_id) AS site_id
  FROM document d
  JOIN source_artifact a ON a.document_id=d.document_id
  JOIN site_evidence se ON se.artifact_id=a.artifact_id
  JOIN site s ON s.site_id=se.site_id
  WHERE s.country_code='RU' AND s.spatial_confidence IN ('exact','reported')
  GROUP BY d.document_id
  HAVING COUNT(DISTINCT se.site_id)=1
)
SELECT pc.candidate_id, pc.extraction_id, pc.profile_label,
       pc.soil_classification_raw, pc.classification_system_candidate,
       pc.land_use_raw, pc.context_text, a.artifact_id, d.document_id,
       one.site_id
FROM profile_candidate pc
JOIN extraction e ON e.extraction_id=pc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
JOIN single_reported_site one ON one.document_id=d.document_id
WHERE pc.status='unreviewed' AND a.artifact_type='text'
ORDER BY d.document_id, pc.candidate_id
"""


def digest(*items: str | None) -> str:
    raw = "\x1f".join((x or "").casefold().strip() for x in items)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats: Counter[str] = Counter()
    seen: set[tuple[str, str, str, str, str]] = set()
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute(
            """CREATE TABLE IF NOT EXISTS profile_evidence (
              profile_id TEXT NOT NULL REFERENCES profile(profile_id),
              artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
              extraction_id TEXT REFERENCES extraction(extraction_id),
              evidence_text TEXT NOT NULL,
              evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('profile_description','table_header','table_row')),
              PRIMARY KEY (profile_id, artifact_id, evidence_kind)
            )"""
        )
        cols = [x[0] for x in con.execute(SQL).description]
        for row in con.execute(SQL):
            rec = dict(zip(cols, row))
            context = rec["context_text"] or ""
            if not PROFILE_LANGUAGE.search(context):
                stats["not_explicit_profile_context"] += 1
                continue
            label = valid_label(rec["profile_label"])
            if rec["profile_label"] and not label:
                stats["invalid_label_held_unlabelled"] += 1
            key = (
                rec["document_id"], rec["site_id"], label or "",
                rec["soil_classification_raw"] or "", rec["land_use_raw"] or "",
            )
            if key in seen:
                stats["duplicate_descriptor"] += 1
                continue
            seen.add(key)
            profile_id = "profile:prose:" + digest(*key)
            note = (
                "Prose profile descriptor linked at document level because this "
                "document contains one reported Russian coordinate; it is not a "
                "row-level or independently surveyed pit coordinate."
            )
            evidence = json.dumps(
                {"profile_candidate_id": rec["candidate_id"],
                 "spatial_linkage": "document_single_reported_coordinate"},
                ensure_ascii=False,
            ) + "\n" + context
            if not args.dry_run:
                con.execute(
                    """INSERT INTO profile(profile_id,site_id,profile_label,soil_classification,
                       classification_system,land_use,notes)
                       VALUES(?,?,?,?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET
                         soil_classification=COALESCE(excluded.soil_classification,profile.soil_classification),
                         classification_system=COALESCE(excluded.classification_system,profile.classification_system),
                         land_use=COALESCE(excluded.land_use,profile.land_use), notes=excluded.notes""",
                    (profile_id, rec["site_id"], label,
                     rec["soil_classification_raw"], rec["classification_system_candidate"],
                     rec["land_use_raw"], note),
                )
                con.execute(
                    """INSERT INTO profile_evidence(profile_id,artifact_id,extraction_id,evidence_text,evidence_kind)
                       VALUES(?,?,?,?, 'profile_description')
                       ON CONFLICT(profile_id,artifact_id,evidence_kind) DO UPDATE SET
                         evidence_text=excluded.evidence_text""",
                    (profile_id, rec["artifact_id"], rec["extraction_id"], evidence),
                )
                con.execute("UPDATE profile_candidate SET status='accepted' WHERE candidate_id=?", (rec["candidate_id"],))
            stats["staged_descriptive_profiles"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
