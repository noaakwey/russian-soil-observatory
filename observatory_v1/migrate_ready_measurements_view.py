#!/usr/bin/env python3
"""Migrate the ready-measurement view to its point-coordinate contract."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


VIEW_SQL = """
CREATE VIEW v_ready_measurements AS
SELECT
  m.measurement_id, d.corpus, d.document_id, s.site_id, s.name AS site_name,
  s.latitude, s.longitude, s.spatial_confidence, p.profile_label,
  h.horizon_label, h.depth_top_cm, h.depth_bottom_cm,
  pd.canonical_name AS property, pd.category, m.value_num, m.value_text,
  m.unit_normalized, m.unit_raw, m.method_normalized, m.method_raw,
  a.source_path AS evidence_path, m.evidence_locator
FROM measurement m
JOIN site s ON s.site_id=m.site_id
LEFT JOIN profile p ON p.profile_id=m.profile_id
LEFT JOIN horizon h ON h.horizon_id=m.horizon_id
JOIN property_definition pd ON pd.property_id=m.property_id
JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE m.qa_status='accepted'
  AND s.country_code='RU'
  AND s.spatial_confidence IN ('exact','reported');
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        before = con.execute("SELECT count(*) FROM v_ready_measurements").fetchone()[0]
        if not args.dry_run:
            con.execute("DROP VIEW IF EXISTS v_ready_measurements")
            con.execute(VIEW_SQL)
            con.commit()
        after = con.execute("SELECT count(*) FROM v_ready_measurements").fetchone()[0]
        unsafe = con.execute("""
            SELECT count(*) FROM v_ready_measurements
            WHERE spatial_confidence NOT IN ('exact','reported')
        """).fetchone()[0]
    print({"before": before, "after": after, "unsafe_rows": unsafe, "applied": not args.dry_run})


if __name__ == "__main__":
    main()
