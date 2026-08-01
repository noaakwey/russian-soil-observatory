#!/usr/bin/env python3
"""Locate PDF text pages likely to contain a study-area map or site scheme.

This is an inventory only.  It creates no coordinate candidate; its output is
the finite, reproducible page queue for targeted figure OCR.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path

MAP_CAPTION = re.compile(
    r"(?:\bfig(?:ure)?\.?\s*\d+[.:]?[^\n\f]{0,280}?(?:map|study area|location|sampling|site)|"
    r"\bрис(?:унок|\.)?\s*\d+[.:]?[^\n\f]{0,280}?(?:карт|район|место|схем|располож|участк))",
    re.I,
)


def sources(springer: Path, pochvovedenie: Path):
    for p in sorted(springer.glob("*.txt")):
        yield "springer", p, f"springer:{p.stem}"
    for p in sorted(pochvovedenie.glob("*.txt")):
        yield "pochvovedenie", p, f"pochvovedenie:{p.stem}"


def clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--springer-text-dir',type=Path,required=True); p.add_argument('--pochvovedenie-text-dir',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--db',type=Path); p.add_argument('--without-reported-sites',action='store_true'); a=p.parse_args()
    if a.without_reported_sites and not a.db:
        raise SystemExit('--without-reported-sites requires --db')
    mapped: set[str] = set()
    if a.db:
        with sqlite3.connect(a.db) as con:
            mapped={r[0] for r in con.execute("""SELECT DISTINCT d.document_id FROM document d
                JOIN source_artifact a ON a.document_id=d.document_id JOIN site_evidence se ON se.artifact_id=a.artifact_id
                JOIN site s ON s.site_id=se.site_id WHERE s.spatial_confidence IN ('exact','reported')""")}
    rows=[]
    for corpus,path,document_id in sources(a.springer_text_dir,a.pochvovedenie_text_dir):
        if a.without_reported_sites and document_id in mapped:
            continue
        pages=path.read_text(encoding='utf-8',errors='replace').split('\f')
        for page_number,page in enumerate(pages,start=1):
            matches=list(MAP_CAPTION.finditer(page))
            if matches:
                rows.append({'corpus':corpus,'document_id':document_id,'text_path':str(path),'page':page_number,'caption_fragment':clean(matches[0].group(0))[:450]})
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['corpus','document_id','text_path','page','caption_fragment']);w.writeheader();w.writerows(rows)
    print({'candidate_pages':len(rows),'documents':len({r['document_id'] for r in rows}),'excluded_documents_with_reported_sites':len(mapped) if a.without_reported_sites else 0})

if __name__=='__main__':main()
