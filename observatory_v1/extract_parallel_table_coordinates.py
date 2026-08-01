#!/usr/bin/env python3
"""Stage explicitly parallel latitude/longitude lists from source-text tables.

Some Springer XML/PDF text preserves a table as ``Coordinates: N lat_1 ...
N lat_n; E lon_1 ... E lon_n``.  Values are paired only by identical ordinal
position after one literal Coordinates heading.  Unequal lists, lone values
and arbitrary prose are rejected rather than guessing a pairing.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path


HEADING = re.compile(r"\bcoordinates?\b(?P<body>.{0,1800})", re.I | re.S)
LAT = re.compile(r"\bN\s*(?P<value>\d{1,2}[.,]\d{4,8})\b", re.I)
LON = re.compile(r"\bE\s*(?P<value>\d{2,3}[.,]\d{4,8})\b", re.I)


def ident(extraction_id: str, latitude: float, longitude: float, ordinal: int) -> str:
    raw = f"{extraction_id}|{latitude:.8f}|{longitude:.8f}|{ordinal}"
    return f"{extraction_id}:parallel_table:{hashlib.sha1(raw.encode()).hexdigest()[:16]}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    stats = {'artifacts': 0, 'headings': 0, 'accepted_lists': 0, 'candidates': 0, 'rejected_lists': 0, 'added': 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        documents = {row[0] for row in con.execute('SELECT document_id FROM document')}
        source_rows = con.execute("""SELECT e.extraction_id,e.raw_text,a.artifact_id,d.document_id,d.corpus
              FROM extraction e JOIN source_artifact a ON a.artifact_id=e.artifact_id
              JOIN document d ON d.document_id=a.document_id
             WHERE a.artifact_type='text' AND e.raw_text IS NOT NULL""")
        for source in source_rows:
            stats['artifacts'] += 1
            text = source['raw_text']
            for heading in HEADING.finditer(text):
                stats['headings'] += 1
                body = heading.group('body')
                lats = [float(match['value'].replace(',', '.')) for match in LAT.finditer(body)]
                lons = [float(match['value'].replace(',', '.')) for match in LON.finditer(body)]
                if not (2 <= len(lats) <= 12 and len(lats) == len(lons)):
                    stats['rejected_lists'] += 1
                    continue
                if any(not (-90 <= lat <= 90 and -180 <= lon <= 180) for lat, lon in zip(lats, lons)):
                    stats['rejected_lists'] += 1
                    continue
                # The matching heading must be table-like; otherwise an
                # arbitrary prose enumeration could look like a list.
                # Require a multi-column table cue.  ``soil pit`` in prose is
                # not enough: two independent prose coordinates must never be
                # mistaken for ordinal table columns.
                if not re.search(r"(?:forest\s*type|\bregion\b|\bdistrict\b|"
                                 r"\bage\b|soil\s*\[\d+\]|\btable\s*\d+\b)", body, re.I):
                    stats['rejected_lists'] += 1
                    continue
                stats['accepted_lists'] += 1
                for ordinal, (lat, lon) in enumerate(zip(lats, lons), start=1):
                    candidate_id = ident(source['extraction_id'], lat, lon, ordinal)
                    context = text[max(0, heading.start() - 420): min(len(text), heading.end() + 240)].replace('\n', ' ')
                    rows.append({'candidate_id': candidate_id, 'document_id': source['document_id'],
                                 'corpus': source['corpus'], 'artifact_id': source['artifact_id'],
                                 'latitude': lat, 'longitude': lon, 'ordinal': ordinal,
                                 'context_text': context})
                    if args.apply:
                        cur = con.execute("""INSERT OR IGNORE INTO location_candidate
                            (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                            VALUES(?,?,?,?,NULL,NULL,'parallel_table_coordinates',?,'unreviewed')""",
                            (candidate_id, source['extraction_id'], lat, lon, context))
                        stats['added'] += int(cur.rowcount > 0)
                    stats['candidates'] += 1
        if args.apply:
            con.commit()
    with args.output.open('w', encoding='utf-8', newline='') as handle:
        fields = ['candidate_id','document_id','corpus','artifact_id','latitude','longitude','ordinal','context_text']
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
