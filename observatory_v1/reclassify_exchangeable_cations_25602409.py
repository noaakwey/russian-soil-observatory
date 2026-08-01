#!/usr/bin/env python3
"""Curated header-based mapping of exchangeable Ca/Mg in one source table."""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path
DOC='springer:10.1134_S1064229325602409'
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args();n=0
 with sqlite3.connect(a.db) as c:
  for pid,name in [('exchangeable_calcium','exchangeable calcium'),('exchangeable_magnesium','exchangeable magnesium')]:
   c.execute("insert into property_definition(property_id,canonical_name,category,canonical_unit,description) values(?,?, 'exchange','mol(+)/kg',?) on conflict(property_id) do nothing",(pid,name,'Exchangeable cation charge basis as printed in source table.'))
  rows=c.execute("""select t.candidate_id,t.property_id from table_measurement_candidate t join source_artifact x on x.artifact_id=t.artifact_id
   where x.document_id=? and t.row_label_raw glob '[0-9]*-18*' and t.property_id in ('calcium','magnesium')""",(DOC,)).fetchall();n=len(rows)
  if not a.dry_run:
   for cid,pid in rows:
    new='exchangeable_calcium' if pid=='calcium' else 'exchangeable_magnesium'
    c.execute('update table_measurement_candidate set property_id=?,unit_raw=\"mol(+)/kg\" where candidate_id=?',(new,cid))
   c.commit()
 print(json.dumps({'reclassified':n},ensure_ascii=False))
if __name__=='__main__':main()
