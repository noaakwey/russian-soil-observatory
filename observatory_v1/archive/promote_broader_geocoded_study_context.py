#!/usr/bin/env python3
"""Promote audited administrative study contexts as explicitly low-precision sites."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path

from audit_geocode_quality import SQL, tier


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); p.add_argument('--dry-run',action='store_true'); a=p.parse_args()
    stats={'eligible':0,'promoted':0}
    with sqlite3.connect(a.db) as con:
        con.row_factory=sqlite3.Row; rows=[dict(r) for r in con.execute(SQL)]
        for r in rows:
            if tier(r) != 'candidate_geocoded_study_context':
                continue
            stats['eligible'] += 1
            if a.dry_run:
                continue
            # Retrieve the full accepted geocode and artifact only after the
            # quality gate; this remains an administrative context, never a
            # claimed sampling coordinate.
            row=con.execute("""SELECT pg.latitude,pg.longitude,pg.spatial_precision_m,pg.source_url,e.artifact_id
                FROM place_geocode pg JOIN place_candidate pc ON pc.candidate_id=pg.candidate_id
                JOIN extraction e ON e.extraction_id=pc.extraction_id WHERE pc.candidate_id=?""",(r['candidate_id'],)).fetchone()
            lat,lon,precision,url,artifact=row
            sid=f"site:place:{r['candidate_id']}"
            con.execute("""INSERT INTO site(site_id,country_code,name,region,latitude,longitude,spatial_precision_m,spatial_confidence,geometry_source)
                VALUES(?, 'RU', ?, ?, ?, ?, ?, 'geocoded', ?)
                ON CONFLICT(site_id) DO NOTHING""",(sid,r['place_text'],r['display_name'],lat,lon,precision,
                'Nominatim administrative boundary centroid; study-area context; not a reported sampling coordinate.'))
            con.execute("INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind) VALUES(?,?,?,'location_text')",(sid,artifact,r['context_text']))
            con.execute("INSERT OR REPLACE INTO site_evidence(site_id,artifact_id,evidence_text,evidence_kind) VALUES(?,?,?,'geocoding')",(sid,artifact,json.dumps({'provider':'Nominatim','source_url':url,'precision_m':precision,'quality_gate':'matched_administrative_name+study_context','meaning':'administrative centroid/boundary; not sampling coordinate'},ensure_ascii=False)))
            con.execute("UPDATE place_candidate SET status='accepted' WHERE candidate_id=?",(r['candidate_id'],))
            stats['promoted'] += 1
        if not a.dry_run: con.commit()
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__':main()
