#!/usr/bin/env python3
"""Inspect, without mutating data, whether prose values have direct coordinate proof.

The candidate extractor stores snippets rather than character offsets.  This
audit therefore uses the strongest reproducible proxy available: value and
coordinate candidates generated from the same text extraction, a normalized
property/unit, exactly one validated Russian coordinate there, and a nontrivial
sample or horizon label present in the coordinate evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


def contains_label(context: str, label: str) -> bool:
    label = label.strip()
    return len(label) >= 2 and bool(re.search(r"(?<![\w-])" + re.escape(label) + r"(?![\w-])", context, re.I))


SQL = """
SELECT mc.candidate_id, mc.extraction_id, mc.property_id, mc.value_num, mc.unit_raw,
       mc.horizon_label, mc.sample_label, mc.context_text, n.normalization_status,
       lc.candidate_id AS coordinate_candidate_id, lc.latitude, lc.longitude,
       lc.context_text AS coordinate_context
FROM measurement_candidate mc
JOIN measurement_candidate_normalization n ON n.candidate_id=mc.candidate_id
JOIN location_candidate lc ON lc.extraction_id=mc.extraction_id
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
WHERE mc.status='unreviewed' AND mc.property_id IS NOT NULL
  AND n.normalization_status IN ('exact','converted')
  AND lv.country_code='RU' AND lv.result='inside'
ORDER BY mc.candidate_id
"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--output', type=Path)
    a = p.parse_args()
    by_measurement: dict[str, list[dict]] = defaultdict(list)
    with sqlite3.connect(a.db) as con:
        cols = [x[0] for x in con.execute(SQL).description]
        for row in con.execute(SQL):
            rec = dict(zip(cols, row))
            label = rec['sample_label'] or rec['horizon_label']
            if label and contains_label(rec['coordinate_context'], label):
                by_measurement[rec['candidate_id']].append(rec)
    stats = Counter()
    rows = []
    for cid, matches in by_measurement.items():
        coords = {m['coordinate_candidate_id'] for m in matches}
        if len(coords) != 1:
            stats['ambiguous_same_extraction_coordinate'] += 1
            continue
        r = matches[0]
        stats['direct_same_extraction_label_coordinate'] += 1
        rows.append({k: r[k] for k in ('candidate_id','extraction_id','property_id','value_num','unit_raw','horizon_label','sample_label','coordinate_candidate_id','latitude','longitude','context_text','coordinate_context')})
    if a.output:
        with a.output.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]) if rows else ['candidate_id'])
            w.writeheader(); w.writerows(rows)
    print(json.dumps({'candidate_rows': len(rows), 'stats': dict(stats)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
