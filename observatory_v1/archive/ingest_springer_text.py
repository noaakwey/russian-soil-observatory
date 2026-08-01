#!/usr/bin/env python3
"""Stage property/location candidates from extracted Springer prose."""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path
from ingest_pochvovedenie_text import PROPS, VALUE, DEPTH, COORD, SAMPLE, HORIZON, METHOD, ctx, num

def main():
 p=argparse.ArgumentParser(); p.add_argument('--text-dir',type=Path,required=True); p.add_argument('--db',type=Path,required=True); p.add_argument('--commit-every',type=int,default=25); a=p.parse_args()
 stats={'texts':0,'property_candidates':0,'coordinate_candidates':0,'unknown_documents':0}
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON')
  for file_no, f in enumerate(sorted(a.text_dir.glob('*.txt')), start=1):
   doc=f'springer:{f.stem}'; aid=f'{doc}:text'; eid=f'{aid}:raw'; text=f.read_text(encoding='utf-8',errors='replace')
   if not c.execute('SELECT 1 FROM document WHERE document_id=?',(doc,)).fetchone(): stats['unknown_documents']+=1; continue
   c.execute("INSERT INTO source_artifact(artifact_id,document_id,artifact_type,source_path) VALUES(?,?,'text',?) ON CONFLICT(artifact_id) DO NOTHING",(aid,doc,str(f)))
   c.execute("INSERT INTO extraction(extraction_id,artifact_id,extractor,extractor_version,raw_text,parsed_json,status) VALUES(?,?, 'regex-candidate','v1',?,?,'parsed') ON CONFLICT(extraction_id) DO UPDATE SET raw_text=excluded.raw_text",(eid,aid,text,'{}'))
   i=0
   for prop,(_,_,pat) in PROPS.items():
    import re
    for m in re.finditer(pat,text,re.I):
     w=ctx(text,m.start(),m.end()); v=VALUE.search(w)
     if not v: continue
     d=DEPTH.search(w); sample=SAMPLE.search(w); horizon=HORIZON.search(w); method=METHOD.search(w); cid=f'{eid}:m:{i}'; i+=1
     c.execute("INSERT OR REPLACE INTO measurement_candidate VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",(cid,eid,prop,m.group(0),num(v.group(1)),None,v.group(2),method.group(0) if method else None,horizon.group(1) if horizon else None,num(d.group(1)) if d else None,num(d.group(2)) if d else None,sample.group(1) if sample else None,w,'unreviewed'))
     stats['property_candidates']+=1
   for j,m in enumerate(COORD.finditer(text)):
    lat,lon=num(m.group(1)),num(m.group(2))
    if lat<=90 and lon<=180: c.execute("INSERT OR REPLACE INTO location_candidate VALUES(?,?,?,?,?,?,?,?,?)",(f'{eid}:l:{j}',eid,lat,lon,None,None,'decimal_degrees',ctx(text,m.start(),m.end()),'unreviewed')); stats['coordinate_candidates']+=1
   stats['texts']+=1
   # A long initial corpus pass must not keep SQLite locked for its entire
   # duration. Every batch is internally consistent, and INSERT OR REPLACE
   # keeps a resumed pass idempotent.
   if file_no % a.commit_every == 0:
    c.commit()
  c.commit()
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__': main()
