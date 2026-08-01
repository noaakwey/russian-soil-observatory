#!/usr/bin/env python3
"""Stage header-grounded numeric candidates from OCR table matrices.

This is intentionally conservative: only a recognized property header above a
numeric cell yields a candidate; all candidates retain table row/column proof.
"""
from __future__ import annotations
import argparse, re, sqlite3
from collections import defaultdict
from pathlib import Path
from ingest_pochvovedenie_text import DEPTH, HORIZON, num
from table_property_patterns import SYMBOL_PROPERTIES, TABLE_PROPERTY_PATTERNS, normalize_header

UNIT = r'(?:mg\s*(?:CO2|TPF|NH4-N|PNP)?\s*/\s*kg\s*/\s*(?:day|d|h)|мг\s*/\s*кг\s*/\s*(?:сут|ч)|cmol\(?c?\)\s*/\s*kg|ммоль\s*/\s*кг|mmol\s*/\s*kg|mg\s*/\s*kg|мг\s*/\s*кг|g\s*/\s*kg|г\s*/\s*кг|g\s*/\s*l|г\s*/\s*л|mg\s*/\s*l|мг\s*/\s*л|g\s*/\s*cm[³3]|г\s*/\s*см[³3]|cm\s*/\s*(?:day|d|h)|см\s*/\s*(?:сут|ч)|mS\s*/\s*cm|µS\s*/\s*cm|uS\s*/\s*cm|dS\s*/\s*m|S\s*/\s*m|MPa|kPa|mV|°\s*C|%|pH)'
NUMBER = re.compile(r'^\s*(-?\d+(?:[.,]\d+)?)\s*(' + UNIT + r')?\s*$' ,re.I)
HEADER_UNIT = re.compile(UNIT, re.I)
# Table depth columns routinely omit ``cm`` after the header.  This pattern is
# intentionally used only for a row label, never arbitrary prose.
TABLE_DEPTH = re.compile(r'^\s*(\d{1,3})\s*[–—-]\s*(\d{1,3})(?:\s*(?:cm|см))?\s*$', re.I)

def property_for(header: str):
    # Patterns carrying words/formulae first; symbols only after stripping
    # unit expressions to prevent ``mg/kg`` from being read as Mg.  LaTeX
    # wrappers are removed first so ``pH\( _{H_2O} \)`` still reads as pH in
    # water rather than collapsing to the method-unspecified variant.
    header = normalize_header(header)
    for pid, pattern in TABLE_PROPERTY_PATTERNS.items():
        if re.search(pattern, header, re.I):
            return pid
    without_units = HEADER_UNIT.sub(' ', header)
    for pid, symbol in SYMBOL_PROPERTIES.items():
        # A symbol is a property only as a genuine header token.  OCR often
        # puts regression equations (``B 1.583 2.273``) above a numeric
        # column; treating their coefficient B as boron is a false positive.
        if re.search(symbol, without_units) and not re.search(r'\d', without_units):
            return pid
    return None

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--header-rows',type=int,default=3);p.add_argument('--replace-existing',action='store_true',help='Rebuild the regenerable OCR table candidate layer from table_cell.');a=p.parse_args()
 stats={'tables':0,'header_properties':0,'candidates':0}
 with sqlite3.connect(a.db) as c:
 # Stream one table at a time; an OCR matrix can be large.
  if a.replace_existing:
   c.execute('DELETE FROM table_measurement_candidate')
  artifacts=[r[0] for r in c.execute('SELECT DISTINCT artifact_id FROM table_cell')]
  for no,artifact in enumerate(artifacts,start=1):
   cells=defaultdict(dict)
   for r,col,text,rowspan in c.execute('SELECT row_index,column_index,text_raw,rowspan FROM table_cell WHERE artifact_id=? ORDER BY row_index,column_index',(artifact,)):
    # Materialise row spans so a treatment/sample label remains attached to
    # all of its depth rows, instead of disappearing after the first row.
    for spanned_row in range(r, r + rowspan):
     cells[spanned_row].setdefault(col,text)
   columns={col for row in cells.values() for col in row}
   ordered_rows=sorted(cells)
   # OCR tables vary from a single header line to several stacked headers.
   # The first numerically dense row is the defensible boundary; fixed three
   # rows previously swallowed the first observations into the header.
   numeric_threshold=max(2, len(columns)//3)
   data_start=next((r for r in ordered_rows if sum(bool(NUMBER.match(v)) for v in cells[r].values())>=numeric_threshold), a.header_rows)
   headers={}
   for col in columns:
    text=' '.join(cells[r].get(col,'') for r in ordered_rows if r < data_start).strip()
    pid=property_for(text)
    if pid: headers[col]=(pid,text);stats['header_properties']+=1
   if not headers: continue
   stats['tables']+=1
   for r,row in cells.items():
    if r<data_start: continue
    row_text=' | '.join(row.values()); depth=DEPTH.search(row_text); horizon=HORIZON.search(row_text)
    non_numeric=[v for _,v in sorted(row.items()) if not NUMBER.match(v)]
    row_label=' | '.join(non_numeric) or None
    table_depth=next((TABLE_DEPTH.match(v) for v in row.values() if TABLE_DEPTH.match(v)), None)
    for col,(pid,header) in headers.items():
     value=row.get(col,'');m=NUMBER.match(value)
     if not m: continue
     cid=f'{artifact}:tm:r{r}:c{col}'
     c.execute('''INSERT OR REPLACE INTO table_measurement_candidate
       (candidate_id,artifact_id,row_index,column_index,property_id,property_header_raw,value_num,value_text,unit_raw,row_label_raw,horizon_label,depth_top_cm,depth_bottom_cm,status)
       VALUES(?,?,?,?,?,?,?,NULL,?,?,?,?,?,'unreviewed')''',
       (cid,artifact,r,col,pid,header,num(m.group(1)),m.group(2) or (HEADER_UNIT.search(header).group(0) if HEADER_UNIT.search(header) else ('pH' if pid == 'ph_h2o' else None)),row_label,horizon.group(1) if horizon else None,num(depth.group(1)) if depth else (float(table_depth.group(1)) if table_depth else None),num(depth.group(2)) if depth else (float(table_depth.group(2)) if table_depth else None)))
     stats['candidates']+=1
   if no%100==0:c.commit()
  c.commit()
 print(stats)
if __name__=='__main__':main()
