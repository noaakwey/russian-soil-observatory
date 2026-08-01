#!/usr/bin/env python3
"""Stage OCR values only when a table row begins with an explicit pit label."""
from __future__ import annotations
import argparse,hashlib,json,sqlite3
from collections import Counter
from pathlib import Path
from normalize_measurement_candidates import convert
def tok(x): return hashlib.sha1(x.encode()).hexdigest()[:20]
SQL="""SELECT p.profile_id,p.site_id,p.profile_label,t.candidate_id,t.artifact_id,t.row_index,t.column_index,t.property_id,t.property_header_raw,t.value_num,t.unit_raw,t.row_label_raw,t.horizon_label,t.depth_top_cm,t.depth_bottom_cm,pd.canonical_unit
FROM profile p JOIN profile_evidence pe ON pe.profile_id=p.profile_id JOIN source_artifact pa ON pa.artifact_id=pe.artifact_id
JOIN table_measurement_candidate t ON t.artifact_id IN (SELECT a.artifact_id FROM source_artifact a WHERE a.document_id=pa.document_id)
JOIN property_definition pd ON pd.property_id=t.property_id
WHERE p.profile_id LIKE 'profile:explicit_pit:%' AND t.status='unreviewed' AND t.value_num IS NOT NULL AND t.unit_raw IS NOT NULL AND t.row_label_raw LIKE p.profile_label || '%'"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args();s=Counter()
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON');cols=[x[0] for x in c.execute(SQL).description]
  for row in c.execute(SQL):
   r=dict(zip(cols,row)); val,unit,status,warn=convert(r['value_num'],r['unit_raw'],r['canonical_unit'],r['property_id'])
   if status not in ('exact','converted'):s['normalization_'+status]+=1;continue
   sample='sample:explicit_table:'+tok(r['candidate_id']);analysis='analysis:explicit_table:'+tok(r['candidate_id']);mid='measurement:explicit_table:'+tok(r['candidate_id'])
   ev=json.dumps({'table_candidate_id':r['candidate_id'],'spatial_linkage':'explicit_profile_label_to_coordinate','profile_label':r['profile_label']},ensure_ascii=False)
   if not a.dry_run:
    c.execute("insert into sample(sample_id,site_id,profile_id,sample_label,depth_top_cm,depth_bottom_cm,notes) values(?,?,?,?,?,?,?) on conflict(sample_id) do nothing",(sample,r['site_id'],r['profile_id'],r['row_label_raw'],r['depth_top_cm'],r['depth_bottom_cm'],'OCR row with explicit profile-label-to-coordinate linkage.'))
    c.execute("insert into sample_evidence(sample_id,artifact_id,evidence_text) values(?,?,?) on conflict(sample_id,artifact_id) do update set evidence_text=excluded.evidence_text",(sample,r['artifact_id'],ev))
    c.execute("insert into laboratory_analysis(analysis_id,sample_id,analysis_label,evidence_artifact_id) values(?,?,?,?) on conflict(analysis_id) do nothing",(analysis,sample,'OCR table row',r['artifact_id']))
    c.execute("insert into measurement(measurement_id,site_id,profile_id,property_id,value_num,unit_raw,unit_normalized,qa_status,evidence_artifact_id,evidence_locator) values(?,?,?,?,?,?,?,'accepted',?,?) on conflict(measurement_id) do update set qa_status='accepted'",(mid,r['site_id'],r['profile_id'],r['property_id'],val,r['unit_raw'],unit,r['artifact_id'],ev))
    c.execute("insert into laboratory_analysis_measurement(analysis_id,measurement_id) values(?,?) on conflict do nothing",(analysis,mid));c.execute("update table_measurement_candidate set status='accepted' where candidate_id=?",(r['candidate_id'],))
   s['staged_accepted']+=1
  if not a.dry_run:c.commit()
 print(dict(s))
if __name__=='__main__':main()
