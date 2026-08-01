#!/usr/bin/env python3
"""Export one reproducible readiness row for every source document."""
from __future__ import annotations
import argparse,csv,sqlite3
from pathlib import Path

SQL="""
WITH artifacts AS (SELECT document_id,
 SUM(artifact_type='text') has_fulltext,SUM(artifact_type='ocr_markdown') ocr_artifacts,
 SUM(artifact_type='page') map_pages FROM source_artifact GROUP BY document_id),
 coords AS (SELECT a.document_id,COUNT(DISTINCT s.site_id) reported_sites,
 COUNT(DISTINCT CASE WHEN s.name LIKE 'Reported soil-study context%' THEN s.site_id END) soil_context_sites
 FROM source_artifact a JOIN site_evidence se ON se.artifact_id=a.artifact_id JOIN site s ON s.site_id=se.site_id
 WHERE s.spatial_confidence IN ('reported','exact') GROUP BY a.document_id),
 profiles AS (SELECT a.document_id,COUNT(DISTINCT p.profile_id) profiles,
 SUM(p.notes='Direct profile-label-to-coordinate link in one source fragment.') direct_profiles
 FROM profile p JOIN profile_evidence pe ON pe.profile_id=p.profile_id JOIN source_artifact a ON a.artifact_id=pe.artifact_id GROUP BY a.document_id),
 tables AS (SELECT a.document_id,COUNT(t.candidate_id) table_cells,COUNT(DISTINCT t.artifact_id) ocr_tables,
 SUM(n.normalization_status IN ('exact','converted')) comparable_cells FROM table_measurement_candidate t
 JOIN source_artifact a ON a.artifact_id=t.artifact_id JOIN table_measurement_candidate_normalization n ON n.candidate_id=t.candidate_id GROUP BY a.document_id),
 measurements AS (SELECT a.document_id,SUM(m.qa_status='accepted') accepted_measurements,SUM(m.qa_status='flagged') flagged_measurements FROM measurement m JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id GROUP BY a.document_id)
SELECT d.document_id,d.corpus,d.doi,d.publication_year,COALESCE(ar.has_fulltext,0) has_fulltext,COALESCE(ar.ocr_artifacts,0) ocr_artifacts,COALESCE(ar.map_pages,0) map_pages,
 COALESCE(c.reported_sites,0) reported_sites,COALESCE(c.soil_context_sites,0) soil_context_sites,COALESCE(p.profiles,0) profiles,COALESCE(p.direct_profiles,0) direct_profiles,
 COALESCE(t.table_cells,0) table_cells,COALESCE(t.ocr_tables,0) ocr_tables,COALESCE(t.comparable_cells,0) comparable_cells,COALESCE(m.accepted_measurements,0) accepted_measurements,COALESCE(m.flagged_measurements,0) flagged_measurements,
 CASE WHEN COALESCE(m.accepted_measurements,0)>0 THEN 'direct_measurement_ready'
      WHEN COALESCE(m.flagged_measurements,0)>0 THEN 'document_single_coordinate_measurements'
      WHEN COALESCE(c.reported_sites,0)>0 AND COALESCE(t.table_cells,0)>0 THEN 'multiple_or_unlinked_reported_coordinates'
      WHEN COALESCE(c.reported_sites,0)>0 THEN 'coordinate_catalogued'
      WHEN COALESCE(t.table_cells,0)>0 THEN 'table_only_requires_location_link'
      ELSE 'no_operational_spatial_or_table_layer' END AS readiness_tier
FROM document d LEFT JOIN artifacts ar USING(document_id) LEFT JOIN coords c USING(document_id) LEFT JOIN profiles p USING(document_id) LEFT JOIN tables t USING(document_id) LEFT JOIN measurements m USING(document_id)
ORDER BY d.corpus,d.document_id
"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with sqlite3.connect(a.db) as c:
  cur=c.execute(SQL);fs=[x[0] for x in cur.description]; rows=[dict(zip(fs,x)) for x in cur]
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fs);w.writeheader();w.writerows(rows)
 print({'documents':len(rows)})
if __name__=='__main__':main()
