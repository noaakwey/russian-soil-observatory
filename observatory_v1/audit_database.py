#!/usr/bin/env python3
"""Audit provenance and referential invariants of the operational database."""
from __future__ import annotations
import argparse, json, sqlite3
from pathlib import Path

CHECKS = {
 'site_without_evidence': '''SELECT count(*) FROM site s WHERE NOT EXISTS (SELECT 1 FROM site_evidence se WHERE se.site_id=s.site_id)''',
 'site_missing_coordinates': 'SELECT count(*) FROM site WHERE latitude IS NULL OR longitude IS NULL',
 'site_non_russia': "SELECT count(*) FROM site WHERE country_code <> 'RU'",
 'geocoded_site_missing_precision': "SELECT count(*) FROM site WHERE spatial_confidence='geocoded' AND (spatial_precision_m IS NULL OR spatial_precision_m <= 0)",
 'geocoded_site_missing_evidence': "SELECT count(*) FROM site s WHERE s.spatial_confidence='geocoded' AND NOT EXISTS (SELECT 1 FROM site_evidence se WHERE se.site_id=s.site_id AND se.evidence_kind='geocoding')",
 'accepted_measurement_missing_artifact': '''SELECT count(*) FROM measurement m LEFT JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id WHERE m.qa_status='accepted' AND a.artifact_id IS NULL''',
 'accepted_measurement_non_russian_site': '''SELECT count(*) FROM measurement m JOIN site s ON s.site_id=m.site_id WHERE m.qa_status='accepted' AND s.country_code <> 'RU' ''',
 'accepted_measurement_non_point_confidence': '''SELECT count(*) FROM measurement m JOIN site s ON s.site_id=m.site_id WHERE m.qa_status='accepted' AND s.spatial_confidence NOT IN ('exact','reported') ''',
 'staged_table_measurement_missing_artifact': '''SELECT count(*) FROM measurement m LEFT JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id WHERE m.qa_status='flagged' AND m.evidence_locator LIKE '%document_single_reported_coordinate%' AND a.artifact_id IS NULL''',
 'staged_table_measurement_non_reported_site': '''SELECT count(*) FROM measurement m JOIN site s ON s.site_id=m.site_id WHERE m.qa_status='flagged' AND m.evidence_locator LIKE '%document_single_reported_coordinate%' AND (s.country_code <> 'RU' OR s.spatial_confidence NOT IN ('exact','reported'))''',
 'staged_table_measurement_missing_linkage': '''SELECT count(*) FROM measurement m WHERE m.qa_status='flagged' AND m.evidence_locator LIKE '%document_single_reported_coordinate%' AND (m.evidence_locator IS NULL OR m.evidence_locator NOT LIKE '%table_candidate_id%')''',
 'regional_table_measurement_missing_artifact': '''SELECT count(*) FROM measurement m LEFT JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id WHERE m.qa_status='flagged' AND m.evidence_locator LIKE '%document_single_geocoded_district%' AND a.artifact_id IS NULL''',
 'regional_table_measurement_non_geocoded_site': '''SELECT count(*) FROM measurement m JOIN site s ON s.site_id=m.site_id WHERE m.qa_status='flagged' AND m.evidence_locator LIKE '%document_single_geocoded_district%' AND (s.country_code <> 'RU' OR s.spatial_confidence <> 'geocoded')''',
 'sample_without_evidence': '''SELECT count(*) FROM sample s WHERE NOT EXISTS (SELECT 1 FROM sample_evidence se WHERE se.sample_id=s.sample_id)''',
 'lab_analysis_missing_sample': '''SELECT count(*) FROM laboratory_analysis la LEFT JOIN sample s ON s.sample_id=la.sample_id WHERE s.sample_id IS NULL''',
 'lab_analysis_missing_evidence': '''SELECT count(*) FROM laboratory_analysis la LEFT JOIN source_artifact a ON a.artifact_id=la.evidence_artifact_id WHERE a.artifact_id IS NULL''',
 'accepted_location_outside_validation': '''SELECT count(*) FROM location_candidate lc WHERE lc.status='accepted' AND NOT EXISTS (SELECT 1 FROM location_validation lv WHERE lv.candidate_id=lc.candidate_id AND lv.country_code='RU' AND lv.result='inside')''',
}

def main() -> None:
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with sqlite3.connect(a.db) as c:
  report={name:c.execute(sql).fetchone()[0] for name,sql in CHECKS.items()}
  report['counts']={table:c.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in ('document','site','profile','horizon','sample','laboratory_analysis','measurement','measurement_candidate','table_measurement_candidate')}
  report['ready']=all(value==0 for name,value in report.items() if name!='counts')
 a.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False))
if __name__=='__main__':main()
