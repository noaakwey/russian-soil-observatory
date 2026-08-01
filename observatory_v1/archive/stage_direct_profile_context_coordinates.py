#!/usr/bin/env python3
"""Stage profiles only where their own fragment prints label and coordinate."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

from audit_profile_context_coordinate import SQL, coords, specific


def raw_profile_blocks(text, label):
    """Yield only source fragments belonging to this exact printed label.

    Context windows from an extractor can contain two adjacent profiles.  That
    is harmless for a distinctive label but unsafe for ``Разрез 3``: the first
    coordinate after the string may belong to its neighbour.  Staging therefore
    uses raw article boundaries as the authority for every direct link.
    """
    profile = re.compile(r"(?:Разрез|Точка|Point|Soil\s+(?:profile|pit)|Pit)\s+" +
                         re.escape(label) + r"(?![A-Za-zА-Яа-я0-9_-])", re.I)
    all_profiles = re.compile(r"(?:Разрез|Точка|Point|Soil\s+(?:profile|pit)|Pit)\s+"
                              r"[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{0,24}", re.I)
    for match in profile.finditer(text):
        next_match = all_profiles.search(text, match.end())
        yield text[match.start():next_match.start() if next_match else min(len(text), match.start() + 2500)]


def digest(*items: str) -> str:
    return hashlib.sha1("\x1f".join(items).encode()).hexdigest()[:20]


def matched_coordinate(con, rec):
    path = Path(rec['source_path'])
    if not path.exists():
        return None
    candidates=con.execute("""SELECT lc.candidate_id,lc.latitude,lc.longitude FROM location_candidate lc
        JOIN location_validation lv ON lv.candidate_id=lc.candidate_id WHERE lc.extraction_id=?
        AND lv.country_code='RU' AND lv.result='inside'""",(rec['extraction_id'],)).fetchall()
    text = path.read_text(encoding='utf-8', errors='replace')
    matches=[]
    for block in raw_profile_blocks(text, rec['profile_label']):
        for x,y,_start,_end in coords(block):
            matches += [(cid,lat,lon) for cid,lat,lon in candidates if abs(x-lat)<1e-6 and abs(y-lon)<1e-6]
    return matches[0] if len({x[0] for x in matches})==1 else None


def main():
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--dry-run',action='store_true');a=p.parse_args(); groups=defaultdict(list)
    with sqlite3.connect(a.db) as con:
        con.row_factory=sqlite3.Row; con.execute('PRAGMA foreign_keys=ON')
        con.execute("""CREATE TABLE IF NOT EXISTS profile_evidence (
          profile_id TEXT NOT NULL REFERENCES profile(profile_id), artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
          extraction_id TEXT REFERENCES extraction(extraction_id), evidence_text TEXT NOT NULL,
          evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('profile_description','table_header','table_row')),
          PRIMARY KEY (profile_id, artifact_id, evidence_kind))""")
        for row in con.execute(SQL):
            rec=dict(row)
            if not specific(rec['profile_label']): continue
            hit=matched_coordinate(con,rec)
            if not hit: continue
            cid,lat,lon=hit; site_id=f'site:{cid}'
            if con.execute('SELECT 1 FROM site WHERE site_id=?',(site_id,)).fetchone():
                groups[(rec['document_id'],site_id,rec['profile_label'])].append(rec)
        stats={'groups':len(groups),'staged_profiles':0,'candidate_descriptions':0}
        for (doc,site,label),records in groups.items():
            profile_id='profile:direct:'+digest(doc,site,label)
            soils=sorted({r['soil_classification_raw'] for r in records if r['soil_classification_raw']})
            systems=sorted({r['classification_system_candidate'] for r in records if r['classification_system_candidate']})
            lands=sorted({r['land_use_raw'] for r in records if r['land_use_raw']})
            evidence={'spatial_linkage':'direct_profile_coordinate_label','profile_candidate_ids':[r['candidate_id'] for r in records]}
            text=json.dumps(evidence,ensure_ascii=False)+'\n'+'\n---\n'.join(r['context_text'] for r in records)
            if not a.dry_run:
                con.execute("""INSERT INTO profile(profile_id,site_id,profile_label,soil_classification,classification_system,land_use,notes)
                 VALUES(?,?,?,?,?,?,?) ON CONFLICT(profile_id) DO UPDATE SET soil_classification=excluded.soil_classification,
                 classification_system=excluded.classification_system,land_use=excluded.land_use,notes=excluded.notes""",
                 (profile_id,site,label,'; '.join(soils) or None,'; '.join(systems) or None,'; '.join(lands) or None,
                  'Direct profile-label-to-coordinate link in one source fragment.'))
                con.execute("""INSERT INTO profile_evidence(profile_id,artifact_id,extraction_id,evidence_text,evidence_kind)
                 VALUES(?,?,?,?, 'profile_description') ON CONFLICT(profile_id,artifact_id,evidence_kind) DO UPDATE SET evidence_text=excluded.evidence_text""",
                 (profile_id,records[0]['artifact_id'],records[0]['extraction_id'],text))
                con.executemany("UPDATE profile_candidate SET status='accepted' WHERE candidate_id=?",[(r['candidate_id'],) for r in records])
            stats['staged_profiles']+=1;stats['candidate_descriptions']+=len(records)
        if not a.dry_run: con.commit()
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__':main()
