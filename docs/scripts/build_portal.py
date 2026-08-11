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
``data/full_table_observations.csv``  the clean table layer with quality flags;
                                 rejected raw candidates remain in the source
                                 database and review queue, not in public data.

The build never invents a value.  Unit, coordinate and property confidence
travel with each row so a pedologist can filter on them.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sqlite3
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from property_dictionary_ru import CATEGORY_EN, CATEGORY_RU, merged_category

EARTH_RADIUS_KM = 6371.0
RUSSIA_AREA_KM2 = 17_098_246
# site.country_code is a label, not a geographic filter — some rows are
# foreign case-study/comparison sites an author cites in an otherwise
# Russian study. Match the bounding box build_insight_analysis.py uses so
# the portal's own spatial stats (Clark-Evans, nearest neighbour, cells)
# describe the domestic record, not a mix of it and foreign context points.
RUSSIA_BOUNDS = dict(lat=(41.0, 82.0), lon=(19.0, 190.0))

# Legacy rows carry absolute extraction paths from a machine that no longer
# exists.  The file name is the useful part of that provenance; the host
# directory is noise in a public release, so it is dropped on export.
LEGACY_PATH = re.compile(r'/(?:home/linux|Users/[^/\s"]+|Volumes/[^/\s"]+)/(?:[^/\s"]+/)*')


def strip_host_paths(value):
    """Reduce an absolute extraction path to its file name."""
    if isinstance(value, str) and '/' in value:
        return LEGACY_PATH.sub('', value)
    return value


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
  spatial_tier TEXT,
  trusted INTEGER NOT NULL,
  metric INTEGER NOT NULL,
  page_start INTEGER,
  table_label TEXT
);
CREATE INDEX idx_obs_property ON observation(property_id);
CREATE INDEX idx_obs_category ON observation(category);
CREATE INDEX idx_obs_year ON observation(publication_year);
CREATE INDEX idx_obs_quality ON observation(header_match_kind, value_plausibility);
CREATE INDEX idx_obs_spatial ON observation(spatial_linkage);
CREATE INDEX idx_obs_property_chart ON observation(property_id, trusted, metric);
CREATE INDEX idx_obs_depth ON observation(property_id, depth_top_cm);
CREATE INDEX idx_obs_geo ON observation(property_id, context_latitude);

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
       COALESCE(y.publication_year, d.publication_year), y.year_confidence,
       o.property_id, p.canonical_name, p.category,
       o.property_header_raw, o.value_num_raw, o.unit_raw,
       o.value_normalized, o.unit_normalized, o.normalization_status,
       f.header_match_kind, f.value_plausibility,
       o.spatial_linkage, o.row_label_raw, o.horizon_label_raw,
       o.depth_top_cm, o.depth_bottom_cm,
       t.latitude, t.longitude, t.tier, a.page_start, a.table_label,
       u.confidence AS unit_confidence
