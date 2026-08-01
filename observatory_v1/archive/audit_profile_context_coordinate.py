#!/usr/bin/env python3
"""Find profile candidates whose own text fragment prints a coordinate pair."""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

from extract_ocr_artifact_coordinates import DECIMAL, DMS, dms
from extract_russian_abbreviated_coordinates import DECIMAL as RU_DECIMAL, DMS as RU_DMS, dms_value
from extract_degree_decimal_minutes import (
    PAIR as DEGREE_MINUTES,
    REVERSED_PAIR as REVERSED_DEGREE_MINUTES,
    RUSSIAN_PAIR as RU_DEGREE_MINUTES,
    value as degree_minute_value,
)


def specific(label: str | None) -> bool:
    if not label:
        return False
    clean = label.strip()
    # Labels are extracted only after an explicit profile/pit/sample keyword.
    # Therefore a short numeric ``Разрез 3`` is specific enough, while a bare
    # letter remains unsafe.
    return bool(re.search(r'\d', clean) and len(clean) <= 24)


def coords(text: str):
    seen = set()
    for m in DECIMAL.finditer(text or ''):
        value = (float(m['lat'].replace(',','.')),float(m['lon'].replace(',','.')),m.start(),m.end())
        seen.add(value[:2]); yield value
    for m in DMS.finditer(text or ''):
        try:
            value = (dms(m['lat_d'],m['lat_m'],m['lat_s'],m['lat_h']),dms(m['lon_d'],m['lon_m'],m['lon_s'],m['lon_h']),m.start(),m.end())
            if value[:2] not in seen: seen.add(value[:2]); yield value
        except ValueError: continue
    for m in RU_DECIMAL.finditer(text or ''):
        lat, lon = float(m['lat'].replace(',','.')), float(m['lon'].replace(',','.'))
        if m['lat_h'].strip().upper().startswith(('S','Ю')): lat = -lat
        if m['lon_h'].strip().upper().startswith(('W','З')): lon = -lon
        value = (lat, lon, m.start(), m.end())
        if value[:2] not in seen: seen.add(value[:2]); yield value
    for m in RU_DMS.finditer(text or ''):
        try:
            value = (dms_value(m,'lat',m['lat_h']),dms_value(m,'lon',m['lon_h']),m.start(),m.end())
            if value[:2] not in seen: seen.add(value[:2]); yield value
        except ValueError: continue
    # Explicit degrees plus decimal minutes (e.g. 51°37.604′ N) are common in
    # Russian papers.  They are author-reported point coordinates, not map
    # ticks, and must participate in the same exact text-local linkage.
    for pattern, cardinal in ((DEGREE_MINUTES, True), (RU_DEGREE_MINUTES, False)):
        for m in pattern.finditer(text or ''):
            try:
                lat = degree_minute_value(m['lat_d'], m['lat_m'], m['lat_h'] if cardinal else 'N')
                lon = degree_minute_value(m['lon_d'], m['lon_m'], m['lon_h'] if cardinal else 'E')
                value = (lat, lon, m.start(), m.end())
                if value[:2] not in seen:
                    seen.add(value[:2]); yield value
            except ValueError:
                continue
    # The author may print longitude before latitude (``38°58′ E, 51°36′ N``).
    # Preserve the exact character window so downstream label matching remains
    # local; the coordinate is only reordered for its numeric representation.
    for m in REVERSED_DEGREE_MINUTES.finditer(text or ''):
        try:
            lat = degree_minute_value(m['lat_d'], m['lat_m'], m['lat_h'])
            lon = degree_minute_value(m['lon_d'], m['lon_m'], m['lon_h'])
            value = (lat, lon, m.start(), m.end())
            if value[:2] not in seen:
                seen.add(value[:2]); yield value
        except ValueError:
            continue

SQL="""
SELECT pc.candidate_id,pc.extraction_id,pc.profile_label,pc.soil_classification_raw,pc.classification_system_candidate,
 pc.land_use_raw,pc.context_text,d.document_id,d.corpus,a.artifact_id,a.source_path
FROM profile_candidate pc JOIN extraction e ON e.extraction_id=pc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id JOIN document d ON d.document_id=a.document_id
WHERE pc.profile_label IS NOT NULL
"""

def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path);a=p.parse_args();out=[]
 with sqlite3.connect(a.db) as con:
  con.row_factory=sqlite3.Row
  for r in con.execute(SQL):
   r=dict(r)
   if not specific(r['profile_label']): continue
   local=list(coords(r['context_text']))
   if not local: continue
   label_match=re.search(re.escape(r['profile_label']),r['context_text'],re.I)
   if not label_match: continue
   candidates=con.execute("""SELECT lc.candidate_id,lc.latitude,lc.longitude FROM location_candidate lc JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
    WHERE lc.extraction_id=? AND lv.country_code='RU' AND lv.result='inside'""",(r['extraction_id'],)).fetchall()
   matches=[(cid,lat,lon) for x,y,start,end in local
            if -20 <= start-label_match.end() <= 120
            for cid,lat,lon in candidates if abs(x-lat)<1e-6 and abs(y-lon)<1e-6]
   if len({m[0] for m in matches})==1:
    cid,lat,lon=matches[0];r.update(coordinate_candidate_id=cid,latitude=lat,longitude=lon);out.append(r)
 if a.output:
  fields=['candidate_id','document_id','corpus','profile_label','soil_classification_raw','classification_system_candidate','land_use_raw','coordinate_candidate_id','latitude','longitude','context_text','artifact_id']
  with a.output.open('w',newline='',encoding='utf-8') as f:
   w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows([{k:r[k] for k in fields} for r in out])
 print(json.dumps({'direct_profile_context_coordinate':len(out)},ensure_ascii=False))
if __name__=='__main__':main()
