#!/usr/bin/env python3
"""Append decimal coordinate pairs only after an explicit coordinate marker.

Many papers write ``coordinates: 52.12345, 37.54321`` without cardinal
letters.  A naked decimal pair is deliberately rejected; the marker is what
makes this a textual coordinate claim rather than a table value.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


PAIR = re.compile(
    r"(?:coordinates?|coord\.?|координат\w*)\s*[:=–—-]?\s*(?:lat(?:itude)?\s*)?"
    r"(?P<lat>[+-]?\d{1,2}[.,]\d{3,8})\s*°?\s*(?:[NSСЮ])?\s*[,;/]\s*"
    r"(?:lon(?:gitude)?\s*)?(?P<lon>[+-]?\d{2,3}[.,]\d{3,8})\s*°?\s*(?:[EWВЗ])?",
    re.I,
)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    a = p.parse_args()
    stats = {'artifacts': 0, 'matches': 0, 'added': 0, 'invalid': 0}
    with sqlite3.connect(a.db) as con:
        con.execute('PRAGMA busy_timeout=60000')
        for extraction_id, raw in con.execute("""
            SELECT e.extraction_id,e.raw_text FROM extraction e
            JOIN source_artifact a ON a.artifact_id=e.artifact_id
            WHERE a.artifact_type='text' AND e.raw_text IS NOT NULL
        """):
            stats['artifacts'] += 1
            for index, m in enumerate(PAIR.finditer(raw)):
                stats['matches'] += 1
                try:
                    lat, lon = float(m['lat'].replace(',', '.')), float(m['lon'].replace(',', '.'))
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError
                except ValueError:
                    stats['invalid'] += 1
                    continue
                context = raw[max(0, m.start()-280):min(len(raw), m.end()+380)].replace('\n', ' ')
                cur = con.execute("""INSERT OR IGNORE INTO location_candidate
                    (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                    VALUES(?,?,?,?,NULL,NULL,'explicit_decimal_coordinate_marker',?,'unreviewed')""",
                    (f'{extraction_id}:explicit_decimal_marker:{index}', extraction_id, lat, lon, context))
                stats['added'] += int(cur.rowcount > 0)
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
