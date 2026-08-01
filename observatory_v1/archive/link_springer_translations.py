#!/usr/bin/env python3
"""Link Springer translations to Pochvovedenie originals using printed evidence.

No documents are merged.  A link is created only when the Springer paper
itself gives the original journal year/issue and exactly one local catalog
record agrees on year, issue and first-author surname.
"""
from __future__ import annotations
import argparse, json, re, sqlite3
from pathlib import Path

ORIGINAL = re.compile(
    r'Original Russian Text\s*©\s*([^,\n]+).*?published in Pochvovedenie,\s*(\d{4}),\s*No\.\s*(\d+)',
    re.I | re.S,
)
DOI = re.compile(r'\bDOI:\s*(10\.\d{4,9}/[^\s]+)', re.I)

def surname(authors: str) -> str | None:
    # A.A. Dymov -> Dymov; Cyrillic is retained too.
    words = re.findall(r'[A-Za-zА-Яа-яЁё-]{3,}', authors)
    return words[-1] if words else None

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--text-dir',type=Path,required=True);p.add_argument('--db',type=Path,required=True);a=p.parse_args()
    stats={'files':0,'printed_original_note':0,'linked_candidate':0,'ambiguous':0,'no_catalog_match':0,'doi_updated':0}
    with sqlite3.connect(a.db) as c:
      for f in sorted(a.text_dir.glob('*.txt')):
        doc=f'springer:{f.stem}'; text=f.read_text(encoding='utf-8',errors='replace'); stats['files']+=1
        doi=DOI.search(text)
        if doi:
          cur=c.execute('UPDATE document SET doi=COALESCE(doi,?) WHERE document_id=?',(doi.group(1).rstrip('.'),doc));stats['doi_updated']+=cur.rowcount > 0
        m=ORIGINAL.search(text)
        if not m: continue
        stats['printed_original_note']+=1
        author,year,issue=m.groups(); last=surname(author)
        if not last:
          stats['no_catalog_match']+=1;continue
        # Pochved catalog IDs encode issue/year/first author (e.g.
        # Pochved2013002Dymov); constrain all three components.
        rows=c.execute('SELECT document_id FROM document WHERE corpus="pochvovedenie" AND document_id LIKE ?', (f'%Pochved{year}{int(issue):03d}{last}%',)).fetchall()
        if len(rows)==1:
          target=rows[0][0]
          note=f'Printed in Springer: Original Russian Text © {author}; published in Pochvovedenie, {year}, No. {issue}.'
          c.execute('INSERT OR REPLACE INTO document_link(document_id_a,document_id_b,relation,confidence,evidence_note) VALUES(?, ?, "translation_of", "candidate", ?)',(doc,target,note))
          stats['linked_candidate']+=1
        elif len(rows)>1: stats['ambiguous']+=1
        else: stats['no_catalog_match']+=1
      c.commit()
    print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
