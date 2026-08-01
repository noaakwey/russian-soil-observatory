#!/usr/bin/env python3
"""Create strictly evidence-filtered sites from accepted administrative geocodes.

Coordinates represent a geocoded administrative centroid/boundary only.  They
must not be interpreted as the sampling point itself.
"""
from __future__ import annotations
import argparse, json, re, sqlite3
from pathlib import Path

SQL='''
SELECT pc.candidate_id,pc.place_text,pc.context_text,pg.display_name,pg.latitude,pg.longitude,
       pg.geometry_kind,pg.spatial_precision_m,pg.source_url,e.artifact_id
FROM place_candidate pc
JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
JOIN extraction e ON e.extraction_id=pc.extraction_id
WHERE pc.status='unreviewed' AND pg.status='accepted' AND pg.country_code='RU'
'''
DIRECT_STUDY_CONTEXT = re.compile(
    r'\b(?:study (?:area|site)|research (?:was|has been)|soil (?:samples?|profiles?|pits?)|'
    r'samples? (?:were|was) (?:collected|taken|analysed|analyzed)|field (?:site|study)|'
    r'sampling|investigated|examined|located|район исследования|исследуем\w*\s+(?:почв|участ)|'
    r'почвенн\w*\s+(?:образц|разрез|профил)|отбор\w*\s+(?:почв|образц)|'
    r'образц\w*\s+почв|разрез\w*|профил\w*|почв\w*\s+(?:отобран|исследован|изучен)|'
    r'исследован\w*\s+(?:почв|участ)|участк\w*\s+исследован)\b', re.I)
REFERENCE_OR_AFFILIATION = re.compile(
    r'\b(?:references|литератур|bibliograph|doi\s*[:.]|e-?mail|принят[ао]? в редакц|'
    r'поступил[ао]? в редакц|институт|university|академи[яи])\b|//', re.I)


def is_study_context(context: str) -> bool:
    """Require an action or study-site phrase, never generic word 'soil'."""
    return bool(DIRECT_STUDY_CONTEXT.search(context)) and not (
        REFERENCE_OR_AFFILIATION.search(context) and not re.search(
            r'\b(?:район исследования|study area|samples? (?:were|was) (?:collected|taken)|'
            r'отбор\w*|разрез\w*|profile|soil pit)\b', context, re.I
        )
    )
def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);a=p.parse_args();stats={'promoted':0,'not_study_context':0}
 with sqlite3.connect(a.db) as c:
  c.execute('PRAGMA foreign_keys=ON')
  for cid,place,context,display,lat,lon,kind,precision,url,artifact in c.execute(SQL):
   if not is_study_context(context):
    stats['not_study_context']+=1
    continue
   sid=f'site:place:{cid}'
   source='Geocoded administrative centroid/boundary via Nominatim; not a reported sampling coordinate.'
   c.execute('''INSERT INTO site(site_id,country_code,name,region,latitude,longitude,spatial_precision_m,spatial_confidence,geometry_source)
                VALUES(?, 'RU', ?, ?, ?, ?, ?, 'geocoded', ?) ON CONFLICT(site_id) DO NOTHING''',(sid,place,display,lat,lon,precision,source))
   c.execute('INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind) VALUES(?,?,?,"location_text")',(sid,artifact,context))
   c.execute('INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind) VALUES(?,?,?,"geocoding")',(sid,artifact,json.dumps({'provider':'Nominatim','source_url':url,'precision_m':precision,'meaning':'administrative centroid/boundary; not sampling coordinate'},ensure_ascii=False)))
   c.execute("UPDATE place_candidate SET status='accepted' WHERE candidate_id=?",(cid,));stats['promoted']+=1
  c.commit()
 print(json.dumps(stats,ensure_ascii=False))
if __name__=='__main__':main()
