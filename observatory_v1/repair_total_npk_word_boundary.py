#!/usr/bin/env python3
"""Purge candidates the total_N/P/K patterns matched by accident.

``total\\s+(?:P|phosphorus)`` (and the N/K equivalents) had no word boundary
after the bare letter, so "Total P" matched as a *prefix* of any word
starting with P: "Total Porosity", "Total Particles", "Total PAHs", "Total
Precipitation", "Total pore volume" all landed in ``total_phosphorus``, and
the same happened to N ("Total Number...") and K ("total key site area").
The fixed patterns in ``table_property_patterns.py`` add a ``\\b`` after the
lone letter; this script removes the candidates the *old* pattern created
that the *new* one would not, so ``extract_table_measurement_candidates.py
--additive`` can reclassify those exact cells correctly on the next run.

Safe by construction: the curated ``measurement`` table (1 239 verified
anchors) has no foreign key into ``table_measurement_candidate`` at all — it
links to ``source_artifact``/``extraction`` directly — so this cannot touch
anything a human verified.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

from extract_table_measurement_candidates import property_for

AFFECTED = ('total_phosphorus', 'total_nitrogen', 'total_potassium')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--dry-run', action='store_true',
                        help='report what would be deleted without deleting')
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        rows = con.execute("""
            SELECT candidate_id, property_id, property_header_raw
            FROM table_measurement_candidate
            WHERE property_id IN (?,?,?)
        """, AFFECTED).fetchall()

        contaminated = [
            (candidate_id, old_property)
            for candidate_id, old_property, header in rows
            if property_for(header) != old_property
        ]

        print(f'{len(rows)} candidates currently tagged {AFFECTED}')
        print(f'{len(contaminated)} no longer match under the corrected pattern')
        if args.dry_run:
            for candidate_id, old_property in contaminated[:20]:
                print(f'  would delete {candidate_id} ({old_property})')
            return

        ids = [cid for cid, _ in contaminated]
        placeholders = ','.join('?' * len(ids))
        if ids:
            observation_ids = [row[0] for row in con.execute(
                f'SELECT observation_id FROM table_observation WHERE candidate_id IN ({placeholders})', ids)]
            obs_placeholders = ','.join('?' * len(observation_ids))
            if observation_ids:
                con.execute(f'DELETE FROM observation_quality_flag WHERE observation_id IN ({obs_placeholders})',
                           observation_ids)
                con.execute(f'DELETE FROM table_observation WHERE observation_id IN ({obs_placeholders})',
                           observation_ids)
            con.execute(f'DELETE FROM table_measurement_candidate_normalization WHERE candidate_id IN ({placeholders})', ids)
            con.execute(f'DELETE FROM table_measurement_candidate WHERE candidate_id IN ({placeholders})', ids)
        con.commit()
        print(f'deleted {len(ids)} contaminated candidates and their observations')


if __name__ == '__main__':
    main()
