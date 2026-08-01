#!/usr/bin/env python3
"""Export raw table cells from single-coordinate papers that need human review.

Nothing is deleted: this makes every non-promoted numeric cell inspectable with
its source table location and the exact reason automatic normalization stopped.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

from normalize_measurement_candidates import convert
from stage_supported_table_measurements import observation_reason, plausible, query_for


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument('--db', type=Path, required=True); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); rows = []
    with sqlite3.connect(a.db) as con:
        q = query_for('reported')
        cur = con.execute(q); cols = [x[0] for x in cur.description]
        for row in cur:
            r = dict(zip(cols, row))
            value, unit, status, warning = convert(r['value_num'], r['unit_raw'], r['canonical_unit'], r['property_id'])
            if status not in {'exact','converted'}: reason = f'normalization_{status}'
            elif not plausible(value, unit): reason = 'implausible_value'
            else: reason = observation_reason(r, value, unit)
            if reason:
                rows.append({**r, 'review_reason': reason, 'normalized_candidate_value': value,
                             'normalized_candidate_unit': unit, 'normalization_note': warning})
        q_no_unit = q.replace("WHERE t.status='unreviewed' AND t.value_num IS NOT NULL AND t.unit_raw IS NOT NULL", "WHERE t.status='unreviewed' AND t.value_num IS NOT NULL AND (t.unit_raw IS NULL OR trim(t.unit_raw)='')")
        cur = con.execute(q_no_unit); cols = [x[0] for x in cur.description]
        for row in cur:
            r = dict(zip(cols, row)); rows.append({**r, 'review_reason': 'source_unit_missing',
                'normalized_candidate_value': None, 'normalized_candidate_unit': None,
                'normalization_note': 'Raw numeric cell retained; unit cannot be inferred automatically.'})
    fields = list(rows[0]) if rows else ['candidate_id']
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('w', newline='', encoding='utf-8') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
    print(json.dumps({'review_candidates':len(rows)},ensure_ascii=False))
if __name__=='__main__':main()