FROM table_observation o
JOIN document d ON d.document_id = o.document_id
JOIN property_definition p ON p.property_id = o.property_id
JOIN observation_quality_flag f ON f.observation_id = o.observation_id
JOIN source_artifact a ON a.artifact_id = o.artifact_id
LEFT JOIN document_publication_year y ON y.document_id = o.document_id
LEFT JOIN document_spatial_tier t ON t.document_id = o.document_id
LEFT JOIN observation_unit_inference u ON u.observation_id = o.observation_id
WHERE o.property_id <> 'unclassified_table_metric'
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
         latitude, longitude, tier, page_start, table_label, unit_confidence) = row
        category = merged_category(category)
        localized = names.get(property_id, {})
        trusted = int(header_kind != 'symbol_embedded' and plausibility == 'ok')
        # 2026-08 rebuild: table_observation is admission-gated (three-agent
        # verified provenance, unit required before a row is accepted), so
        # normalization_status is 'exact'/'converted' for every row and the
        # old post-hoc observation_unit_inference confidence tier is empty.
        # "Proven unit" is the admission criterion itself, not a per-row flag.
        metric = int(status in ('exact', 'converted'))
        rows.append((
            observation_id, document_id, corpus, doi, year, year_confidence,
            property_id, canonical, localized.get('ru'), category,
            CATEGORY_RU.get(category, category), header, value_raw, unit_raw,
            value_normalized, unit_normalized, status, header_kind, plausibility,
            spatial, strip_host_paths(row_label), horizon, depth_top, depth_bottom,
            latitude, longitude, tier, trusted, metric, page_start,
            strip_host_paths(table_label),
        ))
    target.executemany(
        f"INSERT INTO observation VALUES({','.join('?' * 31)})", rows)

    target.executemany(
        "INSERT INTO reported_site VALUES(?,?,?,?,?,?,?,?)",
        source.execute("""
            SELECT s.site_id, s.latitude, s.longitude, s.region, s.spatial_confidence,
                   MIN(a.document_id), MIN(d.corpus), MIN(COALESCE(y.publication_year, d.publication_year))
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
        ('raw_observations', str(source.execute("SELECT COUNT(*) FROM table_observation").fetchone()[0])),
        ('excluded_rejected_unclassified', str(source.execute(
            "SELECT COUNT(*) FROM table_observation WHERE property_id='unclassified_table_metric'"
        ).fetchone()[0])),
        ('license', 'CC BY 4.0 for the compiled database; source articles remain under their own rights'),
        ('note', 'Clean export: rejected unclassified raw candidates remain only in the source audit layer.'),
    ])
    target.commit()
    target.execute('VACUUM')
    target.close()
    return len(rows)


# --------------------------------------------------------------------------
# Map payload
# --------------------------------------------------------------------------

def build_map(source: sqlite3.Connection) -> dict:
    """The interactive map, restricted to sites inside Russia's borders.

    217 of the 1431 spatially-confident sites (2026-08-11) sit outside
    RUSSIA_BOUNDS -- foreign case-study/comparison sites an author cites
    within an otherwise Russian study (see the manuscript's limitations).
    The portal's own spatial statistics (Clark-Evans, nearest neighbour,
    grid occupancy) already exclude them; the map now does too, so a reader
    of "Russian Soil Observatory" does not open the map to see pins in
    Chile or Vietnam with no explanation. Excluded sites remain fully
    queryable via the SQL tab and the CSV/SQLite exports.
    """
    sites: dict[tuple[float, float], dict] = {}
    for site_id, latitude, longitude, region, corpus, doi, year, confidence, evidence in source.execute(f"""
        SELECT s.site_id, s.latitude, s.longitude, s.region,
               MIN(d.corpus), MIN(d.doi), MIN(COALESCE(y.publication_year, d.publication_year)), MIN(y.year_confidence),
               MIN(se.evidence_text)
        FROM site s
        LEFT JOIN site_evidence se ON se.site_id = s.site_id
        LEFT JOIN source_artifact a ON a.artifact_id = se.artifact_id
        LEFT JOIN document d ON d.document_id = a.document_id
        LEFT JOIN document_publication_year y ON y.document_id = a.document_id
        WHERE s.latitude IS NOT NULL AND s.spatial_confidence IN ('exact','reported')
          AND s.latitude BETWEEN {RUSSIA_BOUNDS['lat'][0]} AND {RUSSIA_BOUNDS['lat'][1]}
          AND s.longitude BETWEEN {RUSSIA_BOUNDS['lon'][0]} AND {RUSSIA_BOUNDS['lon'][1]}
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

    # Per-point measurements are read straight off `table_observation` via its
    # `context_site_id` link to `site` — NOT via the legacy `measurement`
    # table's `operational_measurement_id` back-reference, which a live audit
    # showed ties only 516 of the current 94,996 observations (the old
    # promotion step was never rerun against the rebuilt observation layer).
    # `context_site_id` is the link the rebuilt pipeline actually populates:
    # 15,124 observations reference it, 12,792 of them at sites with
    # coordinates.
    for latitude, longitude, canonical, value, unit, qa, doi in source.execute("""
        SELECT s.latitude, s.longitude, p.canonical_name,
               COALESCE(o.value_normalized, o.value_num_raw),
               COALESCE(o.unit_normalized, o.unit_raw), o.qa_status, d.doi
        FROM table_observation o
        JOIN site s ON s.site_id = o.context_site_id
        JOIN property_definition p ON p.property_id = o.property_id
        JOIN document d ON d.document_id = o.document_id
        WHERE s.latitude IS NOT NULL
          AND o.property_id <> 'unclassified_table_metric'
    """):
        key = (round(latitude, 5), round(longitude, 5))
        if key in sites and len(sites[key]['measurements']) < 60:
            sites[key]['measurements'].append({
                'property': canonical, 'value': value, 'unit': unit,
                'qa': qa, 'doi': doi,
            })

    # Soil type is read off the same `context_site_id` link, for the same
    # reason (see above).
    for latitude, longitude, soil_type, confidence, wrb_group, wrb_confidence in source.execute("""
        SELECT s.latitude, s.longitude, st.soil_type_normalized, st.confidence,
               st.wrb_reference_group, st.wrb_confidence
        FROM table_observation o
        JOIN site s ON s.site_id = o.context_site_id
        JOIN observation_soil_type st ON st.observation_id = o.observation_id
        WHERE s.latitude IS NOT NULL AND st.soil_type_normalized IS NOT NULL
          AND o.property_id <> 'unclassified_table_metric'
    """):
        key = (round(latitude, 5), round(longitude, 5))
        entry = sites.get(key)
        if entry is None:
            continue
        soil_types = entry.setdefault('soil_types', [])
        item = {
            'soil_type': soil_type, 'confidence': confidence,
            'wrb_group': wrb_group, 'wrb_confidence': wrb_confidence,
        }
        if item not in soil_types and len(soil_types) < 6:
            soil_types.append(item)

    points = sorted(sites.values(), key=lambda item: (-len(item['measurements']), -item['records']))
    return {'points': points}


# --------------------------------------------------------------------------
# Aggregates
# --------------------------------------------------------------------------

def _merge_category_rows(raw_rows):
    """Fold `(category, distinct_property_count, observation_count)` rows
    grouped by the *raw* category into CATEGORY_MERGE's canonical slugs.
    Summing COUNT(DISTINCT property_id) across the merged rows is safe: a
    property_id has exactly one category in property_definition, so no
    property can appear under two of the raw categories being combined."""
    merged: dict[str, dict[str, int]] = {}
    for category, props, count in raw_rows:
        canonical = merged_category(category)
        bucket = merged.setdefault(canonical, {'properties': 0, 'observations': 0})
        bucket['properties'] += props
        bucket['observations'] += count
    return merged


def build_aggregates(source: sqlite3.Connection, names: dict[str, dict[str, str]]) -> dict:
    def rows(sql: str) -> list[tuple]:
        return source.execute(sql).fetchall()

    corpus = dict(rows("SELECT corpus, COUNT(*) FROM document GROUP BY 1"))
    total_observations = rows("SELECT COUNT(*) FROM table_observation WHERE property_id <> 'unclassified_table_metric'")[0][0]
    raw_observations = rows("SELECT COUNT(*) FROM table_observation")[0][0]

    # A property's own distribution needs a scan of its trusted+metric values,
    # its depth coverage and its spatial coverage.  106 286 rows is cheap to
    # walk once in Python; 101 separate queries would not be, and SQLite has
    # no portable median, so percentiles are computed here instead of in SQL.
    census: dict[str, dict] = defaultdict(lambda: {
        'depth': 0, 'spatial': 0, 'values': [], 'units': Counter()})
    for pid, value, unit, has_depth, is_metric, is_trusted, has_spatial in rows("""
        SELECT o.property_id, o.value_normalized, o.unit_normalized,
               CASE WHEN o.depth_top_cm IS NOT NULL THEN 1 ELSE 0 END,
               CASE WHEN o.normalization_status IN ('exact','converted') THEN 1 ELSE 0 END,
               CASE WHEN f.header_match_kind <> 'symbol_embedded'
                         AND f.value_plausibility = 'ok' THEN 1 ELSE 0 END,
               CASE WHEN t.document_id IS NOT NULL THEN 1 ELSE 0 END
        FROM table_observation o
        JOIN observation_quality_flag f ON f.observation_id = o.observation_id
        LEFT JOIN document_spatial_tier t ON t.document_id = o.document_id
        WHERE o.property_id <> 'unclassified_table_metric'
    """):
        entry = census[pid]
        entry['depth'] += has_depth
        entry['spatial'] += has_spatial
        if is_metric and is_trusted and value is not None:
            entry['values'].append(value)
            entry['units'][unit] += 1

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
        WHERE o.property_id <> 'unclassified_table_metric'
        GROUP BY 1,2,3 ORDER BY 4 DESC
    """):
        category = merged_category(category)
        localized = names.get(pid, {})
        entry = census[pid]
        values = sorted(entry['values'])
        properties.append({
            'property_id': pid, 'property': canonical,
            'property_ru': localized.get('ru'),
            # The per-property CSV only covers the curated canonical
            # vocabulary; ~1990 source-specific properties (2026-08-11) have
            # no row there at all. Their category is still one of the ~90
            # category slugs CATEGORY_RU now covers, so fall back to that
            # rather than showing the raw snake_case category to a reader.
            'category': category,
            'category_ru': CATEGORY_RU.get(category, category),
            'observations': count, 'normalized': normalized,
            'header_trusted': clean, 'value_plausible': plausible,
            'documents': docs,
            'with_depth': entry['depth'],
            'with_spatial': entry['spatial'],
            'unit_mode': entry['units'].most_common(1)[0][0] if entry['units'] else None,
            'median': round(percentile(values, 0.5), 4) if values else None,
            'p25': round(percentile(values, 0.25), 4) if values else None,
            'p75': round(percentile(values, 0.75), 4) if values else None,
            'n_metric': len(values),
        })

    per_year = [
        {'year': year, 'observations': observations, 'documents': documents}
        for year, observations, documents in rows("""
            SELECT COALESCE(y.publication_year, d.publication_year), COUNT(*), COUNT(DISTINCT o.document_id)
            FROM table_observation o
            JOIN document d ON d.document_id = o.document_id
            LEFT JOIN document_publication_year y ON y.document_id = o.document_id
            WHERE o.property_id <> 'unclassified_table_metric'
            GROUP BY 1 ORDER BY 1
        """)
    ]

    documents_per_year = [
        {'year': year, 'pochvovedenie': russian, 'springer': springer}
        for year, russian, springer in rows("""
            SELECT COALESCE(y.publication_year, d.publication_year),
                   SUM(d.corpus IN ('pochvovedenie','rcsi')), SUM(d.corpus='springer')
            FROM document d LEFT JOIN document_publication_year y USING(document_id)
            GROUP BY 1 ORDER BY 1
        """)
    ]

    points = [(lat, lon) for lat, lon in rows(
        """SELECT DISTINCT ROUND(latitude,5), ROUND(longitude,5) FROM site
           WHERE latitude IS NOT NULL AND spatial_confidence IN ('exact','reported')""")
        if RUSSIA_BOUNDS['lat'][0] <= lat <= RUSSIA_BOUNDS['lat'][1]
        and RUSSIA_BOUNDS['lon'][0] <= lon <= RUSSIA_BOUNDS['lon'][1]]
    neighbours = sorted(
        min(haversine(point, other) for index, other in enumerate(points) if index != position)
        for position, point in enumerate(points)
    ) if len(points) > 1 else []
    expected = 0.5 / math.sqrt(len(points) / RUSSIA_AREA_KM2) if points else 0.0

    cells = Counter((int(math.floor(lat / 5)) * 5, int(math.floor(lon / 5)) * 5)
                    for lat, lon in points)

    spatial = {
        'unique_positions': len(points),
        'coordinate_records': rows(f"""SELECT COUNT(*) FROM site
             WHERE latitude IS NOT NULL AND spatial_confidence IN ('exact','reported')
               AND latitude BETWEEN {RUSSIA_BOUNDS['lat'][0]} AND {RUSSIA_BOUNDS['lat'][1]}
               AND longitude BETWEEN {RUSSIA_BOUNDS['lon'][0]} AND {RUSSIA_BOUNDS['lon'][1]}""")[0][0],
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
            "SELECT f.header_match_kind, COUNT(*) FROM observation_quality_flag f "
            "JOIN table_observation o ON o.observation_id=f.observation_id "
            "WHERE o.property_id <> 'unclassified_table_metric' GROUP BY 1")),
        'value_plausibility': dict(rows(
            "SELECT f.value_plausibility, COUNT(*) FROM observation_quality_flag f "
            "JOIN table_observation o ON o.observation_id=f.observation_id "
            "WHERE o.property_id <> 'unclassified_table_metric' GROUP BY 1")),
        'normalization_status': dict(rows(
            "SELECT normalization_status, COUNT(*) FROM table_observation WHERE property_id <> 'unclassified_table_metric' GROUP BY 1")),
        # 2026-08 rebuild: table_observation is admission-gated (three-agent
        # verified provenance; a row only exists here once its unit is
        # proven), so normalization_status is 'exact'/'converted' for
        # everything in it and the old per-row confidence tier
        # (observation_unit_inference) is retired. The meaningful "how much
        # of the source material actually made it in" number is now the
        # candidate admission rate.
        'candidate_status': dict(rows(
            "SELECT status, COUNT(*) FROM table_measurement_candidate GROUP BY 1")),
        'spatial_linkage': dict(rows(
            "SELECT spatial_linkage, COUNT(*) FROM table_observation WHERE property_id <> 'unclassified_table_metric' GROUP BY 1")),
        'analysis_ready': rows("""
            SELECT COUNT(*) FROM table_observation o
            JOIN observation_quality_flag f ON f.observation_id = o.observation_id
            WHERE o.property_id <> 'unclassified_table_metric'
              AND f.header_match_kind <> 'symbol_embedded' AND f.value_plausibility = 'ok'""")[0][0],
        'unflagged': rows("""
            SELECT COUNT(*) FROM observation_quality_flag f
            JOIN table_observation o ON o.observation_id=f.observation_id
            WHERE o.property_id <> 'unclassified_table_metric'
              AND f.header_match_kind <> 'symbol_embedded' AND f.value_plausibility = 'ok'""")[0][0],
    }

    depth = {
        'with_depth': rows("SELECT COUNT(*) FROM table_observation WHERE property_id <> 'unclassified_table_metric' AND depth_top_cm IS NOT NULL")[0][0],
        'profiles': rows("""SELECT COUNT(*) FROM (
              SELECT document_id, row_label_raw FROM table_observation
              WHERE property_id <> 'unclassified_table_metric' AND depth_top_cm IS NOT NULL GROUP BY 1,2)""")[0][0],
    }

    return {
        'documents': {'total': sum(corpus.values()), **corpus},
        'observations': total_observations,
        'raw_observations': raw_observations,
        'excluded_rejected_unclassified': raw_observations - total_observations,
        'artifacts': rows("SELECT COUNT(*) FROM source_artifact")[0][0],
        'ocr_tables': rows("SELECT COUNT(DISTINCT artifact_id) FROM table_cell")[0][0],
        'properties': properties,
        'categories': sorted((
            {'category': category,
             'category_ru': CATEGORY_RU.get(category, category),
             'category_en': CATEGORY_EN.get(category, category),
             'observations': merged['observations'], 'properties': merged['properties']}
            for category, merged in _merge_category_rows(rows("""
                SELECT p.category, COUNT(DISTINCT p.property_id), COUNT(*)
                FROM table_observation o JOIN property_definition p ON p.property_id=o.property_id
                WHERE o.property_id <> 'unclassified_table_metric'
                GROUP BY 1""")).items()),
            key=lambda row: -row['observations']),
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
    'unit_normalized', 'normalization_status', 'unit_confidence', 'unit_method',
    'header_match_kind',
    'value_plausibility', 'plausibility_rule', 'qa_status', 'spatial_linkage',
    'context_latitude', 'context_longitude', 'spatial_tier', 'row_label_raw',
    'horizon_label_raw', 'depth_top_cm', 'depth_bottom_cm', 'page_start',
    'table_label', 'evidence_locator',
]


def export_csv(source: sqlite3.Connection, path: Path, names: dict[str, dict[str, str]]) -> int:
    written = 0
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(CSV_COLUMNS)
        for row in source.execute("""
            SELECT o.observation_id, o.candidate_id, o.document_id, d.corpus, d.doi,
                   COALESCE(y.publication_year, d.publication_year), y.year_confidence, p.canonical_name, o.property_id,
                   p.category, o.property_header_raw, o.value_num_raw, o.unit_raw,
                   o.value_normalized, o.unit_normalized, o.normalization_status,
                   u.confidence, u.method,
                   f.header_match_kind, f.value_plausibility, f.plausibility_rule,
                   o.qa_status, o.spatial_linkage, t.latitude, t.longitude, t.tier,
                   o.row_label_raw, o.horizon_label_raw, o.depth_top_cm, o.depth_bottom_cm,
                   a.page_start, a.table_label, o.evidence_locator
            FROM table_observation o
            JOIN document d ON d.document_id = o.document_id
            JOIN property_definition p ON p.property_id = o.property_id
            JOIN observation_quality_flag f ON f.observation_id = o.observation_id
            JOIN source_artifact a ON a.artifact_id = o.artifact_id
            LEFT JOIN document_publication_year y ON y.document_id = o.document_id
            LEFT JOIN document_spatial_tier t ON t.document_id = o.document_id
            LEFT JOIN observation_unit_inference u ON u.observation_id = o.observation_id
            WHERE o.property_id <> 'unclassified_table_metric'
            ORDER BY o.observation_id
        """):
            values = [strip_host_paths(cell) for cell in row]
            property_id = values.pop(8)
            values.insert(8, names.get(property_id, {}).get('ru'))
            values[9] = merged_category(values[9])
            writer.writerow(values)
            written += 1
    return written


def export_document_links(source: sqlite3.Connection, path: Path) -> int:
    """Export the Russian-original/translation correspondence table.

    Documents are never merged, so this is the only place the correspondence
    is visible: each row asserts that ``document_id_a`` and ``document_id_b``
    describe the same article, with the evidence and confidence that
    produced the link (see link_springer_translations.py).
    """
    rows = source.execute("""
        SELECT document_id_a, document_id_b, relation, confidence, evidence_note
        FROM document_link ORDER BY document_id_b
    """).fetchall()
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(['document_id_a', 'document_id_b', 'relation', 'confidence', 'evidence_note'])
        writer.writerows(rows)
    return len(rows)


def export_property_census(properties: list[dict], path: Path) -> int:
    """Write the full per-property coverage table the analysis appendix reads.

    Every property the pipeline recognises gets one row, not only the ones
    prose in the report singles out — this is what makes "every property is
    in the analysis" true rather than aspirational.
    """
    columns = [
        'property_id', 'property', 'property_ru', 'category', 'category_ru',
        'observations', 'documents', 'unit_proven_pct', 'header_trusted_pct',
        'value_plausible_pct', 'with_depth_pct', 'with_spatial_pct',
        'unit_mode', 'median', 'p25', 'p75', 'n_metric',
    ]
    with path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(columns)
        for row in properties:
            n = row['observations'] or 1
            writer.writerow([
                row['property_id'], row['property'], row['property_ru'],
                row['category'], row['category_ru'], row['observations'],
                row['documents'], round(100 * row['normalized'] / n, 1),
                round(100 * row['header_trusted'] / n, 1),
                round(100 * row['value_plausible'] / n, 1),
                round(100 * row['with_depth'] / n, 1),
                round(100 * row['with_spatial'] / n, 1),
                row['unit_mode'], row['median'], row['p25'], row['p75'],
                row['n_metric'],
            ])
    return len(properties)


def export_supplemental_layer(
    core: sqlite3.Connection,
    extended: sqlite3.Connection,
    output: Path,
    names: dict[str, dict[str, str]],
) -> dict:
    """Export explicit semantic mappings without changing the core layer.

    The extended repair copy contains a deliberately broader experimental
    catalog.  Only rows whose extended property is absent from the fixed core
    catalog and whose core candidate is still unclassified are exported here.
    They remain supplemental evidence, not core observations used by the
    manuscript aggregates.
    """
    core_ids = {row[0] for row in core.execute(
        'SELECT property_id FROM property_definition')}
    core_assignments = dict(core.execute(
        'SELECT candidate_id, property_id FROM table_observation'))
    extended_rows = extended.execute("""
        SELECT o.observation_id, o.candidate_id, o.document_id, d.corpus, d.doi,
               COALESCE(y.publication_year, d.publication_year),
               o.property_id, p.canonical_name, p.category,
               o.property_header_raw, o.value_num_raw, o.unit_raw,
               o.value_normalized, o.unit_normalized, o.normalization_status,
               f.header_match_kind, f.value_plausibility, f.plausibility_rule,
               o.qa_status, o.row_label_raw, o.horizon_label_raw,
               o.depth_top_cm, o.depth_bottom_cm, a.page_start, a.table_label,
               o.evidence_locator
        FROM table_observation o
        JOIN document d ON d.document_id=o.document_id
        JOIN property_definition p ON p.property_id=o.property_id
        JOIN observation_quality_flag f ON f.observation_id=o.observation_id
        JOIN source_artifact a ON a.artifact_id=o.artifact_id
        LEFT JOIN document_publication_year y ON y.document_id=o.document_id
        WHERE o.property_id <> 'unclassified_table_metric'
        ORDER BY o.observation_id
    """).fetchall()
    rows = [row for row in extended_rows
            if row[6] not in core_ids
            and core_assignments.get(row[1]) == 'unclassified_table_metric']

    observation_path = output / 'supplemental_observations.csv'
    observation_columns = [
        'observation_id', 'candidate_id', 'document_id', 'corpus', 'doi',
        'publication_year', 'property_id', 'property', 'property_ru',
        'category', 'property_header_raw', 'value_num_raw', 'unit_raw',
        'value_normalized', 'unit_normalized', 'normalization_status',
        'header_match_kind', 'value_plausibility', 'plausibility_rule',
        'qa_status', 'row_label_raw', 'horizon_label_raw', 'depth_top_cm',
        'depth_bottom_cm', 'page_start', 'table_label', 'evidence_locator',
        'layer_status',
    ]
    with observation_path.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(observation_columns)
        for row in rows:
            values = list(row)
            property_id = values[6]
            values.insert(8, names.get(property_id, {}).get('ru'))
            values[9] = merged_category(values[9])
            values.append('supplemental_semantic_not_core')
            writer.writerow([strip_host_paths(value) for value in values])

    property_ids = sorted({row[6] for row in rows})
    definitions = []
    for property_id in property_ids:
        definition = extended.execute(
            'SELECT property_id, canonical_name, category, canonical_unit '
            'FROM property_definition WHERE property_id=?', (property_id,)
        ).fetchone()
        property_rows = [row for row in rows if row[6] == property_id]
        documents = sorted({row[2] for row in property_rows})
        category = merged_category(definition[2])
        definitions.append([
            *definition[:2], category, definition[3],
            names.get(property_id, {}).get('ru'),
            CATEGORY_RU.get(category, category),
            len(property_rows), len(documents), ';'.join(documents),
            'explicit_header_mapping',
        ])
    with (output / 'supplemental_property_definitions.csv').open(
            'w', encoding='utf-8', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow([
            'property_id', 'property', 'category', 'canonical_unit',
            'property_ru', 'category_ru', 'observations', 'documents',
            'document_ids', 'mapping_basis',
        ])
        writer.writerows(definitions)

    core_raw = core.execute('SELECT COUNT(*) FROM table_observation').fetchone()[0]
    core_unclassified = core.execute(
        "SELECT COUNT(*) FROM table_observation "
        "WHERE property_id='unclassified_table_metric'"
    ).fetchone()[0]
    audit = {
        'core_catalog_definitions': len(core_ids),
        'core_raw_observations': core_raw,
        'core_unclassified_observations': core_unclassified,
        'supplemental_property_definitions': len(definitions),
        'supplemental_observations': len(rows),
        'core_quarantine_after_supplemental_mapping': core_unclassified - len(rows),
        'extended_candidate_quarantine': extended.execute(
            "SELECT COUNT(*) FROM table_observation "
            "WHERE property_id='unclassified_table_metric'"
        ).fetchone()[0],
        'layer_status': 'supplemental_semantic_not_core',
        'definition': (
            'Explicit mappings from the extended repair copy. They retain '
            'raw provenance and are excluded from core portal aggregates, '
            'manuscript tables, and the fixed 2,629-property catalog.'
        ),
    }
    (output / 'supplemental_layer_audit.json').write_text(
        json.dumps(audit, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return audit


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=Path('docs/data'))
    parser.add_argument('--dictionary', type=Path,
                        default=Path('docs/data/property_dictionary_ru_public.csv'))
    parser.add_argument('--supplemental-db', type=Path,
                        help='Extended repair copy used only for the supplemental semantic export.')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    names = load_property_names(args.dictionary)
    source = sqlite3.connect(f'file:{args.db}?mode=ro', uri=True)
    supplemental = None
    supplemental_audit = None
    if args.supplemental_db:
        supplemental = sqlite3.connect(
            f'file:{args.supplemental_db}?mode=ro', uri=True)
    generated_at = source.execute("SELECT datetime('now')").fetchone()[0]

    aggregates = build_aggregates(source, names)
    aggregates['generated_at'] = generated_at
    if supplemental is not None:
        supplemental_audit = export_supplemental_layer(
            source, supplemental, args.output, names)
        aggregates['supplemental_semantic_layer'] = supplemental_audit
    (args.output / 'aggregates.json').write_text(
        json.dumps(aggregates, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    payload = build_map(source)
    payload['generated_at'] = generated_at
    (args.output / 'portal_map.json').write_text(
        json.dumps(payload, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')

    observations = build_browser_database(source, args.output / 'observatory.sqlite',
                                          names, generated_at)
    exported = export_csv(source, args.output / 'full_table_observations.csv', names)
    census_rows = export_property_census(
        aggregates['properties'], args.output / 'property_census.csv')
    link_rows = export_document_links(source, args.output / 'document_links.csv')
    raw_count = source.execute("SELECT COUNT(*) FROM table_observation").fetchone()[0]
    excluded_count = source.execute(
        "SELECT COUNT(*) FROM table_observation WHERE property_id='unclassified_table_metric'"
    ).fetchone()[0]
    excluded_status = dict(source.execute(
        """SELECT q.status, COUNT(*)
           FROM table_observation o
           JOIN table_manual_review_queue q ON q.candidate_id=o.candidate_id
           WHERE o.property_id='unclassified_table_metric'
           GROUP BY q.status"""
    ).fetchall())
    excluded_quality = dict(source.execute(
        """SELECT COALESCE(f.value_plausibility, 'no_quality_flag'), COUNT(*)
           FROM table_observation o
           LEFT JOIN observation_quality_flag f ON f.observation_id=o.observation_id
           WHERE o.property_id='unclassified_table_metric'
           GROUP BY COALESCE(f.value_plausibility, 'no_quality_flag')"""
    ).fetchall())
    clean_soil_links = source.execute(
        """SELECT COUNT(*) FROM observation_soil_type st
           JOIN table_observation o ON o.observation_id=st.observation_id
           WHERE o.property_id <> 'unclassified_table_metric'"""
    ).fetchone()[0]
    (args.output / 'full_table_observation_audit.json').write_text(
        json.dumps({
            'raw_table_observations': raw_count,
            'clean_table_observations': raw_count - excluded_count,
            'excluded_rejected_unclassified': excluded_count,
            'excluded_queue_status': excluded_status,
            'excluded_unclassified_quality': excluded_quality,
            'supplemental_semantic_layer': supplemental_audit,
            'clean_soil_type_links': clean_soil_links,
            'source_soil_type_links': source.execute(
                'SELECT COUNT(*) FROM observation_soil_type').fetchone()[0],
            'soil_type_orphans': source.execute(
                """SELECT COUNT(*) FROM observation_soil_type st
                   LEFT JOIN table_observation o ON o.observation_id=st.observation_id
                   WHERE o.observation_id IS NULL"""
            ).fetchone()[0],
            'foreign_key_errors': len(source.execute('PRAGMA foreign_key_check').fetchall()),
            'integrity_check': source.execute('PRAGMA integrity_check').fetchone()[0],
            'definition': 'Public portal exports only clean table observations; rejected raw candidates remain in the audit source.',
        }, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    source.close()
    if supplemental is not None:
        supplemental.close()

    print(json.dumps({
        'generated_at': generated_at,
        'browser_database_rows': observations,
        'csv_rows': exported,
        'property_census_rows': census_rows,
        'document_link_rows': link_rows,
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
