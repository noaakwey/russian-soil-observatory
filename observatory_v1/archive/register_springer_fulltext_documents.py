#!/usr/bin/env python3
"""Register full-text Springer PDFs absent from the OCR-derived document list."""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--text-dir',type=Path,required=True);p.add_argument('--db',type=Path,required=True);a=p.parse_args();stats={'registered':0,'existing':0}
 with sqlite3.connect(a.db) as c:
  for text in sorted(a.text_dir.glob('*.txt')):
   doc=f'springer:{text.stem}'
   cur=c.execute("INSERT INTO document(document_id,corpus,language,source_path) VALUES(?, 'springer', 'en', ?) ON CONFLICT(document_id) DO NOTHING",(doc,f'springer_fulltext:{text.with_suffix(".pdf").name}'))
   if cur.rowcount:stats['registered']+=1
   else:stats['existing']+=1
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
