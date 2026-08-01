#!/usr/bin/env python3
"""Build every published artefact of the Russian Soil Observatory geoportal.

Everything the site serves is derived here, in one pass, straight from the
working SQLite database:

``data/observatory.sqlite``      a trimmed, denormalized database the browser
                                 queries with sql.js — the whole observation
                                 layer, no server.
``data/portal_map.json``         author-reported coordinates with their source
                                 evidence and strictly linked measurements.
``data/aggregates.json``         every number the report and the charts quote.
``data/full_table_observations.csv``  the complete layer with quality flags.

The build never invents a value.  Unit, coordinate and property confidence
travel with each row so a pedologist can filter on them.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
from collections import Counter, defaultdict
from pathlib import Path

EARTH_RADIUS_KM = 6371.0
RUSSIA_AREA_KM2 = 17_098_246


def haversine(first: tuple[float, float], second: tuple[float, float]) -> float:
    lat1, lon1 = math.radians(first[0]), math.radians(first[1])
    lat2, lon2 = math.radians(second[0]), math.radians(second[1])
    inner = (math.sin((lat2 - lat1) / 2) ** 2
             + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2)
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(inner))


def percentile(ordered: list[float], fraction: float) -> float:
    if not ordered:
        return float('nan')
    return ordered[int(fraction * (len(ordered) - 1))]


def load_property_names(path: Path) -> dict[str, dict[str, str]]:
    if not path.exists():
        return {}
    with path.open(encoding='utf-8') as handle:
        return {
            row['property_id']: {
                'ru': row['property_russian'],
                'category_ru': row['category_russian'],
            }
            for row in csv.DictReader(handle)
        }


# --------------------------------------------------------------------------
# Browser database
# --------------------------------------------------------------------------

BROWSER_SCHEMA = """
CREATE TABLE observation (
  observation_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL,
  corpus TEXT NOT NULL,
  doi TEXT,
  publication_year INTEGER,
  year_confidence TEXT,
  property_id TEXT NOT NULL,
  property TEXT NOT NULL,
  property_ru TEXT,
  category TEXT NOT NULL,
  category_ru TEXT,
  property_header_raw TEXT NOT NULL,
  value_raw REAL,
  unit_raw TEXT,
  value_normalized REAL,
  unit_normalized TEXT,
  normalization_status TEXT NOT NULL,
  header_match_kind TEXT NOT NULL,
  value_plausibility TEXT NOT NULL,
  spatial_linkage TEXT NOT NULL,
  row_label_raw TEXT,
  horizon_label_raw TEXT,
  depth_top_cm REAL,
  depth_bottom_cm REAL,
  context_latitude REAL,
  context_longitude REAL,
  page_start INTEGER,
  table_label TEXT
);
CREATE INDEX idx_obs_property ON observation(property_id);
CREATE INDEX idx_obs_category ON observation(category);
CREATE INDEX idx_obs_year ON observation(publication_year);
CREATE INDEX idx_obs_quality ON observation(header_match_kind, value_plausibility);
CREATE INDEX idx_obs_spatial ON observation(spatial_linkage);

CREATE TABLE reported_site (
  site_id TEXT PRIMARY KEY,
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  region TEXT,
  spatial_confidence TEXT NOT NULL,
  document_id TEXT,
  corpus TEXT,
  publication_year INTEGER
);
CREATE INDEX idx_site_xy ON reported_site(latitude, longitude);

CREATE TABLE verified_measurement (
  measurement_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL,
  latitude REAL,
  longitude REAL,
  property TEXT NOT NULL,
  property_ru TEXT,
  value_num REAL,
  unit_normalized TEXT,
  unit_raw TEXT,
  qa_status TEXT NOT NULL,
  document_id TEXT,
  doi TEXT
);

CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
"""

OBSERVATION_QUERY = """
SELECT o.observation_id, o.document_id, d.corpus, d.doi,
       y.publication_year, y.year_confidence,
       o.property_id, p.canonical_name, p.category,
       o.property_header_raw, o.value_num_raw, o.unit_raw,
       o.value_normalized, o.unit_normalized, o.normalization_status,
       f.header_match_kind, f.value_plausibility,
       o.spatial_linkage, o.row_label_raw, o.horizon_label_raw,
       o.depth_top_cm, o.depth_bottom_cm,
       s.latitude, s.longitude, a.page_start, a.table_label
