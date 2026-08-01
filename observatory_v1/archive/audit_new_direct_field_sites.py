#!/usr/bin/env python3
"""Prepare deduplicated direct field-object coordinates for human-auditable promotion.

The input is the all-candidate audit.  This selector never creates sites: it
keeps only primary text evidence, removes coordinates already represented by a
site in that document, and rejects obvious reference/URL snippets.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path


BAD = re.compile(r"\b(?:https?://|www\.|reference(?:s)?\b|bibliograph\w*|earth\.google)\b", re.I)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    source: dict[str, str] = {}
    with sqlite3.connect(args.db) as con:
        for candidate_id, artifact_type in con.execute("""SELECT lc.candidate_id,a.artifact_type
              FROM location_candidate lc JOIN extraction e ON e.extraction_id=lc.extraction_id
              JOIN source_artifact a ON a.artifact_id=e.artifact_id"""):
            source[candidate_id] = artifact_type
        existing: set[tuple[str, float, float]] = set()
        for document_id, latitude, longitude in con.execute("""SELECT DISTINCT d.document_id,s.latitude,s.longitude
              FROM site s JOIN site_evidence se ON se.site_id=s.site_id
              JOIN source_artifact a ON a.artifact_id=se.artifact_id
              JOIN document d ON d.document_id=a.document_id"""):
            existing.add((document_id, round(latitude, 7), round(longitude, 7)))
    groups: dict[tuple[str, float, float], dict[str, str]] = {}
    with args.input.open(encoding='utf-8') as handle:
        for row in csv.DictReader(handle):
            if row['category'] != 'direct_labeled_field_object':
                continue
            if source.get(row['candidate_id']) != 'text':
                continue
            key = (row['document_id'], round(float(row['latitude']), 7), round(float(row['longitude']), 7))
            if key in existing or BAD.search(row.get('context_text') or ''):
                continue
            groups.setdefault(key, row)
    fields = ['candidate_id','precision_hint','category','document_id','corpus','latitude','longitude','context_text']
    with args.output.open('w', encoding='utf-8', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader()
        for row in groups.values():
            writer.writerow({**{field: row.get(field, '') for field in fields},
                             'category': 'direct_source_field_object'})
    print({'selected': len(groups)})


if __name__ == '__main__':
    main()
