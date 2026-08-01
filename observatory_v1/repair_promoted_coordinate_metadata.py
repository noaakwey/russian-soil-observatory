#!/usr/bin/env python3
"""Correct generic provenance wording on previously promoted coordinate sites."""
from __future__ import annotations
import json, sqlite3, argparse
from pathlib import Path

def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);a=p.parse_args(); changed=0
    with sqlite3.connect(a.db) as con:
        rows=con.execute("""SELECT s.site_id,lc.precision_hint,se.evidence_text FROM site s
            JOIN location_candidate lc ON s.site_id='site:'||lc.candidate_id
            JOIN site_evidence se ON se.site_id=s.site_id
            WHERE s.geometry_source LIKE 'Explicit degrees+decimal-minutes coordinate%'""")
        for sid,precision,evidence in rows:
            try: category=json.loads(evidence).get('audit_category','audited_coordinate')
            except (ValueError,TypeError): category='audited_coordinate'
            source=f'Explicit author-reported {precision} coordinate; country validated; audited {category}. Field-object location, not an automatic row-level measurement.'
            con.execute('UPDATE site SET geometry_source=? WHERE site_id=?',(source,sid));changed+=1
        con.commit()
    print(json.dumps({'repaired':changed},ensure_ascii=False))
if __name__=='__main__':main()
