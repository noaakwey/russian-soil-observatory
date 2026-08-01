#!/usr/bin/env python3
"""Attribute a study region to each document from its full text.

Three quarters of the observation layer sat in documents with no location at
all, not because the articles omit one but because no extractor had ever read
their ``text`` artifact: 85% of them name an oblast, krai, republic or a major
physiographic region in prose.

The result is deliberately a *region*, not a point.  Every row carries the
centroid of the named unit, its approximate radius, how many times it was
mentioned, and whether a single unit dominates the article.  Nothing here may
be used as a sampling coordinate; it exists so zonal questions can be asked of
the whole corpus instead of the 6.7% with printed coordinates.

Priority order, so a precise statement always beats a vague one:

1. a named federal subject ("Kursk oblast", "Republic of Tatarstan");
2. a physiographic macroregion ("Western Siberia", "the Caucasus"), used only
   when no subject is found.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from russian_region_gazetteer import REGIONS, SUBJECT_SUFFIXES

DDL = """
CREATE TABLE IF NOT EXISTS document_study_region (
  document_id TEXT NOT NULL REFERENCES document(document_id),
  region_name TEXT NOT NULL,
  region_kind TEXT NOT NULL CHECK (region_kind IN ('subject','macroregion')),
  latitude REAL NOT NULL,
  longitude REAL NOT NULL,
  radius_km REAL NOT NULL,
  mentions INTEGER NOT NULL,
  rank INTEGER NOT NULL,
  attribution TEXT NOT NULL CHECK (attribution IN ('single_region','dominant_region','multi_region')),
  method TEXT NOT NULL,
  PRIMARY KEY (document_id, region_name)
);
CREATE INDEX IF NOT EXISTS idx_study_region_doc ON document_study_region(document_id);
CREATE INDEX IF NOT EXISTS idx_study_region_name ON document_study_region(region_name);
"""

SUFFIX_GROUP = '|'.join(SUBJECT_SUFFIXES)


def build_pattern() -> re.Pattern:
    """Compile every gazetteer name into one alternation, longest name first.

    Scanning 4 180 articles with one regex per region is minutes of work per
    thousand documents; a single alternation walks each text once.  Longest
    name first matters: without it ``Altai`` would shadow ``Altai Republic``
    and ``Novgorod`` would swallow ``Nizhny Novgorod``.
    """
    alternatives = '|'.join(
        re.escape(name) for name in sorted(REGIONS, key=len, reverse=True))
    return re.compile(
        rf'(?P<name>{alternatives})'
        rf'(?:sky|skaya|skii|skiy)?'
        rf'(?P<suffix>\s+(?:{SUFFIX_GROUP}))?')


PATTERN = build_pattern()

# A location named once in a reference list is not a study area; require the
# mention to appear in the first part of the article, where Methods live.
METHODS_WINDOW = 30000

# A name carrying an administrative suffix is a deliberate statement of place;
# a bare mention counts for less so a passing reference cannot outvote it.
SUFFIX_WEIGHT = 4
BARE_WEIGHT = 1

# Author affiliations name a city in every single article and have nothing to
# do with the study area: without this filter "Moscow" wins 1 010 documents
# purely on "Lomonosov Moscow State University".
AFFILIATION = re.compile(
    r'univer|institut|academy|akadem|faculty|department|laborator|'
    r'e-?mail|@|research cent|state agrar|timiryazev|lomonosov|'
    r'dokuchaev|soil science society|publish|press\b',
    re.I)
AFFILIATION_WINDOW = 70

# The header block carries title, authors and addresses; the study area is
# described later, in Methods.
HEADER_SKIP = 1200


def regions_in(text: str) -> Counter:
    body = text[HEADER_SKIP:METHODS_WINDOW]
    counts: Counter = Counter()
    for match in PATTERN.finditer(body):
        context = body[max(0, match.start() - AFFILIATION_WINDOW):
                       match.end() + AFFILIATION_WINDOW]
        if AFFILIATION.search(context):
            continue
        counts[match.group('name')] += (
            SUFFIX_WEIGHT if match.group('suffix') else BARE_WEIGHT)
    return counts


def resolve(counts: Counter) -> list[tuple[str, int, int]]:
    """Return [(name, mentions, rank)], subjects preferred over macroregions."""
    subjects = {n: c for n, c in counts.items() if REGIONS[n][3] == 'subject'}
    pool = subjects or dict(counts)
    if not pool:
        return []
    ordered = sorted(pool.items(), key=lambda kv: (-kv[1], kv[0]))
    return [(name, hits, rank) for rank, (name, hits) in enumerate(ordered, start=1)]


def classify(resolved: list[tuple[str, int, int]]) -> str:
    if len(resolved) == 1:
        return 'single_region'
    top, second = resolved[0][1], resolved[1][1]
    return 'dominant_region' if top >= 2 * second else 'multi_region'


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--max-regions', type=int, default=3,
                        help='keep at most this many regions per document')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    stats: Counter = Counter()
    region_docs: Counter = Counter()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        con.execute('DELETE FROM document_study_region')
        documents = con.execute("""
            SELECT a.document_id, e.raw_text
            FROM source_artifact a
            JOIN extraction e ON e.artifact_id = a.artifact_id
            WHERE a.artifact_type = 'text' AND e.raw_text IS NOT NULL
        """).fetchall()

        payload = []
        for document_id, text in documents:
            stats['documents_scanned'] += 1
            resolved = resolve(regions_in(text))
            if not resolved:
                stats['no_region_found'] += 1
                continue
            attribution = classify(resolved)
            stats[attribution] += 1
            for name, mentions, rank in resolved[:args.max_regions]:
                latitude, longitude, radius, kind = REGIONS[name]
                payload.append((document_id, name, kind, latitude, longitude,
                                radius, mentions, rank, attribution,
                                'gazetteer match in first 30k characters of full text'))
                if rank == 1:
                    region_docs[name] += 1

        con.executemany("""
            INSERT INTO document_study_region
              (document_id, region_name, region_kind, latitude, longitude,
               radius_km, mentions, rank, attribution, method)
            VALUES (?,?,?,?,?,?,?,?,?,?)
        """, payload)
        con.commit()

        covered = con.execute("""
            SELECT COUNT(*) FROM table_observation
            WHERE document_id IN (SELECT document_id FROM document_study_region)
        """).fetchone()[0]
        total = con.execute('SELECT COUNT(*) FROM table_observation').fetchone()[0]

    report = {
        'documents': dict(stats),
        'observations_with_region': covered,
        'observations_total': total,
        'coverage_pct': round(100 * covered / total, 1) if total else 0,
        'top_regions_by_document_count': dict(region_docs.most_common(25)),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
