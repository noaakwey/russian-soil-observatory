#!/usr/bin/env python3
"""Tag which `reported`-tier coordinate documents state an explicit datum.

ОГРАНИЧЕНИЯ item 11 in the manuscript claimed the coordinate reference system
is simply "not documented" and the WGS-84 assumption "not confirmed by any
field in the database" — a blanket claim never actually checked against the
source text. A full-text search turns up genuine, explicit statements in a
meaningful share of documents ("используемый эллипсоид - WGS84", "Координаты
WGS 84" printed as a table column header, etc.), so the claim is overstated.

This script does not change any interpretation of stored coordinates (all are
still treated as WGS-84 by convention, as before) — it only records, per
document with a `site.spatial_confidence='reported'` coordinate, whether an
explicit datum statement was found in that document's extracted text, which
keyword matched, and a short surrounding snippet as evidence. That lets the
limitation be stated with real numbers instead of a blanket claim.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS document_coordinate_datum_evidence (
  document_id TEXT PRIMARY KEY REFERENCES document(document_id),
  datum TEXT NOT NULL,
  matched_text TEXT NOT NULL,
  evidence_snippet TEXT NOT NULL,
  extracted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""

# Ordered so the more specific/unambiguous keywords are checked first.
PATTERNS: list[tuple[str, re.Pattern]] = [
    ('WGS-84', re.compile(r'WGS[\s-]?84', re.I)),
    ('SK-42', re.compile(r'СК[\s-]?42', re.I)),
    ('SK-95', re.compile(r'СК[\s-]?95', re.I)),
    ('PZ-90', re.compile(r'ПЗ[\s-]?90', re.I)),
    ('GSK-2011', re.compile(r'ГСК[\s-]?2011', re.I)),
    ('Pulkovo', re.compile(r'Пулков\w*', re.I)),
]
CONTEXT = 70


def find_datum(text: str) -> tuple[str, str, str] | None:
    for datum, pattern in PATTERNS:
        m = pattern.search(text or '')
        if m:
            start = max(0, m.start() - CONTEXT)
            end = min(len(text), m.end() + CONTEXT)
            snippet = text[start:end].replace('\n', ' ').strip()
            return datum, m.group(0), snippet
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)

        doc_ids = [row[0] for row in con.execute("""
            SELECT DISTINCT a.document_id
            FROM site s
            JOIN site_evidence se ON se.site_id = s.site_id AND se.evidence_kind = 'coordinates'
            JOIN source_artifact a ON a.artifact_id = se.artifact_id
            WHERE s.spatial_confidence = 'reported'
        """)]

        payload = []
        for document_id in doc_ids:
            row = con.execute("""
                SELECT e.raw_text FROM extraction e
                JOIN source_artifact a ON a.artifact_id = e.artifact_id
                WHERE a.document_id = ? AND a.artifact_type = 'text'
                ORDER BY length(e.raw_text) DESC LIMIT 1
            """, (document_id,)).fetchone()
            text = (row[0] if row else '') or ''
            found = find_datum(text)
            if found:
                datum, matched_text, snippet = found
                payload.append((document_id, datum, matched_text, snippet))

        con.execute("DELETE FROM document_coordinate_datum_evidence")
        con.executemany("""
            INSERT INTO document_coordinate_datum_evidence
              (document_id, datum, matched_text, evidence_snippet)
            VALUES (?,?,?,?)
        """, payload)
        con.commit()

    by_datum: dict[str, int] = {}
    for _, datum, _, _ in payload:
        by_datum[datum] = by_datum.get(datum, 0) + 1

    report = {
        'reported_tier_documents': len(doc_ids),
        'documents_with_explicit_datum': len(payload),
        'documents_without_explicit_datum': len(doc_ids) - len(payload),
        'by_datum': by_datum,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
