#!/usr/bin/env python3
"""Flag implausible normalized OCR values without deleting or rewriting them.

The raw OCR cell remains the source of truth.  A flag is appended to the
normalization warning so exports can keep every reported value while scientific
summaries can explicitly separate values needing image/source verification.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path


RANGES = {
    "ph_h2o": (0.0, 14.0), "ph_kcl": (0.0, 14.0),
    "sand": (0.0, 100.0), "silt": (0.0, 100.0), "clay": (0.0, 100.0),
    "organic_matter": (0.0, 100.0), "bulk_density": (0.05, 3.5),
    "base_saturation": (0.0, 100.0), "porosity": (0.0, 100.0),
    "exchangeable_sodium_percentage": (0.0, 100.0),
}


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); p.add_argument('--dry-run',action='store_true'); a=p.parse_args()
    stats=Counter()
    with sqlite3.connect(a.db) as con:
        rows=con.execute("""SELECT n.candidate_id,n.value_normalized,n.warning,t.property_id
                           FROM table_measurement_candidate_normalization n
                           JOIN table_measurement_candidate t ON t.candidate_id=n.candidate_id
                           WHERE n.normalization_status IN ('exact','converted')
                             AND n.value_normalized IS NOT NULL""").fetchall()
        for cid,value,warning,pid in rows:
            bounds=RANGES.get(pid)
            if not bounds or bounds[0] <= value <= bounds[1]: continue
            marker=f'qc_implausible_range:{pid}:{bounds[0]}..{bounds[1]}'
            if warning and marker in warning: stats['already_flagged'] += 1; continue
            updated='; '.join(x for x in [warning,marker] if x)
            if not a.dry_run: con.execute('UPDATE table_measurement_candidate_normalization SET warning=? WHERE candidate_id=?',(updated,cid))
            stats[pid] += 1
        if not a.dry_run: con.commit()
    print(json.dumps(dict(stats),ensure_ascii=False))
if __name__=='__main__': main()
