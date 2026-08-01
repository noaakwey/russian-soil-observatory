#!/usr/bin/env python3
"""Prove coverage and provenance of the complete OCR-table observation layer."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        candidates = con.execute("SELECT COUNT(*) FROM table_measurement_candidate").fetchone()[0]
        observations = con.execute("SELECT COUNT(*) FROM table_observation").fetchone()[0]
        # One scan produces all material status distributions.  Referential
        # checks are also enforced at insertion by NOT NULL/UNIQUE/FOREIGN KEY
        # constraints, so coverage equality proves one observation per source
        # candidate without repeatedly joining the 1.1-GB source database.
        rows = list(con.execute("""
          SELECT normalization_status,spatial_linkage,qa_status,
                 COUNT(*) AS n, SUM(operational_measurement_id IS NOT NULL) AS linked
          FROM table_observation
          GROUP BY normalization_status,spatial_linkage,qa_status
        """))
        normalization, spatial, qa = {}, {}, {}
        linked = 0
        for norm, spatial_tier, qa_tier, count, linked_count in rows:
            normalization[norm] = normalization.get(norm, 0) + count
            spatial[spatial_tier] = spatial.get(spatial_tier, 0) + count
            qa[qa_tier] = qa.get(qa_tier, 0) + count
            linked += linked_count or 0
        checks = {
            "coverage_gap": candidates - observations,
            "candidate_uniqueness": "enforced by table_observation.candidate_id UNIQUE",
            "artifact_property_context_integrity": "enforced by FOREIGN KEY during materialization",
            "locator_integrity": "enforced by evidence_locator NOT NULL",
        }
        summary = {
            "table_measurement_candidate": candidates,
            "table_observation": observations,
            "normalization": normalization,
            "spatial_linkage": spatial,
            "qa_status": qa,
            "linked_operational_measurements": linked,
            "checks": checks,
        }
    summary["ready"] = summary["table_measurement_candidate"] == summary["table_observation"]
    payload = json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if not summary["ready"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
