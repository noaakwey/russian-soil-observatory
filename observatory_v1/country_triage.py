#!/usr/bin/env python3
"""Validate coordinate candidates against a pinned country-boundary GeoJSON.

This program intentionally does *not* create sites.  It only records whether
the reported coordinate lies in Russia, with the exact boundary source and
version used for the decision.  A later review step still has to connect a
coordinate to the reported profile/table and promote it to an operational site.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def point_in_ring(lon: float, lat: float, ring: list[list[float]]) -> bool:
    """Ray-casting test; GeoJSON positions are [longitude, latitude]."""
    inside = False
    x1, y1 = ring[-1]
    for x2, y2 in ring:
        crosses = (y1 > lat) != (y2 > lat)
        if crosses and lon < (x2 - x1) * (lat - y1) / (y2 - y1) + x1:
            inside = not inside
        x1, y1 = x2, y2
    return inside


def polygon_contains(lon: float, lat: float, polygon: list[list[list[float]]]) -> bool:
    return bool(polygon) and point_in_ring(lon, lat, polygon[0]) and not any(
        point_in_ring(lon, lat, hole) for hole in polygon[1:]
    )


def geometry_contains(lon: float, lat: float, geometry: dict) -> bool:
    typ, coordinates = geometry['type'], geometry['coordinates']
    if typ == 'Polygon':
        return polygon_contains(lon, lat, coordinates)
    if typ == 'MultiPolygon':
        return any(polygon_contains(lon, lat, polygon) for polygon in coordinates)
    raise ValueError(f'Unsupported geometry type: {typ}')


def feature_code(feature: dict) -> str | None:
    p = feature.get('properties', {})
    return p.get('ISO_A2') or p.get('iso_a2') or p.get('ISO_A3') or p.get('iso_a3')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--boundaries', type=Path, required=True)
    parser.add_argument('--dataset', default='Natural Earth Admin 0 Countries')
    parser.add_argument('--version', required=True)
    args = parser.parse_args()
    features = json.loads(args.boundaries.read_text(encoding='utf-8'))['features']
    # Keep only features with a usable ISO country code; nearby territories then
    # remain unresolved rather than being silently classified as Russian.
    countries = [(feature_code(f), f['geometry']) for f in features if feature_code(f)]
    stats = {'checked': 0, 'russia': 0, 'other_country': 0, 'unresolved': 0}
    with sqlite3.connect(args.db) as con:
        con.execute('PRAGMA foreign_keys=ON')
        con.execute('PRAGMA busy_timeout=60000')
        rows = con.execute('SELECT candidate_id, latitude, longitude FROM location_candidate').fetchall()
        for candidate_id, lat, lon in rows:
            matches = [code for code, geometry in countries if geometry_contains(lon, lat, geometry)]
            # ISO_A2 may be absent for Russia in some Natural Earth revisions;
            # ISO_A3 is then RUS, which we normalize to the database code RU.
            code = matches[0] if len(matches) == 1 else None
            if code == 'RUS':
                code = 'RU'
            result = 'inside' if code else ('border_ambiguous' if matches else 'unresolved')
            if result == 'inside':
                stats['russia' if code == 'RU' else 'other_country'] += 1
            else:
                stats['unresolved'] += 1
            con.execute(
                '''INSERT INTO location_validation
                   (candidate_id,validator,boundary_dataset,boundary_version,country_code,result,details_json)
                   VALUES(?,?,?,?,?,?,?)
                   ON CONFLICT(candidate_id) DO UPDATE SET
                     validator=excluded.validator,boundary_dataset=excluded.boundary_dataset,
                     boundary_version=excluded.boundary_version,country_code=excluded.country_code,
                     result=excluded.result,details_json=excluded.details_json,validated_at=CURRENT_TIMESTAMP''',
                (candidate_id, 'country_triage.py', args.dataset, args.version, code, result,
                 json.dumps({'matches': matches}, ensure_ascii=False)),
            )
            con.execute('UPDATE location_candidate SET country_candidate=? WHERE candidate_id=?', (code, candidate_id))
            stats['checked'] += 1
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
