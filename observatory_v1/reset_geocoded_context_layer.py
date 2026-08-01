#!/usr/bin/env python3
"""Remove only derived regional-centroid sites before a stricter re-promotion.

Exact/reported sites and every measurement are deliberately untouched.
Geocode responses are retained as a cache; accepted candidates are returned to
the queue so the newer semantic filter can evaluate the same evidence.
"""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path

def main():
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); a=p.parse_args()
    with sqlite3.connect(a.db) as c:
        c.execute('PRAGMA foreign_keys=ON')
        site_ids=[r[0] for r in c.execute("SELECT site_id FROM site WHERE spatial_confidence='geocoded'")]
        c.executemany('DELETE FROM site_evidence WHERE site_id=?',[(x,) for x in site_ids])
        c.executemany('DELETE FROM site WHERE site_id=?',[(x,) for x in site_ids])
        c.execute("""UPDATE place_candidate SET status='unreviewed'
                   WHERE candidate_id IN (SELECT candidate_id FROM place_geocode WHERE status='accepted' AND country_code='RU')""")
        c.commit()
    print(json.dumps({'removed_geocoded_sites':len(site_ids)},ensure_ascii=False))

if __name__=='__main__': main()
