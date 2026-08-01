#!/usr/bin/env python3
"""Map printed P2O5/K2O mass fractions to distinct oxide properties."""
from __future__ import annotations
import argparse,json,sqlite3
from pathlib import Path
from normalize_measurement_candidates import convert
DOC='springer:10.1134_S1064229320050105'
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args();n=0
 with sqlite3.connect(a.db) as c:
  for pid,name in [('phosphorus_pentoxide','phosphorus pentoxide (P2O5)'),('potassium_oxide','potassium oxide (K2O)')]:
   c.execute("insert into property_definition(property_id,canonical_name,category,canonical_unit,description) values(?,?, 'elemental_oxide','%','Mass fraction of oxide in ignited sample, as printed in source table.') on conflict(property_id) do nothing",(pid,name))
  rows=c.execute("""select t.candidate_id,t.property_id from table_measurement_candidate t join source_artifact a on a.artifact_id=t.artifact_id where a.document_id=? and t.property_id in ('available_phosphorus','available_potassium','phosphorus_pentoxide','potassium_oxide')""",(DOC,)).fetchall();n=len(rows)
  if not a.dry_run:
   for cid,pid in rows:
    new_pid='phosphorus_pentoxide' if pid in ('available_phosphorus','phosphorus_pentoxide') else 'potassium_oxide'
    c.execute('update table_measurement_candidate set property_id=?,unit_raw=\"%\" where candidate_id=?',(new_pid,cid))
    value=c.execute('select value_num from table_measurement_candidate where candidate_id=?',(cid,)).fetchone()[0]
    canonical=c.execute('select canonical_unit from property_definition where property_id=?',(new_pid,)).fetchone()[0]
    normalized,unit,status,warning=convert(value,'%',canonical,new_pid)
    c.execute("""insert into table_measurement_candidate_normalization
      (candidate_id,value_normalized,unit_normalized,normalization_status,warning,normalizer_version)
      values(?,?,?,?,?,'v1') on conflict(candidate_id) do update set
      value_normalized=excluded.value_normalized,unit_normalized=excluded.unit_normalized,
      normalization_status=excluded.normalization_status,warning=excluded.warning,
      normalizer_version=excluded.normalizer_version,normalized_at=CURRENT_TIMESTAMP""",
      (cid,normalized,unit,status,warning))
   c.commit()
 print(json.dumps({'reclassified':n},ensure_ascii=False))
if __name__=='__main__':main()
