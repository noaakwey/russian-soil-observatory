#!/usr/bin/env python3
"""Remove the first automated promotion before rebuilding text candidates.

This affects only rows created by the experimental automatic promoter.  Raw
OCR cells, table candidates, coordinates, sites and source artifacts remain.
"""
import argparse, json, sqlite3
from pathlib import Path

p=argparse.ArgumentParser(); p.add_argument('--db', type=Path, required=True); a=p.parse_args()
with sqlite3.connect(a.db) as c:
 c.execute('PRAGMA foreign_keys=ON')
 before={t:c.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in ('measurement','laboratory_analysis','sample','profile')}
 c.execute("DELETE FROM laboratory_analysis_measurement WHERE measurement_id LIKE 'measurement:%'")
 c.execute("DELETE FROM laboratory_analysis WHERE analysis_id LIKE 'analysis:%'")
 c.execute("DELETE FROM measurement WHERE measurement_id LIKE 'measurement:%'")
 c.execute("DELETE FROM sample_evidence WHERE sample_id LIKE 'sample:%'")
 c.execute("DELETE FROM sample WHERE sample_id LIKE 'sample:%'")
 c.execute("DELETE FROM horizon WHERE horizon_id LIKE 'horizon:%'")
 c.execute("DELETE FROM profile WHERE profile_id LIKE 'profile:%'")
 c.execute('DELETE FROM measurement_candidate_normalization')
 c.execute('DELETE FROM measurement_candidate')
 c.commit()
 print(json.dumps({'before':before,'measurement_candidates_cleared':True},ensure_ascii=False))
