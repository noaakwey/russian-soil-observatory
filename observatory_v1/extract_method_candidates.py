#!/usr/bin/env python3
"""Extract named laboratory methods from full-text evidence into a review layer."""
from __future__ import annotations
import argparse,json,re,sqlite3
from pathlib import Path
from ingest_pochvovedenie_text import ctx

PATTERNS = {
 'ph_potentiometric': r'potentiometr\w*|потенциометрическ\w*',
 'soc_tyurin': r'Тюрин\w*|Tyurin\w*', 'soc_walkley_black': r'Walkley[ -]?Black',
 'soc_dry_combustion': r'dry combustion|elemental analy[sz]er|сух(?:ое|им) сжиган',
 'nitrogen_kjeldahl': r'Kjeldahl|Кьельдал', 'nitrogen_dumas': r'\bDumas\b|Дюма',
 'phosphorus_olsen': r'\bOlsen\b|Ольсен', 'phosphorus_bray': r'\bBray\b|Брэ[йи]',
 'mehlich_3': r'Mehlich[ -]?3|Мехлич', 'chirikov': r'Чириков\w*|Chirikov\w*', 'machigin': r'Мачигин\w*|Machigin\w*',
 'cec_ammonium_acetate': r'ammonium acetate|ацетат(?:а)? аммони', 'particle_pipette': r'pipette method|пипеточн\w* метод',
 'particle_laser': r'laser diffraction|лазерн\w* дифракц', 'metals_aas': r'atomic absorption|атомно-абсорбцион',
 'metals_icp_oes': r'ICP[ -]?(?:OES|AES)|индуктивно-связанн\w* плазм\w*', 'metals_icp_ms': r'ICP[ -]?MS',
 'xrf': r'XRF|рентгенофлуоресцент', 'loss_on_ignition': r'loss on ignition|потер[яи] при прокаливан'
}
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--text-dir',type=Path,required=True); p.add_argument('--corpus',choices=('springer','pochvovedenie'),required=True); p.add_argument('--db',type=Path,required=True); p.add_argument('--commit-every',type=int,default=50); a=p.parse_args()
 stats={'texts':0,'methods':0,'missing_document':0}
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON')
  for no,path in enumerate(sorted(a.text_dir.glob('*.txt')),start=1):
   doc=f'{a.corpus}:{path.stem}'
   r=c.execute("SELECT e.extraction_id FROM extraction e JOIN source_artifact s ON s.artifact_id=e.artifact_id WHERE s.document_id=? AND s.artifact_type='text' ORDER BY e.extraction_id LIMIT 1",(doc,)).fetchone()
   if not r: stats['missing_document']+=1; continue
   text=path.read_text(encoding='utf-8',errors='replace'); i=0
   for method_id,pattern in PATTERNS.items():
    for m in re.finditer(pattern,text,re.I):
     c.execute("INSERT OR REPLACE INTO method_candidate VALUES(?,?,?,?,?,'unreviewed')",(f'{r[0]}:method:{i}',r[0],method_id,m.group(0),ctx(text,m.start(),m.end())))
     i+=1;stats['methods']+=1
   stats['texts']+=1
   if no%a.commit_every==0:c.commit()
  c.commit()
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
