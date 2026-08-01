#!/usr/bin/env python3
"""Promote only prose values with an explicit, label-level Russian site link.

This deliberately excludes document-level and multi-site guesses.  A value is
operational only when a sample/horizon identifier from its own evidence occurs
in the evidence for exactly one reported Russian coordinate in that document.
All other values remain candidates for later review.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path


def clean_id(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", value)[:80] or "label"


def contains_label(context: str, label: str) -> bool:
    # Single-character labels (A, B, 1) are pervasive in prose and unsafe.
    if len(label.strip()) < 2:
        return False
    return bool(re.search(r"(?<![\w-])" + re.escape(label.strip()) + r"(?![\w-])", context, re.I))


SQL = '''
SELECT mc.candidate_id AS measurement_candidate_id, mc.extraction_id, mc.property_id, mc.value_num,
       mc.value_text, mc.unit_raw, mc.method_raw, mc.horizon_label,
       mc.depth_top_cm, mc.depth_bottom_cm, mc.sample_label, mc.context_text,
       n.value_normalized, n.unit_normalized, n.normalization_status,
       a.artifact_id, a.document_id, lc.candidate_id AS coordinate_candidate_id,
       lc.context_text AS coordinate_context
FROM measurement_candidate mc
JOIN measurement_candidate_normalization n ON n.candidate_id=mc.candidate_id
JOIN extraction e ON e.extraction_id=mc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN location_candidate lc ON lc.extraction_id IN (
  SELECT e2.extraction_id FROM extraction e2
  JOIN source_artifact a2 ON a2.artifact_id=e2.artifact_id
  WHERE a2.document_id=a.document_id
)
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
WHERE mc.status='unreviewed'
  AND mc.property_id IS NOT NULL
  AND n.normalization_status IN ('exact','converted')
  AND lv.country_code='RU' AND lv.result='inside'
  AND EXISTS (SELECT 1 FROM site s WHERE s.site_id='site:' || lc.candidate_id)
'''


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    args = p.parse_args()
    stats = defaultdict(int)
    with sqlite3.connect(args.db) as con:
        con.execute('PRAGMA foreign_keys=ON')
        columns = [c[0] for c in con.execute(SQL).description]
        by_candidate: dict[str, list[dict]] = defaultdict(list)
        for row in con.execute(SQL):
            rec = dict(zip(columns, row))
            label = rec['sample_label'] or rec['horizon_label']
            if label and contains_label(rec['coordinate_context'], label):
                by_candidate[rec['measurement_candidate_id']].append(rec)
        for candidate_id, matches in by_candidate.items():
            # Exactly one explicit Russian coordinate is required.
            site_matches = {m['coordinate_candidate_id']: m for m in matches}
            if len(site_matches) != 1:
                stats['ambiguous_coordinate_link'] += 1
                continue
            r = next(iter(site_matches.values()))
            site_id = 'site:' + r['coordinate_candidate_id']
            label = r['sample_label'] or r['horizon_label']
            profile_id = f"profile:{clean_id(site_id)}:{clean_id(label)}"
            horizon_id = None
            if r['horizon_label'] or r['depth_top_cm'] is not None:
                horizon_id = f"horizon:{clean_id(profile_id)}:{clean_id(r['horizon_label'] or str(r['depth_top_cm']))}"
            sample_id = f"sample:{clean_id(candidate_id)}"
            analysis_id = f"analysis:{clean_id(candidate_id)}"
            measurement_id = f"measurement:{clean_id(candidate_id)}"
            con.execute('''INSERT INTO profile(profile_id,site_id,profile_label,notes)
                           VALUES(?,?,?,?) ON CONFLICT(profile_id) DO NOTHING''',
                        (profile_id, site_id, label,
                         'Auto-promoted only after explicit label-level coordinate linkage.'))
            if horizon_id:
                con.execute('''INSERT INTO horizon(horizon_id,profile_id,horizon_label,depth_top_cm,depth_bottom_cm)
                               VALUES(?,?,?,?,?) ON CONFLICT(horizon_id) DO NOTHING''',
                            (horizon_id, profile_id, r['horizon_label'], r['depth_top_cm'], r['depth_bottom_cm']))
            con.execute('''INSERT INTO sample(sample_id,site_id,profile_id,horizon_id,sample_label,depth_top_cm,depth_bottom_cm,notes)
                           VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(sample_id) DO NOTHING''',
                        (sample_id, site_id, profile_id, horizon_id, r['sample_label'],
                         r['depth_top_cm'], r['depth_bottom_cm'],
                         'Auto-promoted from a prose candidate with direct label-to-coordinate evidence.'))
            con.execute('''INSERT INTO sample_evidence(sample_id,artifact_id,extraction_id,evidence_text)
                           VALUES(?,?,?,?) ON CONFLICT(sample_id,artifact_id) DO UPDATE SET
                             extraction_id=excluded.extraction_id,evidence_text=excluded.evidence_text''',
                        (sample_id, r['artifact_id'], r['extraction_id'], r['context_text']))
            con.execute('''INSERT INTO laboratory_analysis(analysis_id,sample_id,analysis_label,method_raw,evidence_artifact_id,evidence_extraction_id)
                           VALUES(?,?,?,?,?,?) ON CONFLICT(analysis_id) DO NOTHING''',
                        (analysis_id, sample_id, 'Auto-staged analytical observation', r['method_raw'],
                         r['artifact_id'], r['extraction_id']))
            con.execute('''INSERT INTO measurement(measurement_id,site_id,profile_id,horizon_id,property_id,value_num,value_text,
                              unit_raw,unit_normalized,method_raw,qa_status,evidence_artifact_id,evidence_extraction_id,evidence_locator)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(measurement_id) DO UPDATE SET
                             value_num=excluded.value_num,value_text=excluded.value_text,unit_raw=excluded.unit_raw,
                             unit_normalized=excluded.unit_normalized,method_raw=excluded.method_raw,qa_status=excluded.qa_status,
                             evidence_locator=excluded.evidence_locator''',
                        (measurement_id, site_id, profile_id, horizon_id, r['property_id'], r['value_normalized'], r['value_text'],
                         r['unit_raw'], r['unit_normalized'], r['method_raw'], 'accepted', r['artifact_id'], r['extraction_id'],
                         f"prose measurement_candidate={candidate_id}; coordinate_candidate={r['coordinate_candidate_id']}"))
            con.execute('''INSERT INTO laboratory_analysis_measurement(analysis_id,measurement_id)
                           VALUES(?,?) ON CONFLICT(analysis_id,measurement_id) DO NOTHING''',
                        (analysis_id, measurement_id))
            con.execute("UPDATE measurement_candidate SET status='accepted' WHERE candidate_id=?", (candidate_id,))
            stats['promoted_measurements'] += 1
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
