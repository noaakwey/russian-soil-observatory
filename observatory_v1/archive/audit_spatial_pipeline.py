#!/usr/bin/env python3
"""Read-only inventory of spatial evidence and unresolved expansion paths."""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path

QUERIES = {
 "location_candidates": "SELECT precision_hint, status, COUNT(*) n FROM location_candidate GROUP BY precision_hint,status ORDER BY n DESC",
 "location_validation": "SELECT country_code,result,COUNT(*) n FROM location_validation GROUP BY country_code,result ORDER BY n DESC",
 "place_candidates": "SELECT status,COUNT(*) n FROM place_candidate GROUP BY status ORDER BY n DESC",
 "place_geocodes": "SELECT status,COUNT(*) n FROM place_geocode GROUP BY status ORDER BY n DESC",
 "sites": "SELECT spatial_confidence,COUNT(*) n FROM site GROUP BY spatial_confidence ORDER BY n DESC",
 "unresolved_place_levels": "SELECT pc.administrative_level,COUNT(*) n FROM place_candidate pc LEFT JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id WHERE pc.status='unreviewed' GROUP BY pc.administrative_level ORDER BY n DESC",
 "documents_by_spatial": """SELECT CASE WHEN EXISTS (SELECT 1 FROM source_artifact a JOIN site_evidence se ON se.artifact_id=a.artifact_id JOIN site s ON s.site_id=se.site_id WHERE a.document_id=d.document_id AND s.spatial_confidence IN ('exact','reported')) THEN 'reported_coordinate' WHEN EXISTS (SELECT 1 FROM source_artifact a JOIN site_evidence se ON se.artifact_id=a.artifact_id JOIN site s ON s.site_id=se.site_id AND s.spatial_confidence='geocoded') THEN 'geocoded_context_only' ELSE 'no_operational_spatial_evidence' END tier,COUNT(*) n FROM document d GROUP BY tier ORDER BY n DESC""",
}
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);a=p.parse_args()
 with sqlite3.connect(a.db) as c:
  out={k:[dict(zip([x[0] for x in c.execute(q).description],r)) for r in c.execute(q)] for k,q in QUERIES.items()}
 print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
