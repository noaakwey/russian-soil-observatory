#!/usr/bin/env python3
"""Create direct profiles when a source phrase prints ``Pit LABEL (coordinate)``.

No fuzzy geographical match is used: a parsed coordinate must equal an already
country-validated location candidate from the same text artifact.
"""
from __future__ import annotations
import argparse, hashlib, json, re, sqlite3
from pathlib import Path
from audit_profile_context_coordinate import coords

# Field identifiers may be ``7``, ``Т6а``, ``1Г-05`` or ``LG-10-20``.
# A bare word is deliberately not a profile label.
LABEL=re.compile(r"\b(?:Pit|Soil\s+pit|Point|Plot|Site|Sampling\s+point|Borehole|Core|разрез|точка|площадка|участок|скважина|керн|ТП)\s*(?:No\.?|№)?\s*([A-Za-zА-Яа-я]{0,8}-?\d+[A-Za-zА-Яа-я]?(?:[-–][A-Za-zА-Яа-я0-9]+)*)",re.I)
def ident(*x): return hashlib.sha1('\x1f'.join(x).encode()).hexdigest()[:20]
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args(); stats={'phrases':0,'profiles':0,'missing_site':0}
 with sqlite3.connect(a.db) as c:
  c.row_factory=sqlite3.Row;c.execute('PRAGMA foreign_keys=ON')
  c.execute("""CREATE TABLE IF NOT EXISTS profile_evidence(profile_id TEXT NOT NULL REFERENCES profile(profile_id),artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),extraction_id TEXT REFERENCES extraction(extraction_id),evidence_text TEXT NOT NULL,evidence_kind TEXT NOT NULL CHECK(evidence_kind IN ('profile_description','table_header','table_row')),PRIMARY KEY(profile_id,artifact_id,evidence_kind))""")
  rows=c.execute("""select e.extraction_id,a.artifact_id,a.source_path,d.document_id from extraction e join source_artifact a on a.artifact_id=e.artifact_id join document d on d.document_id=a.document_id where a.artifact_type='text'""").fetchall()
  for r in rows:
   try: text=Path(r['source_path']).read_text(encoding='utf8',errors='replace')
   except OSError: continue
   cand=c.execute("""select lc.candidate_id,lc.latitude,lc.longitude from location_candidate lc join location_validation lv on lv.candidate_id=lc.candidate_id where lc.extraction_id=? and lv.country_code='RU' and lv.result='inside'""",(r['extraction_id'],)).fetchall()
   for m in LABEL.finditer(text):
    block=text[m.start():m.start()+260]; hits=[]
    for lat,lon,_,_ in coords(block):
     hits += [(x['candidate_id'],lat,lon) for x in cand if abs(x['latitude']-lat)<1e-6 and abs(x['longitude']-lon)<1e-6]
    # The same printed coordinate can have two extraction provenance records
    # (e.g. older and cardinal degree-minute readers).  This is not two field
    # sites: prefer the already promoted candidate; otherwise stay strict.
    by_candidate={x[0]: x for x in hits}
    promoted=[x for x in by_candidate.values() if c.execute('select 1 from site where site_id=?',('site:'+x[0],)).fetchone()]
    if len(promoted)==1:
     cid,lat,lon=promoted[0]
    elif len(by_candidate)==1:
     cid,lat,lon=next(iter(by_candidate.values()))
    else:
     continue
    site='site:'+cid
    if not c.execute('select 1 from site where site_id=?',(site,)).fetchone(): stats['missing_site']+=1;continue
    stats['phrases']+=1;pid='profile:explicit_pit:'+ident(r['document_id'],site,m.group(1))
    if not a.dry_run:
     ev=json.dumps({'spatial_linkage':'explicit_labeled_pit_coordinate','coordinate_candidate_id':cid},ensure_ascii=False)+'\n'+block
     c.execute("insert into profile(profile_id,site_id,profile_label,notes) values(?,?,?,?) on conflict(profile_id) do nothing",(pid,site,m.group(1),'Explicit pit label and author-reported coordinate in one source phrase.'))
     c.execute("insert into profile_evidence(profile_id,artifact_id,extraction_id,evidence_text,evidence_kind) values(?,?,?,?, 'profile_description') on conflict(profile_id,artifact_id,evidence_kind) do update set evidence_text=excluded.evidence_text",(pid,r['artifact_id'],r['extraction_id'],ev))
    stats['profiles']+=1
  if not a.dry_run:c.commit()
 print(stats)
if __name__=='__main__':main()
