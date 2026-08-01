#!/usr/bin/env python3
"""Read-only inventory of profile candidates with a direct coordinate-label match."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


def contains_label(context: str, label: str | None) -> bool:
    label=(label or '').strip()
    # The prose extractor may call a generic Russian noun a label.  A direct
    # multi-site link requires a specific field identifier such as RG-7 or P8.
    return (len(label)>=3 and bool(re.search(r'\d',label)) and
            bool(re.search(r'(?<![\w-])'+re.escape(label)+r'(?![\w-])',context or '',re.I)))

SQL = """
SELECT pc.candidate_id,pc.extraction_id,pc.profile_label,pc.soil_classification_raw,
       pc.classification_system_candidate,pc.land_use_raw,pc.context_text,
       lc.candidate_id AS coordinate_candidate_id,lc.latitude,lc.longitude,lc.context_text AS coordinate_context,
       d.document_id,d.corpus,a.artifact_id
FROM profile_candidate pc JOIN location_candidate lc ON lc.extraction_id=pc.extraction_id
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
JOIN extraction e ON e.extraction_id=pc.extraction_id JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE pc.status='unreviewed' AND pc.profile_label IS NOT NULL
  AND lv.country_code='RU' AND lv.result='inside'
"""

def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args()
    grouped=defaultdict(list)
    with sqlite3.connect(a.db) as c:
        c.row_factory=sqlite3.Row
        for r in c.execute(SQL):
            rec=dict(r)
            if contains_label(rec['coordinate_context'],rec['profile_label']): grouped[rec['candidate_id']].append(rec)
    rows=[]; stats=Counter()
    for cid,matches in grouped.items():
        coords={r['coordinate_candidate_id'] for r in matches}
        if len(coords)!=1: stats['ambiguous_coordinate_label']+=1; continue
        rows.append(matches[0]); stats['direct_label_coordinate']+=1
    if a.output:
        fields=['candidate_id','document_id','corpus','profile_label','soil_classification_raw','classification_system_candidate','land_use_raw','coordinate_candidate_id','latitude','longitude','context_text','coordinate_context','artifact_id']
        with a.output.open('w',encoding='utf-8',newline='') as f:
            w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:r[k] for k in fields} for r in rows])
    print(json.dumps({'rows':len(rows),'stats':dict(stats)},ensure_ascii=False))

if __name__=='__main__':main()
