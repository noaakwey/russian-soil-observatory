#!/usr/bin/env python3
"""Summarize safely normalized OCR table values by property, without spatial claims."""
from __future__ import annotations
import argparse,csv,sqlite3
from pathlib import Path

SQL="""
SELECT p.property_id,p.canonical_name AS property,p.category,p.canonical_unit,
 COUNT(t.candidate_id) AS numeric_cells,COUNT(DISTINCT t.artifact_id) AS ocr_tables,COUNT(DISTINCT a.document_id) AS documents,
 SUM(CASE WHEN n.normalization_status IN ('exact','converted') THEN 1 ELSE 0 END) AS comparable_cells_all,
 SUM(CASE WHEN n.normalization_status IN ('exact','converted')
               AND COALESCE(n.warning,'') NOT LIKE '%qc_implausible_range%' THEN 1 ELSE 0 END) AS comparable_cells_qc_clear,
 SUM(CASE WHEN COALESCE(n.warning,'') LIKE '%qc_implausible_range%' THEN 1 ELSE 0 END) AS qc_flagged_cells,
 SUM(CASE WHEN n.normalization_status='exact' THEN 1 ELSE 0 END) AS exact_unit_cells,
 SUM(CASE WHEN n.normalization_status='converted' THEN 1 ELSE 0 END) AS converted_cells,
 SUM(CASE WHEN n.normalization_status='missing_unit' THEN 1 ELSE 0 END) AS missing_unit_cells,
 SUM(CASE WHEN n.normalization_status='incompatible' THEN 1 ELSE 0 END) AS incompatible_unit_cells,
 MIN(CASE WHEN n.normalization_status IN ('exact','converted') AND COALESCE(n.warning,'') NOT LIKE '%qc_implausible_range%' THEN n.value_normalized END) AS minimum_normalized_qc_clear,
 AVG(CASE WHEN n.normalization_status IN ('exact','converted') AND COALESCE(n.warning,'') NOT LIKE '%qc_implausible_range%' THEN n.value_normalized END) AS mean_normalized_qc_clear,
 MAX(CASE WHEN n.normalization_status IN ('exact','converted') AND COALESCE(n.warning,'') NOT LIKE '%qc_implausible_range%' THEN n.value_normalized END) AS maximum_normalized_qc_clear
FROM table_measurement_candidate t JOIN table_measurement_candidate_normalization n ON n.candidate_id=t.candidate_id
JOIN property_definition p ON p.property_id=t.property_id JOIN source_artifact a ON a.artifact_id=t.artifact_id
GROUP BY p.property_id,p.canonical_name,p.category,p.canonical_unit ORDER BY comparable_cells_qc_clear DESC,numeric_cells DESC,p.property_id
"""
def main():
 p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 with sqlite3.connect(a.db) as c:
  cur=c.execute(SQL); fields=[x[0] for x in cur.description];rows=[dict(zip(fields,x)) for x in cur]
 a.output.parent.mkdir(parents=True,exist_ok=True)
 with a.output.open('w',newline='',encoding='utf-8') as f:w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
 print({'properties':len(rows),'comparable_cells_all':sum(r['comparable_cells_all'] or 0 for r in rows),
        'comparable_cells_qc_clear':sum(r['comparable_cells_qc_clear'] or 0 for r in rows),
        'qc_flagged_cells':sum(r['qc_flagged_cells'] or 0 for r in rows)})
if __name__=='__main__':main()
