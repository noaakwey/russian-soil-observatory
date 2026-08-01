#!/usr/bin/env python3
"""Register map-page OCR and stage only explicitly cardinal coordinate pairs.

No staged candidate is an operational point.  Map grids and site labels are
kept as raw evidence and go through the normal country/context gate later.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from extract_ocr_artifact_coordinates import DECIMAL, DMS, dms
from extract_cardinal_coordinate_variants import REVERSED_DECIMAL
from extract_degree_decimal_minutes import PAIR as DEGREE_MINUTES, RUSSIAN_PAIR as RU_DEGREE_MINUTES, value as degree_minute_value


def add(con, eid, candidate_id, lat, lon, hint, text, start, end, stats):
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        stats['invalid']+=1; return
    context=text[max(0,start-260):min(len(text),end+340)].replace('\n',' ')
    con.execute("""INSERT OR IGNORE INTO location_candidate
        (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
        VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",(candidate_id,eid,lat,lon,hint,context))
    stats['candidates']+=1


def main():
    p=argparse.ArgumentParser();p.add_argument('--input',type=Path,required=True);p.add_argument('--db',type=Path,required=True);a=p.parse_args()
    stats={'pages':0,'candidates':0,'invalid':0}
    with sqlite3.connect(a.db) as con, a.input.open(encoding='utf-8') as f:
        con.execute('PRAGMA foreign_keys=ON')
        for line in f:
            r=json.loads(line); page_id=r['page_id']; doc=r['document_id']; page=int(r['page']); text=r.get('ocr_text') or ''
            artifact=f'{page_id}:ocr'; eid=f'{artifact}:raw'
            page_source = f"{r['pdf_path']}#page={page}"
            con.execute("""INSERT INTO source_artifact(artifact_id,document_id,artifact_type,source_path,page_start,page_end,metadata_json)
                VALUES(?,?,'page',?,?,?,?) ON CONFLICT(artifact_id) DO UPDATE SET metadata_json=excluded.metadata_json""",(artifact,doc,page_source,page,page,json.dumps({'caption_fragment':r.get('caption_fragment'),'page_id':page_id},ensure_ascii=False)))
            con.execute("""INSERT INTO extraction(extraction_id,artifact_id,extractor,extractor_version,raw_text,parsed_json,status)
                VALUES(?,?, 'rapidocr','map-page-v1',?,'{}','raw') ON CONFLICT(extraction_id) DO UPDATE SET raw_text=excluded.raw_text""",(eid,artifact,text))
            for i,m in enumerate(DECIMAL.finditer(text)):
                add(con,eid,f'{eid}:decimal:{i}',float(m['lat'].replace(',','.')),float(m['lon'].replace(',','.')),'map_ocr_decimal_cardinal',text,m.start(),m.end(),stats)
            for i,m in enumerate(DMS.finditer(text)):
                try: lat,lon=dms(m['lat_d'],m['lat_m'],m['lat_s'],m['lat_h']),dms(m['lon_d'],m['lon_m'],m['lon_s'],m['lon_h'])
                except ValueError: stats['invalid']+=1; continue
                add(con,eid,f'{eid}:dms:{i}',lat,lon,'map_ocr_dms_cardinal',text,m.start(),m.end(),stats)
            for i,m in enumerate(REVERSED_DECIMAL.finditer(text)):
                add(con,eid,f'{eid}:reversed:{i}',float(m['lat'].replace(',','.')),float(m['lon'].replace(',','.')),'map_ocr_reversed_decimal_cardinal',text,m.start(),m.end(),stats)
            for kind, pattern, cardinal in (('degree_minutes', DEGREE_MINUTES, True),
                                             ('russian_degree_minutes', RU_DEGREE_MINUTES, False)):
                for i, m in enumerate(pattern.finditer(text)):
                    try:
                        lat = degree_minute_value(m['lat_d'], m['lat_m'], m['lat_h'] if cardinal else 'N')
                        lon = degree_minute_value(m['lon_d'], m['lon_m'], m['lon_h'] if cardinal else 'E')
                    except ValueError:
                        stats['invalid'] += 1
                        continue
                    add(con,eid,f'{eid}:{kind}:{i}',lat,lon,f'map_ocr_{kind}',text,m.start(),m.end(),stats)
            stats['pages']+=1
        con.commit()
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__':main()
