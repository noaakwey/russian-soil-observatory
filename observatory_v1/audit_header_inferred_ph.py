#!/usr/bin/env python3
"""Count pH table cells where the only unit evidence is an explicit pH header.

This read-only diagnostic intentionally excludes every other property with a
missing unit.  ``pH H2O`` / ``water pH`` defines a pH scale, so it can be
handled transparently as a header-derived unit; Ca, Mg, nutrients, etc. cannot.
"""
from __future__ import annotations
import argparse, json, re, sqlite3
from collections import Counter
from pathlib import Path
from stage_supported_table_measurements import NON_MEASUREMENT_MARKERS, observation_reason, plausible


SQL = """
WITH one AS (
 SELECT d.document_id, MIN(se.site_id) AS site_id FROM document d
 JOIN source_artifact a ON a.document_id=d.document_id
 JOIN site_evidence se ON se.artifact_id=a.artifact_id JOIN site s ON s.site_id=se.site_id
 WHERE s.spatial_confidence IN ('exact','reported') GROUP BY d.document_id HAVING COUNT(DISTINCT s.site_id)=1
)
SELECT t.*, d.document_id FROM table_measurement_candidate t
JOIN source_artifact a ON a.artifact_id=t.artifact_id JOIN document d ON d.document_id=a.document_id
JOIN one ON one.document_id=d.document_id
WHERE t.status='unreviewed' AND t.property_id='ph_h2o'
  AND (t.unit_raw IS NULL OR trim(t.unit_raw)='')
"""

def main():
 p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); a=p.parse_args(); stats=Counter(); examples={}
 with sqlite3.connect(a.db) as c:
  cols=[x[0] for x in c.execute(SQL).description]
  for row in c.execute(SQL):
   r=dict(zip(cols,row)); header=r['property_header_raw'] or ''
   if not re.search(r'\b(?:p\s*h|water\s+p\s*h|p\s*h\s*water)\b',header,re.I):
    stats['header_not_explicit_ph']+=1;continue
   reason=observation_reason(r,float(r['value_num']),'pH') or 'would_stage_header_inferred_ph'
   if not plausible(float(r['value_num']),'pH'):reason='implausible_value'
   stats[reason]+=1;examples.setdefault(reason,{k:r.get(k) for k in ('candidate_id','document_id','property_header_raw','value_num','row_label_raw')})
 print(json.dumps({'stats':dict(stats),'examples':examples},ensure_ascii=False))
if __name__=='__main__':main()
