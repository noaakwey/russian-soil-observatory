#!/usr/bin/env python3
"""Collect literal author soil-type/formula statements from primary text.

This is deliberately a discovery layer.  It does *not* populate ``profile``:
an author statement becomes operational only after a later exact link to one
coordinate-linked profile.  Keeping these candidates makes both positive and
negative evidence available without inventing a pit-to-coordinate relation.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from extract_author_profile_metadata import clean, excerpt
from extract_coordinate_first_profile_metadata import (
    FIELD_LABEL, TYPE_SIGNAL, clean_formula, clean_type, iter_cued_short_formulas,
)


RUSSIAN_TYPE = re.compile(
    r"(?:\bпочва|\bпочвы)\s*(?:—|–|—|-|:)?\s*"
    r"(?P<value>[А-Яа-яЁё][A-Za-zА-Яа-яЁё0-9(),/ .–—-]{2,260}?)"
    r"(?=\s+(?:с\s+формул\w*|формул\w*\s+(?:морфологическ\w+\s+)?строени\w*\s+профил\w*)|[.;])",
    re.I,
)
ENGLISH_TYPE = re.compile(
    r"\b(?:the\s+)?soil\s+(?:was|is|were|are|is\s+represented\s+by|"
    r"is\s+classified\s+as|belongs\s+to)\s*[:–—-]?\s*"
    r"(?P<value>[A-Za-z][A-Za-z0-9(),/ .–—-]{2,240}?)"
    r"(?=\s*(?:[.;]|,\s*(?:with|under|on|at)\b))",
    re.I,
)


def candidate_id(*parts: str) -> str:
    return "author-discovery:" + hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:24]


def nearest_label(text: str, position: int) -> tuple[str | None, int | None, str | None]:
    """Return a label only where the primary text makes it locally usable.

    A label in the preceding OCR column is not a profile association.  For a
    candidate to be eligible for automatic linking, the printed field label
    must end at most 120 characters before the statement or begin at most 80
    characters after it.  The value remains in the discovery layer otherwise.
    """
    labels = list(FIELD_LABEL.finditer(text))
    before = [m for m in labels if m.end() <= position and position - m.end() <= 120]
    if before:
        match = before[-1]
        return match.group("label"), position - match.end(), "before"
    after = [m for m in labels if m.start() >= position and m.start() - position <= 80]
    if after:
        match = after[0]
        return match.group("label"), match.start() - position, "after"
    return None, None, None


def statement_matches(text: str, *, include_types: bool = True,
                      include_formulas: bool = True) -> list[tuple[str, str, int, int, str | None, int | None, str | None]]:
    found: list[tuple[str, str, int, int, str | None, int | None, str | None]] = []
    if include_types:
        for pattern in (RUSSIAN_TYPE, ENGLISH_TYPE):
            for match in pattern.finditer(text):
                raw = clean_type(clean(match.group("value").strip(" ,;:")))
                if TYPE_SIGNAL.search(raw):
                    label, distance, side = nearest_label(text, match.start("value"))
                    found.append(("author_soil_type_raw", raw, match.start("value"),
                                  match.end("value"), label, distance, side))
    if include_formulas:
        for formula, start, end in iter_cued_short_formulas(text):
            raw = clean_formula(formula.strip(" ,;:."))
            label, distance, side = nearest_label(text, start)
            found.append(("author_profile_formula_raw", raw, start, end, label, distance, side))
    return found


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS document_author_statement_candidate (
        candidate_id TEXT PRIMARY KEY,
        document_id TEXT NOT NULL REFERENCES document(document_id),
        artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
        field_name TEXT NOT NULL CHECK (field_name IN ('author_soil_type_raw','author_profile_formula_raw')),
        profile_label_raw TEXT,
        raw_value TEXT NOT NULL,
        evidence_text TEXT NOT NULL,
        linkable INTEGER NOT NULL DEFAULT 0 CHECK (linkable IN (0,1)),
        link_status TEXT NOT NULL DEFAULT 'unlinked'
          CHECK (link_status IN ('unlinked','linked','rejected')),
        extractor TEXT NOT NULL,
        UNIQUE(document_id, artifact_id, field_name, raw_value, profile_label_raw)
    )""")
    con.execute("CREATE INDEX IF NOT EXISTS idx_document_author_statement_candidate_document "
                "ON document_author_statement_candidate(document_id, link_status)")
    columns = {row[1] for row in con.execute("PRAGMA table_info(document_author_statement_candidate)")}
    if "linkable" not in columns:
        con.execute("ALTER TABLE document_author_statement_candidate "
                    "ADD COLUMN linkable INTEGER NOT NULL DEFAULT 0 CHECK (linkable IN (0,1))")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-formulas", action="store_true",
                    help="Scan only bounded formula patterns; useful for a safe corpus-wide rerun.")
    args = ap.parse_args()
    stats = {"artifacts_scanned": 0, "missing_text": 0, "type_candidates": 0,
             "formula_candidates": 0, "labelled_candidates": 0}
    audit: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        rows = con.execute("""
            SELECT a.artifact_id,a.document_id,a.source_path
            FROM source_artifact a
            WHERE a.artifact_type='text'
            ORDER BY a.document_id,a.artifact_id
        """).fetchall()
        for row in rows:
            try:
                text = clean(Path(row["source_path"]).read_text(encoding="utf-8", errors="replace"))
            except OSError:
                stats["missing_text"] += 1
                continue
            stats["artifacts_scanned"] += 1
            seen: set[tuple[str, str, str | None]] = set()
            for field, raw, start, end, label, distance, side in statement_matches(
                    text, include_types=not args.only_formulas):
                key = (field, raw, label)
                if key in seen:
                    continue
                seen.add(key)
                stats["type_candidates" if field == "author_soil_type_raw" else "formula_candidates"] += 1
                stats["labelled_candidates"] += int(label is not None)
                record = {"candidate_id": candidate_id(row["document_id"], row["artifact_id"], field, raw, label or ""),
                          "document_id": row["document_id"], "artifact_id": row["artifact_id"],
                          "field_name": field, "profile_label_raw": label or "", "raw_value": raw,
                          "evidence_text": excerpt(text, start, end),
                          "linkable": int(label is not None and side == "before"),
                          "link_status": "unlinked", "label_distance_chars": "" if distance is None else str(distance),
                          "label_position": side or ""}
                audit.append(record)
                if not args.dry_run:
                    con.execute("""INSERT INTO document_author_statement_candidate
                        (candidate_id,document_id,artifact_id,field_name,profile_label_raw,raw_value,evidence_text,linkable,extractor)
                        VALUES(:candidate_id,:document_id,:artifact_id,:field_name,NULLIF(:profile_label_raw,''),:raw_value,:evidence_text,:linkable,
                                'discover_author_profile_statements:v2')
                        ON CONFLICT(candidate_id) DO UPDATE SET
                          evidence_text=excluded.evidence_text, linkable=excluded.linkable,
                          extractor=excluded.extractor""", record)
        if not args.dry_run:
            con.commit()
    if args.output:
        fields = ["candidate_id", "document_id", "artifact_id", "field_name", "profile_label_raw",
                  "raw_value", "linkable", "label_position", "label_distance_chars", "link_status", "evidence_text"]
        with args.output.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
