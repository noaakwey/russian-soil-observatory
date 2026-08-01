#!/usr/bin/env python3
"""Explain every unreviewed table candidate eligible for a single reported site.

This is a diagnostic companion to ``stage_supported_table_measurements.py``;
it does not mutate any table or status.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from normalize_measurement_candidates import convert
from stage_supported_table_measurements import observation_reason, plausible, query_for


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--spatial-tier', choices=('reported', 'geocoded'), default='reported')
    a = p.parse_args()
    stats: Counter[str] = Counter()
    examples: dict[str, dict] = {}
    with sqlite3.connect(a.db) as c:
        cur = c.execute(query_for(a.spatial_tier))
        cols = [x[0] for x in cur.description]
        for row in cur:
            rec = dict(zip(cols, row))
            value, unit, status, warning = convert(rec['value_num'], rec['unit_raw'], rec['canonical_unit'], rec['property_id'])
            reason = f'normalization_{status}'
            if status in {'exact', 'converted'}:
                if not plausible(value, unit):
                    reason = 'implausible_value'
                else:
                    reason = observation_reason(rec, value, unit) or 'would_stage'
            stats[reason] += 1
            examples.setdefault(reason, {k: rec.get(k) for k in ('candidate_id','document_id','property_id','property_header_raw','value_num','unit_raw','row_label_raw')})
        no_unit = c.execute("""
          WITH one AS (
            SELECT d.document_id FROM document d JOIN source_artifact a ON a.document_id=d.document_id
            JOIN site_evidence se ON se.artifact_id=a.artifact_id JOIN site s ON s.site_id=se.site_id
            WHERE s.spatial_confidence {} GROUP BY d.document_id HAVING COUNT(DISTINCT s.site_id)=1
          )
          SELECT COUNT(*) FROM table_measurement_candidate t JOIN source_artifact a ON a.artifact_id=t.artifact_id
          JOIN one ON one.document_id=a.document_id WHERE t.status='unreviewed' AND (t.unit_raw IS NULL OR trim(t.unit_raw)='')
        """.format("IN ('exact','reported')" if a.spatial_tier == 'reported' else "='geocoded'")).fetchone()[0]
    print(json.dumps({'spatial_tier': a.spatial_tier, 'eligible_with_unit': sum(stats.values()), 'reasons': dict(stats), 'no_unit_single_site': no_unit, 'examples': examples}, ensure_ascii=False))


if __name__ == '__main__':
    main()
