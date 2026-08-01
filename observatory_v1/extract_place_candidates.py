#!/usr/bin/env python3
"""Stage administrative-place mentions from text; do not infer coordinates."""
from __future__ import annotations
import argparse, json, re, sqlite3
from pathlib import Path
from ingest_pochvovedenie_text import ctx

# Keep the reported form.  Geocoding has its own audited, cached stage.
DISTRICT = re.compile(
    r'\b(?:[A-Z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+){0,3}\s+(?:district|raion)|'
    r'[А-ЯЁ][А-Яа-яЁё\-]+(?:\s+[А-ЯЁ][А-Яа-яЁё\-]+){0,3}\s+(?:район(?:е|а|у|ом)?))\b'
)
REGION = re.compile(r'\b(?:[A-Z][A-Za-z\-]+(?:\s+[A-Z][A-Za-z\-]+){0,3}\s+(?:Oblast|Krai|Republic)|[А-ЯЁ][А-Яа-яЁё\-]+(?:\s+[А-ЯЁ][А-Яа-яЁё\-]+){0,3}\s+(?:област[ьи]|кра[ея]|республик[аи]))\b')

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--text-dir',type=Path,required=True);p.add_argument('--corpus',choices=('springer','pochvovedenie'),required=True);p.add_argument('--db',type=Path,required=True);p.add_argument('--commit-every',type=int,default=50);a=p.parse_args()
 stats={'texts':0,'districts':0,'regions':0,'missing_document':0}
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON')
  for no,path in enumerate(sorted(a.text_dir.glob('*.txt')),start=1):
   doc=f'{a.corpus}:{path.stem}'
   row=c.execute("SELECT e.extraction_id FROM extraction e JOIN source_artifact s ON s.artifact_id=e.artifact_id WHERE s.document_id=? AND s.artifact_type='text' ORDER BY e.extraction_id LIMIT 1",(doc,)).fetchone()
   if not row:stats['missing_document']+=1;continue
   text=path.read_text(encoding='utf-8',errors='replace');i=0
   for level,pattern,key in [('district',DISTRICT,'districts'),('region',REGION,'regions')]:
    for m in pattern.finditer(text):
     c.execute('''INSERT INTO place_candidate(candidate_id,extraction_id,place_text,administrative_level,context_text,status)
                  VALUES(?,?,?,?,?,"unreviewed")
                  ON CONFLICT(candidate_id) DO UPDATE SET
                    place_text=excluded.place_text,
                    administrative_level=excluded.administrative_level,
                    context_text=excluded.context_text,
                    status=place_candidate.status''',
               (f'{row[0]}:place:{i}',row[0],m.group(0),level,ctx(text,m.start(),m.end())))
     i+=1;stats[key]+=1
   stats['texts']+=1
   if no%a.commit_every==0:c.commit()
  c.commit()
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
