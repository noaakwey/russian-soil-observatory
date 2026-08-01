#!/usr/bin/env python3
"""Promote only explicit Russian soil-study coordinates to operational sites.

This deliberately creates no measurements.  A coordinate is a usable site
only when it is inside Russia according to the pinned boundary and its own
source context explicitly refers to a soil/sample/profile/site observation.
"""
from __future__ import annotations
import argparse, json, re, sqlite3
from pathlib import Path

# English terms are complete words; Russian stems intentionally allow their
# grammatical endings.  The former ``почв\b`` form matched only the bare stem,
# silently rejecting "почва", "почвенные", "образцы" and "разрезы".
STUDY_CONTEXT = re.compile(
    r'(?:\b(?:soil|sample|profile|horizon|site|pit|section)\b|'
    r'почв\w*|образц\w*|разрез\w*|разр\.?(?=\s|\d)|профил\w*|'
    r'горизонт\w*|точк\w*|участк\w*|площадк\w*|отбор\w*|проб\w*|грунт\w*)',
    re.I,
)

SQL = '''
SELECT lc.candidate_id, lc.latitude, lc.longitude, lc.context_text, e.artifact_id
FROM location_candidate lc
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
JOIN extraction e ON e.extraction_id=lc.extraction_id
WHERE lv.country_code='RU' AND lv.result='inside'
'''

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args()
 stats={'validated_ru_coordinates':0,'promoted_sites':0,'not_soil_context':0}
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON')
  for candidate_id,lat,lon,context,artifact_id in c.execute(SQL):
   stats['validated_ru_coordinates']+=1
   if not STUDY_CONTEXT.search(context):
    stats['not_soil_context']+=1;continue
   site_id=f'site:{candidate_id}'
   if not a.dry_run:
    c.execute('''INSERT INTO site(site_id,country_code,name,latitude,longitude,spatial_precision_m,spatial_confidence,geometry_source)
                VALUES(?, 'RU', ?, ?, ?, NULL, 'reported', ?)
                ON CONFLICT(site_id) DO NOTHING''',
             (site_id, f'Reported study point {lat:.6f}, {lon:.6f}',lat,lon,
              'Explicit decimal coordinates in source; country checked against pinned Natural Earth boundary'))
    c.execute('INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind) VALUES(?,?,?,"coordinates")',(site_id,artifact_id,context))
    c.execute("UPDATE location_candidate SET status='accepted' WHERE candidate_id=?",(candidate_id,))
   stats['promoted_sites']+=1
  if not a.dry_run: c.commit()
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
