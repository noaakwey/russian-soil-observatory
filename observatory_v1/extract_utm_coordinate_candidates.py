#!/usr/bin/env python3
"""Append high-specificity UTM coordinate candidates from article text.

Unlike the rebuild stage, this never deletes existing coordinate candidates.
It accepts only two unambiguous textual forms: a stated ``UTM coordinate
system`` with a zone/band and northing/easting pair, or a stated UTM zone/band
followed by an explicitly ordered easting/northing pair.  A projection mention
without a pair is deliberately ignored.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from rebuild_strict_coordinate_candidates import utm_to_wgs84

# E.g. ``UTM coordinate system: 37V 5724729 301017``.  The UTM latitude band
# V implies the northern hemisphere; northing appears before easting here.
GRID = re.compile(
    r"\bUTM\s+coordinate\s+system\s*:\s*(?P<zone>\d{1,2})\s*(?P<band>[C-HJ-NP-X])"
    r"\s+(?P<northing>\d{6,8}(?:[.,]\d+)?)\s*[-–—,; ]+\s*(?P<easting>\d{5,7}(?:[.,]\d+)?)\b",
    re.I,
)
# E.g. ``WGS-84, UTM Zone 36-S ... 711376 E, 6234567 N``.  The direction
# letters prevent an arbitrary pair of metre values from being accepted.
EN = re.compile(
    r"\b(?:WGS[- ]?84[ ,;]*)?UTM\s+Zone\s*(?P<zone>\d{1,2})\s*[- ]?(?P<band>[C-HJ-NP-X])?"
    r"[^\n]{0,180}?(?P<easting>\d{5,7}(?:[.,]\d+)?)\s*E\s*[,; ]+"
    r"(?P<northing>\d{6,8}(?:[.,]\d+)?)\s*N\b",
    re.I,
)


def num(value: str) -> float:
    return float(value.replace(',', '.'))


def northern(band: str | None) -> str:
    # All bands N–X (except I/O, excluded by the regex) are north of equator.
    return 'N' if not band or band.upper() >= 'N' else 'S'


def sources(springer: Path, pochvovedenie: Path):
    for path in sorted(springer.glob('*.txt')):
        yield path, f'springer:{path.stem}'
    for path in sorted(pochvovedenie.glob('*.txt')):
        yield path, f'pochvovedenie:{path.stem}'


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--springer-text-dir', type=Path, required=True)
    p.add_argument('--pochvovedenie-text-dir', type=Path, required=True)
    a = p.parse_args()
    stats = {'texts': 0, 'grid_matches': 0, 'en_matches': 0, 'added': 0, 'invalid': 0, 'unknown_document': 0}
    with sqlite3.connect(a.db) as con:
        con.execute('PRAGMA busy_timeout=60000')
        known = {r[0] for r in con.execute('SELECT document_id FROM document')}
        for path, doc_id in sources(a.springer_text_dir, a.pochvovedenie_text_dir):
            if doc_id not in known:
                stats['unknown_document'] += 1; continue
            extraction_id = f'{doc_id}:text:raw'
            if not con.execute('SELECT 1 FROM extraction WHERE extraction_id=?', (extraction_id,)).fetchone():
                continue
            text = path.read_text(encoding='utf-8', errors='replace')
            for kind, pattern in (('grid', GRID), ('en', EN)):
                for index, m in enumerate(pattern.finditer(text)):
                    stats[f'{kind}_matches'] += 1
                    try:
                        zone = int(m['zone']); east, north = num(m['easting']), num(m['northing'])
                        if not 1 <= zone <= 60 or not 100_000 <= east <= 900_000 or not 0 <= north <= 10_000_000:
                            raise ValueError('invalid UTM range')
                        lat, lon = utm_to_wgs84(zone, east, north, northern(m['band']))
                    except (ValueError, TypeError):
                        stats['invalid'] += 1; continue
                    context = text[max(0, m.start() - 240): min(len(text), m.end() + 300)].replace('\n', ' ')
                    cur = con.execute(
                        """INSERT OR IGNORE INTO location_candidate
                           (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                           VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
                        (f'{extraction_id}:utm:{kind}:{index}', extraction_id, lat, lon,
                         f'utm_zone_{zone}{m["band"] or ""}', context),
                    )
                    stats['added'] += int(cur.rowcount > 0)
            stats['texts'] += 1
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