FROM table_observation o
JOIN document d ON d.document_id = o.document_id
JOIN property_definition p ON p.property_id = o.property_id
JOIN observation_quality_flag f ON f.observation_id = o.observation_id
JOIN source_artifact a ON a.artifact_id = o.artifact_id
LEFT JOIN document_publication_year y ON y.document_id = o.document_id
LEFT JOIN site s ON s.site_id = o.context_site_id
"""


def build_browser_database(source: sqlite3.Connection, target_path: Path,
                           names: dict[str, dict[str, str]], generated_at: str) -> int:
    if target_path.exists():
        target_path.unlink()
    target = sqlite3.connect(target_path)
    target.executescript(BROWSER_SCHEMA)

    rows = []
    for row in source.execute(OBSERVATION_QUERY):
        (observation_id, document_id, corpus, doi, year, year_confidence,
         property_id, canonical, category, header, value_raw, unit_raw,
         value_normalized, unit_normalized, status, header_kind, plausibility,
         spatial, row_label, horizon, depth_top, depth_bottom,
         latitude, longitude, page_start, table_label) = row
        localized = names.get(property_id, {})
        rows.append((
            observation_id, document_id, corpus, doi, year, year_confidence,
            property_id, canonical, localized.get('ru'), category,
            localized.get('category_ru'), header, value_raw, unit_raw,
            value_normalized, unit_normalized, status, header_kind, plausibility,
            spatial, row_label, horizon, depth_top, depth_bottom,
            latitude, longitude, page_start, table_label,
        ))
    target.executemany(
        f"INSERT INTO observation VALUES({','.join('?' * 28)})", rows)

    target.executemany(
        "INSERT INTO reported_site VALUES(?,?,?,?,?,?,?,?)",
        source.execute("""
            SELECT s.site_id, s.latitude, s.longitude, s.region, s.spatial_confidence,
                   MIN(a.document_id), MIN(d.corpus), MIN(y.publication_year)
            FROM site s
            LEFT JOIN site_evidence se ON se.site_id = s.site_id
            LEFT JOIN source_artifact a ON a.artifact_id = se.artifact_id
            LEFT JOIN document d ON d.document_id = a.document_id
            LEFT JOIN document_publication_year y ON y.document_id = a.document_id
            WHERE s.latitude IS NOT NULL AND s.spatial_confidence IN ('exact','reported')
            GROUP BY s.site_id
        """).fetchall())

    target.executemany(
        "INSERT INTO verified_measurement VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
        [(mid, sid, lat, lon, canonical, names.get(pid, {}).get('ru'),
          value, unit_norm, unit_raw, qa, document_id, doi)
         for mid, sid, lat, lon, pid, canonical, value, unit_norm, unit_raw, qa, document_id, doi
         in source.execute("""
            SELECT m.measurement_id, m.site_id, s.latitude, s.longitude,
                   m.property_id, p.canonical_name, m.value_num,
                   m.unit_normalized, m.unit_raw, m.qa_status,
                   a.document_id, d.doi
            FROM measurement m
            JOIN site s ON s.site_id = m.site_id
            JOIN property_definition p ON p.property_id = m.property_id
            LEFT JOIN source_artifact a ON a.artifact_id = m.evidence_artifact_id
            LEFT JOIN document d ON d.document_id = a.document_id
         """)])

    target.executemany("INSERT INTO meta VALUES(?,?)", [
        ('generated_at', generated_at),
        ('observations', str(len(rows))),
        ('license', 'CC BY 4.0 for the compiled database; source articles remain under their own rights'),
        ('note', 'Values are OCR-derived. Filter header_match_kind and value_plausibility before analysis.'),
    ])
    target.commit()
    target.execute('VACUUM')
    target.close()
    return len(rows)


# --------------------------------------------------------------------------
# Map payload
# --------------------------------------------------------------------------

def build_map(source: sqlite3.Connection) -> dict:
    sites: dict[tuple[float, float], dict] = {}
    for site_id, latitude, longitude, region, corpus, doi, year, confidence, evidence in source.execute("""
        SELECT s.site_id, s.latitude, s.longitude, s.region,
               MIN(d.corpus), MIN(d.doi), MIN(y.publication_year), MIN(y.year_confidence),
               MIN(se.evidence_text)
        FROM site s
        LEFT JOIN site_evidence se ON se.site_id = s.site_id
        LEFT JOIN source_artifact a ON a.artifact_id = se.artifact_id
        LEFT JOIN document d ON d.document_id = a.document_id
        LEFT JOIN document_publication_year y ON y.document_id = a.document_id
        WHERE s.latitude IS NOT NULL AND s.spatial_confidence IN ('exact','reported')
        GROUP BY s.site_id
    """):
        key = (round(latitude, 5), round(longitude, 5))
        entry = sites.setdefault(key, {
            'lat': key[0], 'lon': key[1], 'records': 0,
            'sources': [], 'measurements': [],
        })
        entry['records'] += 1
        if len(entry['sources']) < 6:
            entry['sources'].append({
                'corpus': corpus, 'doi': doi, 'year': year,
                'year_confidence': confidence, 'region': region,
                'evidence': (evidence or '')[:420],
            })

    for latitude, longitude, canonical, value, unit, qa, doi in source.execute("""
        SELECT s.latitude, s.longitude, p.canonical_name, m.value_num,
               COALESCE(m.unit_normalized, m.unit_raw), m.qa_status, d.doi
        FROM measurement m
        JOIN site s ON s.site_id = m.site_id
        JOIN property_definition p ON p.property_id = m.property_id
        LEFT JOIN source_artifact a ON a.artifact_id = m.evidence_artifact_id
        LEFT JOIN document d ON d.document_id = a.document_id
        WHERE s.latitude IS NOT NULL
    """):
        key = (round(latitude, 5), round(longitude, 5))
        if key in sites and len(sites[key]['measurements']) < 60:
            sites[key]['measurements'].append({
                'property': canonical, 'value': value, 'unit': unit,
                'qa': qa, 'doi': doi,
            })

    points = sorted(sites.values(), key=lambda item: (-len(item['measurements']), -item['records']))
    return {'points': points}


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------

def build_aggregates(source: sqlite3.Connection, names: dict[str, dict[str, str]]) -> dict:
    def rows(sql: str) -> list[tuple]:
        return source.execute(sql).fetchall()

    corpus = dict(rows("SELECT corpus, COUNT(*) FROM document GROUP BY 1"))
    total_observations = rows("SELECT COUNT(*) FROM table_observation")[0][0]

    properties = []
    for pid, canonical, category, count, normalized, clean, plausible, docs in rows("""
        SELECT o.property_id, p.canonical_name, p.category, COUNT(*),
               SUM(o.normalization_status IN ('exact','converted')),
               SUM(f.header_match_kind <> 'symbol_embedded'),
               SUM(f.value_plausibility = 'ok'),
               COUNT(DISTINCT o.document_id)
        FROM table_observation o
        JOIN property_definition p ON p.property_id = o.property_id
        JOIN observation_quality_flag f ON f.observation_id = o.observation_id
        GROUP BY 1,2,3 ORDER BY 4 DESC
    """):
        localized = names.get(pid, {})
        properties.append({
            'property_id': pid, 'property': canonical,
            'property_ru': localized.get('ru'),
            'category': category, 'category_ru': localized.get('category_ru'),
            'observations': count, 'normalized': normalized,
            'header_trusted': clean, 'value_plausible': plausible,
            'documents': docs,
        })

    per_year = [
        {'year': year, 'observations': observations, 'documents': documents}
        for year, observations, documents in rows("""
            SELECT y.publication_year, COUNT(*), COUNT(DISTINCT o.document_id)
            FROM table_observation o
            JOIN document_publication_year y ON y.document_id = o.document_id
            GROUP BY 1 ORDER BY 1
        """)
    ]

    documents_per_year = [
        {'year': year, 'pochvovedenie': russian, 'springer': springer}
        for year, russian, springer in rows("""
            SELECT y.publication_year,
                   SUM(d.corpus='pochvovedenie'), SUM(d.corpus='springer')
            FROM document d JOIN document_publication_year y USING(document_id)
            GROUP BY 1 ORDER BY 1
        """)
    ]

    points = rows("""SELECT DISTINCT ROUND(latitude,5), ROUND(longitude,5) FROM site
                     WHERE latitude IS NOT NULL AND spatial_confidence IN ('exact','reported')""")
    neighbours = sorted(
        min(haversine(point, other) for index, other in enumerate(points) if index != position)
        for position, point in enumerate(points)
    ) if len(points) > 1 else []
    expected = 0.5 / math.sqrt(len(points) / RUSSIA_AREA_KM2) if points else 0.0

    cells = Counter((int(math.floor(lat / 5)) * 5, int(math.floor(lon / 5)) * 5)
                    for lat, lon in points)

    spatial = {
        'unique_positions': len(points),
        'coordinate_records': rows("""SELECT COUNT(*) FROM site
             WHERE latitude IS NOT NULL AND spatial_confidence IN ('exact','reported')""")[0][0],
        'nearest_neighbour_km': {
            'median': round(percentile(neighbours, 0.5), 2),
            'p25': round(percentile(neighbours, 0.25), 2),
            'p75': round(percentile(neighbours, 0.75), 2),
            'mean': round(statistics.mean(neighbours), 2) if neighbours else None,
        },
        'share_within_1km': round(100 * sum(1 for d in neighbours if d < 1) / len(neighbours), 1) if neighbours else None,
        'clark_evans_ratio': round(statistics.mean(neighbours) / expected, 3) if neighbours and expected else None,
        'occupied_5deg_cells': len(cells),
        'european_share_pct': round(100 * sum(1 for _, lon in points if lon < 60) / len(points), 1) if points else None,
        'cells': [{'lat': lat, 'lon': lon, 'n': n} for (lat, lon), n in sorted(cells.items())],
    }

    quality = {
        'header_match_kind': dict(rows(
            "SELECT header_match_kind, COUNT(*) FROM observation_quality_flag GROUP BY 1")),
        'value_plausibility': dict(rows(
            "SELECT value_plausibility, COUNT(*) FROM observation_quality_flag GROUP BY 1")),
        'normalization_status': dict(rows(
            "SELECT normalization_status, COUNT(*) FROM table_observation GROUP BY 1")),
        'spatial_linkage': dict(rows(
            "SELECT spatial_linkage, COUNT(*) FROM table_observation GROUP BY 1")),
        'analysis_ready': rows("""
            SELECT COUNT(*) FROM table_observation o
            JOIN observation_quality_flag f ON f.observation_id = o.observation_id
            WHERE f.header_match_kind <> 'symbol_embedded' AND f.value_plausibility = 'ok'
              AND o.normalization_status IN ('exact','converted')""")[0][0],
        'unflagged': rows("""
            SELECT COUNT(*) FROM observation_quality_flag
            WHERE header_match_kind <> 'symbol_embedded' AND value_plausibility = 'ok'""")[0][0],
    }

    depth = {
        'with_depth': rows("SELECT COUNT(*) FROM table_observation WHERE depth_top_cm IS NOT NULL")[0][0],
        'profiles': rows("""SELECT COUNT(*) FROM (
              SELECT document_id, row_label_raw FROM table_observation
              WHERE depth_top_cm IS NOT NULL GROUP BY 1,2)""")[0][0],
    }

    return {
        'documents': {'total': sum(corpus.values()), **corpus},
        'observations': total_observations,
        'artifacts': rows("SELECT COUNT(*) FROM source_artifact")[0][0],
        'ocr_tables': rows("SELECT COUNT(DISTINCT artifact_id) FROM table_cell")[0][0],
        'properties': properties,
        'categories': [
            {'category': category, 'observations': count, 'properties': props}
            for category, props, count in rows("""
                SELECT p.category, COUNT(DISTINCT p.property_id), COUNT(*)
                FROM table_observation o JOIN property_definition p ON p.property_id=o.property_id
                GROUP BY 1 ORDER BY 3 DESC""")
        ],
        'per_year': per_year,
        'documents_per_year': documents_per_year,
        'year_confidence': dict(rows(
            "SELECT year_confidence, COUNT(*) FROM document_publication_year GROUP BY 1")),
        'spatial': spatial,
        'quality': quality,
        'depth': depth,
        'strict_layer': {
            'measurements': rows("SELECT COUNT(*) FROM measurement")[0][0],
            'sites': rows("SELECT COUNT(DISTINCT site_id) FROM measurement")[0][0],
        },
    }


# --------------------------------------------------------------------------
# CSV export
# --------------------------------------------------------------------------

CSV_COLUMNS = [
    'observation_id', 'candidate_id', 'document_id', 'corpus', 'doi',
    'publication_year', 'year_confidence', 'property', 'property_ru', 'category',
    'property_header_raw', 'value_num_raw', 'unit_raw', 'value_normalized',
    'unit_normalized', 'normalization_status', 'header_match_kind',
    'value_plausibility', 'plausibility_rule', 'qa_status', 'spatial_linkage',
    'context_latitude', 'context_longitude', 'row_label_raw', 'horizon_label_raw',
    'depth_top_cm', 'depth_bottom_cm', 'page_start', 'table_label', 'evidence_locator',
]


def export_csv(source: sqlite3.Connection, path: Path, names: dict[str, dict[str, str]]) -> int:
    written = 0
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in source.execute("""
            SELECT o.observation_id, o.candidate_id, o.document_id, d.corpus, d.doi,
                   y.publication_year, y.year_confidence, p.canonical_name, o.property_id,
                   p.category, o.property_header_raw, o.value_num_raw, o.unit_raw,
                   o.value_normalized, o.unit_normalized, o.normalization_status,
                   f.header_match_kind, f.value_plausibility, f.plausibility_rule,
                   o.qa_status, o.spatial_linkage, s.latitude, s.longitude,
                   o.row_label_raw, o.horizon_label_raw, o.depth_top_cm, o.depth_bottom_cm,
                   a.page_start, a.table_label, o.evidence_locator
            FROM table_observation o
            JOIN document d ON d.document_id = o.document_id
            JOIN property_definition p ON p.property_id = o.property_id
            JOIN observation_quality_flag f ON f.observation_id = o.observation_id
            JOIN source_artifact a ON a.artifact_id = o.artifact_id
            LEFT JOIN document_publication_year y ON y.document_id = o.document_id
            LEFT JOIN site s ON s.site_id = o.context_site_id
            ORDER BY o.observation_id
        """):
            values = list(row)
            property_id = values.pop(8)
            values.insert(8, names.get(property_id, {}).get('ru'))
            writer.writerow(values)
            written += 1
    return written


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('docs/data'))
    parser.add_argument('--dictionary', type=Path,
                        default=Path('docs/data/property_dictionary_ru_public.csv'))
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    names = load_property_names(args.dictionary)
    source = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
    generated_at = source.execute("SELECT datetime('now')").fetchone()[0]

    aggregates = build_aggregates(source, names)
    aggregates['generated_at'] = generated_at
    (args.output / 'aggregates.json').write_text(
        json.dumps(aggregates, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    payload = build_map(source)
    payload['generated_at'] = generated_at
    (args.output / 'portal_map.json').write_text(
        json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    observations = build_browser_database(source, args.output / 'observatory.sqlite',
                                          names, generated_at)
    exported = export_csv(source, args.output / 'full_table_observations.csv', names)
    source.close()

    print(json.dumps({
        'generated_at': generated_at,
        'browser_database_rows': observations,
        'csv_rows': exported,
        'map_points': len(payload['points']),
        'aggregate_properties': len(aggregates['properties']),
        'sizes_mb': {
            path.name: round(path.stat().st_size / 1024 / 1024, 2)
            for path in sorted(args.output.glob('*'))
            if path.name in {'observatory.sqlite', 'portal_map.json',
                             'aggregates.json', 'full_table_observations.csv'}
        },
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
