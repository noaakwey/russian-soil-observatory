#!/usr/bin/env python3
"""Produce an auditable queue for human/LLM review; never promote records.

The queue intentionally carries the original evidence snippets instead of
inventing joins between a paper's coordinates and its many table values.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


SQL = '''
SELECT mc.candidate_id, d.corpus, d.document_id, d.title, d.doi,
       pd.canonical_name AS property, mc.property_raw, mc.value_num,
       mc.value_text, mc.unit_raw, mc.method_raw, mc.sample_label,
       mc.horizon_label, mc.depth_top_cm, mc.depth_bottom_cm,
       mc.context_text AS measurement_context,
       lc.candidate_id AS coordinate_candidate_id, lc.latitude, lc.longitude,
       lc.context_text AS coordinate_context, lv.country_code, lv.result
FROM measurement_candidate mc
JOIN extraction e ON e.extraction_id=mc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
LEFT JOIN property_definition pd ON pd.property_id=mc.property_id
LEFT JOIN (
  SELECT e2.artifact_id, lc2.candidate_id, lc2.latitude, lc2.longitude,
         lc2.context_text, lv2.country_code, lv2.result
  FROM location_candidate lc2
  JOIN extraction e2 ON e2.extraction_id=lc2.extraction_id
  LEFT JOIN location_validation lv2 ON lv2.candidate_id=lc2.candidate_id
) lc ON lc.artifact_id=a.artifact_id
LEFT JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
WHERE mc.status='unreviewed'
ORDER BY d.corpus, d.document_id, mc.candidate_id
'''


def confidence(row: dict, ru_count: int) -> tuple[str, str]:
    """A conservative linkage classification, not an acceptance decision."""
    if row['country_code'] != 'RU' or row['result'] != 'inside':
        return 'no_russian_coordinate', 'No explicit coordinate validated inside Russia for this evidence path.'
    label = row['sample_label'] or row['horizon_label']
    coord_context = (row['coordinate_context'] or '').casefold()
    if label and label.casefold() in coord_context:
        return 'strong_candidate', 'Sample/horizon label occurs in the coordinate evidence context; reviewer must confirm table semantics.'
    if ru_count == 1:
        return 'document_level_candidate', 'Exactly one Russian coordinate occurs in this document, but the value is not yet tied to it.'
    return 'ambiguous_multi_site', 'Multiple Russian coordinates occur in this document; do not promote without a direct label/table link.'


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(SQL)]
    ru_count = Counter(
        r['document_id'] for r in rows
        if r['country_code'] == 'RU' and r['result'] == 'inside'
    )
    # The SQL join repeats a coordinate for each measurement; count unique IDs.
    unique_ru: defaultdict[str, set[str]] = defaultdict(set)
    for r in rows:
        if r['country_code'] == 'RU' and r['result'] == 'inside' and r['coordinate_candidate_id']:
            unique_ru[r['document_id']].add(r['coordinate_candidate_id'])
    counts = Counter()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('w', encoding='utf-8') as out:
        for r in rows:
            klass, why = confidence(r, len(unique_ru[r['document_id']]))
            r['linkage_class'] = klass
            r['review_reason'] = why
            counts[klass] += 1
            out.write(json.dumps(r, ensure_ascii=False) + '\n')
    print(json.dumps({'records': len(rows), 'by_linkage_class': counts}, ensure_ascii=False, default=dict))


if __name__ == '__main__':
    main()
