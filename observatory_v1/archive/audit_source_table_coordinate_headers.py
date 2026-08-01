#!/usr/bin/env python3
"""Find unreviewed source-text coordinates inside explicitly spatial soil tables.

This is an audit queue, not an importer.  It uses the table header printed in
the same full-text artifact as the coordinate and accepts only headers that
state both a coordinate column and a soil/sample/study object.  This avoids
turning literature comparison tables or map extents into field sites.
"""
from __future__ import annotations

import argparse, csv, re, sqlite3
from pathlib import Path

# PDF-to-text output commonly puts every column header on a different line;
# retain the first 800 characters after the printed table label.
TABLE = re.compile(r"(?:Table|Таблица)\s*\d+[\s\S]{0,800}", re.I)
COORD = re.compile(r"(?:coordinat|координат|GPS|UTM)", re.I)
OBJECT = re.compile(r"(?:sampling|sample|soil|profile|pit|plot|study\s+object|"
                    r"отбор|образец|почв|разрез|профил|объект\s+исследован)", re.I)

SQL = """
SELECT lc.candidate_id,lc.latitude,lc.longitude,lc.precision_hint,lc.context_text,
       d.document_id,d.corpus,a.artifact_id,a.source_path
FROM location_candidate lc JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
JOIN extraction e ON e.extraction_id=lc.extraction_id JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE lc.status='unreviewed' AND lv.country_code='RU' AND lv.result='inside' AND a.artifact_type='text'
ORDER BY d.document_id,lc.candidate_id
"""

def table_header(text: str, context: str) -> str | None:
    # Context is copied verbatim from the source during extraction.  A short
    # prefix is enough to locate it and avoids fragile reconstruction of DMS.
    prefix = context[:100]
    pos = text.find(prefix) if prefix else -1
    if pos < 0:
        return None
    before = text[max(0, pos - 3500):pos]
    matches = list(TABLE.finditer(before))
    if not matches:
        return None
    # Only the header is evidence here.  Limiting it prevents a coordinate in
    # a distant next table from satisfying a generic word match.
    return matches[-1].group(0)[:800]

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); p.add_argument('--output',type=Path,required=True); a=p.parse_args()
    out=[]; seen=set(); cache={}
    with sqlite3.connect(a.db) as con:
        con.row_factory=sqlite3.Row
        for rec in con.execute(SQL):
            r=dict(rec); path=r['source_path']
            if path not in cache:
                try: cache[path]=Path(path).read_text(encoding='utf-8',errors='replace')
                except OSError: cache[path]=''
            header=table_header(cache[path],r['context_text'] or '')
            if not header or not COORD.search(header) or not OBJECT.search(header):
                continue
            key=(r['document_id'],round(r['latitude'],7),round(r['longitude'],7))
            if key in seen: continue
            seen.add(key); r['table_header']=header; r['category']='source_table_explicit_coordinate_object'; out.append(r)
    fields=['candidate_id','document_id','corpus','artifact_id','precision_hint','latitude','longitude','category','table_header','context_text']
    with a.output.open('w',encoding='utf-8',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows([{k:r.get(k) for k in fields} for r in out])
    print({'unique_candidates':len(out),'documents':len({r['document_id'] for r in out})})
if __name__=='__main__': main()
