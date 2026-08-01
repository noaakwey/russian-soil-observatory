#!/usr/bin/env python3
"""Recover the publication year of the Springer corpus from its DOI.

Every Springer document in this database is *Eurasian Soil Science* (Pleiades
DOI prefix ``10.1134``), whose article identifiers embed a year:
``10.1134/S1064229 3 13 08 0085`` is volume year 2013, issue 8, article 85.
None of the 3 555 Springer records carried ``publication_year``, which left the
whole translated corpus outside every temporal analysis.

The inference is deliberately two-tier, because the series changed:

``issue_number``      blocks 01–12 are printed issues and the embedded year is
                      the issue year.  Validated against Crossref: 89/89 exact.
``submission_year``   block 60+ is the continuous-submission series, where the
                      embedded year is when the article entered the queue; it
                      appears in that volume or the next one.  Validated
                      against Crossref: 40/72 exact, 32 off by one year, none
                      worse — so it is published as a ±1 year estimate.

``document.publication_year`` is left untouched.  An inferred year lives in its
own relation with its confidence, so no analysis can mistake it for a year
printed on the paper.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

ARTICLE = re.compile(r'S1064229(\d)(\d{2})(\d{2})(\d{3}[\dX])', re.I)

DDL = """
CREATE TABLE IF NOT EXISTS document_publication_year (
  document_id TEXT PRIMARY KEY REFERENCES document(document_id),
  publication_year INTEGER NOT NULL,
  year_confidence TEXT NOT NULL CHECK (year_confidence IN ('printed','issue_number','submission_year')),
  uncertainty_years INTEGER NOT NULL DEFAULT 0,
  method TEXT NOT NULL,
  inferred_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_document_year ON document_publication_year(publication_year);
"""


def decode(identifier: str) -> tuple[int, str, int] | None:
    """Return (year, confidence, uncertainty) for an ESS article identifier."""
    match = ARTICLE.search((identifier or '').replace('_', '/'))
    if not match:
        return None
    two_digit = int(match.group(2))
    block = int(match.group(3))
    year = 2000 + two_digit if two_digit <= 68 else 1900 + two_digit
    if block < 60:
        return year, 'issue_number', 0
    return year, 'submission_year', 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--crossref', type=Path,
                        help='doi_metadata.csv with Crossref years, used to report accuracy')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    stats: Counter[str] = Counter()
    years: Counter[int] = Counter()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        payload = []
        for document_id, doi, printed in con.execute(
            "SELECT document_id, doi, publication_year FROM document"
        ):
            if printed is not None:
                payload.append((document_id, printed, 'printed', 0, 'year present in source catalogue'))
                stats['printed'] += 1
                years[printed] += 1
                continue
            decoded = decode(doi) or decode(document_id)
            if decoded is None:
                stats['unrecoverable'] += 1
                continue
            year, confidence, uncertainty = decoded
            payload.append((document_id, year, confidence, uncertainty,
                            'decoded from Pleiades DOI article identifier'))
            stats[confidence] += 1
            years[year] += 1

        con.executemany("""
            INSERT INTO document_publication_year
              (document_id, publication_year, year_confidence, uncertainty_years, method)
            VALUES (?,?,?,?,?)
            ON CONFLICT(document_id) DO UPDATE SET
              publication_year=excluded.publication_year,
              year_confidence=excluded.year_confidence,
              uncertainty_years=excluded.uncertainty_years,
              method=excluded.method,
              inferred_at=CURRENT_TIMESTAMP
        """, payload)
        con.commit()

    report = {
        'documents_with_year': sum(stats[k] for k in stats if k != 'unrecoverable'),
        'by_confidence': dict(stats),
        'year_range': [min(years), max(years)] if years else None,
        'per_year': {str(year): years[year] for year in sorted(years)},
    }

    if args.crossref and args.crossref.exists():
        checks: Counter[str] = Counter()
        with args.crossref.open(encoding='utf-8') as handle:
            for row in csv.DictReader(handle):
                decoded = decode(row['doi'])
                truth = int(row['publication_year']) if row.get('publication_year') else None
                if decoded is None or truth is None:
                    checks['not_comparable'] += 1
                    continue
                year, confidence, _ = decoded
                delta = abs(year - truth)
                checks[f'{confidence}_{"exact" if delta == 0 else "off_by_one" if delta == 1 else "worse"}'] += 1
        report['crossref_validation'] = dict(checks)

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
