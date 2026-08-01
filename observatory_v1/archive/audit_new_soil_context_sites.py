#!/usr/bin/env python3
"""Select independent, explicitly soil-context coordinates without claiming samples.

This intentionally admits a reported research/study context only when the
source names a concrete field object or study action.  Literature/table
attributions remain candidates rather than becoming sites.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path


GOOD = re.compile(r"\b(?:pit|profile|plot|station|site|experiment(?:al)?|sampled?|studied|research area|"
                  r"soil\s+cover|forest\s+reserve)\b|(?:разрез|скв\w*|участ\w*|"
                  r"станци\w*|опытн\w*|исследован\w*|почвенн\w*\s+покров)", re.I)
BAD = re.compile(r"\b(?:according\s+to|cited\s+in|reference(?:s)?|bibliograph\w*)\s*\[|"
                 r"(?:по\s+данным|согласно)\s*\[|https?://|www\.", re.I)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        artifact_types = {candidate_id: artifact_type for candidate_id, artifact_type in con.execute("""SELECT lc.candidate_id,a.artifact_type
          FROM location_candidate lc JOIN extraction e ON e.extraction_id=lc.extraction_id
          JOIN source_artifact a ON a.artifact_id=e.artifact_id""")}
        existing = {(doc, round(lat, 7), round(lon, 7)) for doc, lat, lon in con.execute("""SELECT DISTINCT d.document_id,s.latitude,s.longitude
          FROM site s JOIN site_evidence se ON se.site_id=s.site_id JOIN source_artifact a ON a.artifact_id=se.artifact_id
          JOIN document d ON d.document_id=a.document_id""")}
    selected: dict[tuple[str, float, float], dict[str, str]] = {}
    with args.input.open(encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['category'] != 'soil_context_without_sampling_action':
                continue
            if artifact_types.get(row['candidate_id']) != 'text':
                continue
            context = row.get('context_text') or ''
            if BAD.search(context) or not GOOD.search(context):
                continue
            key = (row['document_id'], round(float(row['latitude']), 7), round(float(row['longitude']), 7))
            if key not in existing:
                selected.setdefault(key, row)
    fields = ['candidate_id','precision_hint','category','document_id','corpus','latitude','longitude','context_text']
    with args.output.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in selected.values():
            writer.writerow({**{field: row.get(field, '') for field in fields}, 'category': 'direct_soil_study_context'})
    print({'selected': len(selected)})


if __name__ == '__main__':
    main()
