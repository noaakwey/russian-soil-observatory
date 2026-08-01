#!/usr/bin/env python3
"""Curated source-header correction for Table 4, Kuchiger Hot Springs.

The paper labels the column ``aCa / Ca2+`` as ion activity in 30% soil
paste, mmol/L.  It is not total calcium (mg/kg), so the candidates are mapped
to a separate property and retain this printed unit.
"""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path
DOC='springer:10.1134_S106422931912007X'
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args();n=0
 with sqlite3.connect(a.db) as c:
  c.execute("""INSERT INTO property_definition(property_id,canonical_name,category,canonical_unit,description)
   VALUES('calcium_ion_activity_paste','calcium ion activity in soil paste','soil_solution','mmol/L','Activity of Ca2+ in a soil paste; not total calcium concentration.')
   ON CONFLICT(property_id) DO NOTHING""")
  rows=c.execute("""SELECT t.candidate_id FROM table_measurement_candidate t JOIN source_artifact x ON x.artifact_id=t.artifact_id
   WHERE x.document_id=? AND t.row_label_raw LIKE 'RF-1-%' AND t.property_id='calcium' AND t.property_header_raw LIKE '%Ca%'""",(DOC,)).fetchall()
  n=len(rows)
  if not a.dry_run:
   for (cid,) in rows:
    c.execute("UPDATE table_measurement_candidate SET property_id='calcium_ion_activity_paste',unit_raw='mmol/L' WHERE candidate_id=?",(cid,))
   c.commit()
 print(json.dumps({'reclassified':n},ensure_ascii=False))
if __name__=='__main__':main()
