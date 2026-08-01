#!/usr/bin/env python3
"""Export a corpus-wide, non-spatial inventory from header-grounded OCR cells.

This is intentionally separate from operational measurements.  It reports what
the full table corpus contains, while preserving the fact that a cell can lack
a unit, a coordinate, or a row-to-site link.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


QUERY = """
SELECT pd.property_id, pd.canonical_name AS property, pd.category, pd.canonical_unit,
       COUNT(t.candidate_id) AS numeric_cells,
       COUNT(DISTINCT t.artifact_id) AS ocr_tables,
       COUNT(DISTINCT d.document_id) AS documents,
       SUM(CASE WHEN t.unit_raw IS NOT NULL AND trim(t.unit_raw)<>'' THEN 1 ELSE 0 END) AS cells_with_source_unit,
       COUNT(DISTINCT NULLIF(trim(t.unit_raw), '')) AS distinct_source_units,
       GROUP_CONCAT(DISTINCT t.property_header_raw) AS header_variants
FROM table_measurement_candidate t
JOIN property_definition pd ON pd.property_id=t.property_id
JOIN source_artifact a ON a.artifact_id=t.artifact_id
JOIN document d ON d.document_id=a.document_id
GROUP BY pd.property_id, pd.canonical_name, pd.category, pd.canonical_unit
ORDER BY numeric_cells DESC, property
"""

YEAR_QUERY = """
SELECT pd.property_id, pd.canonical_name AS property, pd.category, d.publication_year,
       COUNT(t.candidate_id) AS numeric_cells, COUNT(DISTINCT t.artifact_id) AS ocr_tables,
       COUNT(DISTINCT d.document_id) AS documents
FROM table_measurement_candidate t
JOIN property_definition pd ON pd.property_id=t.property_id
JOIN source_artifact a ON a.artifact_id=t.artifact_id
JOIN document d ON d.document_id=a.document_id
GROUP BY pd.property_id, pd.canonical_name, pd.category, d.publication_year
ORDER BY d.publication_year, numeric_cells DESC, property
"""

SPATIAL_QUERY = """
WITH document_sites AS (
  SELECT d.document_id, COUNT(DISTINCT s.site_id) AS reported_site_count
  FROM document d
  LEFT JOIN source_artifact a ON a.document_id=d.document_id
  LEFT JOIN site_evidence se ON se.artifact_id=a.artifact_id
  LEFT JOIN site s ON s.site_id=se.site_id AND s.spatial_confidence IN ('exact','reported')
  GROUP BY d.document_id
), candidates AS (
  SELECT t.candidate_id, t.artifact_id, t.property_id, d.document_id,
         CASE WHEN COALESCE(ds.reported_site_count,0)=0 THEN 'no_reported_coordinate'
              WHEN ds.reported_site_count=1 THEN 'document_single_reported_coordinate'
              ELSE 'document_multiple_reported_coordinates' END AS spatial_linkage_tier
  FROM table_measurement_candidate t
  JOIN source_artifact a ON a.artifact_id=t.artifact_id
  JOIN document d ON d.document_id=a.document_id
  JOIN document_sites ds ON ds.document_id=d.document_id
)
SELECT pd.property_id, pd.canonical_name AS property, pd.category, c.spatial_linkage_tier,
       COUNT(c.candidate_id) AS numeric_cells, COUNT(DISTINCT c.artifact_id) AS ocr_tables,
       COUNT(DISTINCT c.document_id) AS documents
FROM candidates c
JOIN property_definition pd ON pd.property_id=c.property_id
GROUP BY pd.property_id, pd.canonical_name, pd.category, c.spatial_linkage_tier
ORDER BY spatial_linkage_tier, numeric_cells DESC, property
"""

DOCUMENT_QUERY = """
SELECT d.document_id, d.corpus, d.doi, d.publication_year,
       COUNT(t.candidate_id) AS numeric_cells, COUNT(DISTINCT t.artifact_id) AS ocr_tables,
       COUNT(DISTINCT t.property_id) AS recognized_properties
FROM table_measurement_candidate t
JOIN source_artifact a ON a.artifact_id=t.artifact_id
JOIN document d ON d.document_id=a.document_id
GROUP BY d.document_id, d.corpus, d.doi, d.publication_year
ORDER BY d.document_id
"""


def write_query(con: sqlite3.Connection, query: str, output: Path) -> None:
    cur = con.execute(query); fields = [x[0] for x in cur.description]
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for row in cur: w.writerow(dict(zip(fields, row)))


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument('--db', type=Path, required=True); p.add_argument('--output', type=Path, required=True); p.add_argument('--metadata', type=Path); p.add_argument('--year-output', type=Path); p.add_argument('--spatial-output', type=Path); p.add_argument('--document-output', type=Path)
    a = p.parse_args()
    with sqlite3.connect(a.db) as con:
        cur = con.execute(QUERY); fields = [x[0] for x in cur.description]
        rows = [dict(zip(fields, row)) for row in cur]
        all_cells = con.execute('SELECT COUNT(*) FROM table_measurement_candidate').fetchone()[0]
        all_tables = con.execute('SELECT COUNT(DISTINCT artifact_id) FROM table_measurement_candidate').fetchone()[0]
        all_docs = con.execute('''SELECT COUNT(DISTINCT a.document_id) FROM table_measurement_candidate t JOIN source_artifact a ON a.artifact_id=t.artifact_id''').fetchone()[0]
    a.output.parent.mkdir(parents=True, exist_ok=True)
    with a.output.open('w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)
    summary = {'properties': len(rows), 'numeric_cells': all_cells, 'ocr_tables': all_tables, 'documents': all_docs}
    if a.metadata:
        a.metadata.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    with sqlite3.connect(a.db) as con:
        if a.year_output: write_query(con, YEAR_QUERY, a.year_output)
        if a.spatial_output: write_query(con, SPATIAL_QUERY, a.spatial_output)
        if a.document_output: write_query(con, DOCUMENT_QUERY, a.document_output)
    print(summary)


if __name__ == '__main__': main()
