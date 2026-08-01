#!/usr/bin/env python3
"""Extract precise DMS coordinates from article full text.

Some translated articles include explicit coordinates in Methods sections:
"The experiment was carried out at 66°25'N, 67°18'E, Republic of Komi".

These are far more precise than regional centroids and should override region-
level attribution when present.  The extraction is greedy: any DMS pair found
in the Methods section is linked to the document, even if it appears only once
(since a Methods section is unlikely to repeat coordinates).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS document_precise_coordinate (
  document_id TEXT NOT NULL PRIMARY KEY REFERENCES document(document_id),
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  source TEXT NOT NULL,
  confidence TEXT NOT NULL CHECK (confidence IN ('extracted','single_pair')),
  method TEXT NOT NULL
);
"""

# Patterns for DMS coordinates.
# Latitude: 00-90 degrees, 0-59 minutes, optional seconds.
# Longitude: 000-180 degrees, 0-59 minutes, optional seconds.
# Direction: N/S for lat, E/W for lon (Russian и английские буквы).

PATTERNS = [
    # DMS with prime/minute marks and compass direction: 66°25'N or 66° 25' N
    re.compile(
        r'(\d{1,2})\s*[°º]\s*(\d{1,2})\s*[′\']'
        r'(?:\s*(\d{1,2})\s*[″"]\s*)?'
        r'([NSns])',
        re.ASCII),
    # Russian format: 66°25' с.ш. or 66° 25' северной широты
    re.compile(
        r'(\d{1,2})\s*[°º]\s*(\d{1,2})\s*[′\']'
        r'(?:\s*(\d{1,2})\s*[″"]\s*)?'
        r'(?:\s*(?:с\.ш\.|северной|с\.широты))',
        re.IGNORECASE),
    # Longitude: 067°18'E or with Russian suffix
    re.compile(
        r'(\d{1,3})\s*[°º]\s*(\d{1,2})\s*[′\']'
        r'(?:\s*(\d{1,2})\s*[″"]\s*)?'
        r'([EWew])',
        re.ASCII),
    re.compile(
        r'(\d{1,3})\s*[°º]\s*(\d{1,2})\s*[′\']'
        r'(?:\s*(\d{1,2})\s*[″"]\s*)?'
        r'(?:\s*(?:в\.д\.|восточной|в\.долготы))',
        re.IGNORECASE),
]

METHODS_WINDOW = 40000
HEADER_SKIP = 1200


def dms_to_decimal(degrees: int, minutes: int, seconds: float = 0) -> float:
    """Convert DMS to decimal degrees."""
    return degrees + minutes / 60.0 + seconds / 3600.0


def extract_coordinates(text: str) -> list[tuple[float, float, str]]:
    """Find all DMS coordinate pairs in Methods section."""
    body = text[HEADER_SKIP:METHODS_WINDOW]
    coords = []

    # Find all latitude matches.
    lats = {}
    for match in re.finditer(
        r'(\d{1,2})\s*[°º]\s*(\d{1,2})\s*[′\']'
        r'(?:\s*(\d{1,2})\s*[″"]\s*)?'
        r'\s*([NSns])',
        body,
    ):
        deg, minutes, seconds, direction = (
            int(match.group(1)),
            int(match.group(2)),
            float(match.group(3) or 0),
            match.group(4).upper(),
        )
        if deg > 90 or minutes > 59 or seconds > 59:
            continue
        value = dms_to_decimal(deg, minutes, seconds)
        if direction == 'S':
            value = -value
        lats[match.start()] = value

    # Find all longitude matches.
    lons = {}
    for match in re.finditer(
        r'(\d{1,3})\s*[°º]\s*(\d{1,2})\s*[′\']'
        r'(?:\s*(\d{1,2})\s*[″"]\s*)?'
        r'\s*([EWew])',
        body,
    ):
        deg, minutes, seconds, direction = (
            int(match.group(1)),
            int(match.group(2)),
            float(match.group(3) or 0),
            match.group(4).upper(),
        )
        if deg > 180 or minutes > 59 or seconds > 59:
            continue
        value = dms_to_decimal(deg, minutes, seconds)
        if direction == 'W':
            value = -value
        lons[match.start()] = value

    # Pair nearby coordinates: latitude should precede longitude within ~200 chars.
    paired = []
    for lat_pos, lat_val in sorted(lats.items()):
        for lon_pos, lon_val in sorted(lons.items()):
            if lat_pos < lon_pos < lat_pos + 200:
                paired.append((lat_val, lon_val, f'DMS pair at char {lat_pos}'))
                break
    return paired


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    stats: Counter = Counter()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        con.execute('DELETE FROM document_precise_coordinate')

        documents = con.execute("""
            SELECT a.document_id, e.raw_text
            FROM source_artifact a
            JOIN extraction e ON e.artifact_id = a.artifact_id
            WHERE a.artifact_type = 'text' AND e.raw_text IS NOT NULL
        """).fetchall()

        payload = []
        for document_id, text in documents:
            coords = extract_coordinates(text)
            if coords:
                stats['documents_with_coords'] += 1
                # Take the first pair as primary.
                lat, lon, source = coords[0]
                payload.append(
                    (document_id, lat, lon, source, 'extracted',
                     'DMS pair from Methods section of full text')
                )
                stats['coordinate_pairs'] += len(coords)

        con.executemany("""
            INSERT INTO document_precise_coordinate
              (document_id, latitude, longitude, source, confidence, method)
            VALUES (?,?,?,?,?,?)
        """, payload)
        con.commit()

        total = con.execute('SELECT COUNT(*) FROM table_observation').fetchone()[0]
        covered = con.execute("""
            SELECT COUNT(*) FROM table_observation
            WHERE document_id IN (SELECT document_id FROM document_precise_coordinate)
        """).fetchone()[0]

    report = {
        'documents': dict(stats),
        'observations_with_precise_coords': covered,
        'observations_total': total,
        'coverage_pct': round(100 * covered / total, 1) if total else 0,
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
