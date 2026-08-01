#!/usr/bin/env python3
"""Repair only direct profile links disproved by the raw-source audit.

The script deliberately performs no coordinate extraction itself.  Its input is
the immutable audit CSV emitted by ``audit_direct_profile_source_coordinates``;
therefore a database mutation is possible only after a second, independently
saved evidence pass has found exactly one different coordinate and exactly one
existing reported site at that coordinate.  Use ``--apply`` only after reading
the printed plan.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


EPSILON = 1e-6


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    with args.audit.open(encoding="utf-8", newline="") as handle:
        audited = list(csv.DictReader(handle))
    candidates = [row for row in audited if row.get("status") == "source_coordinate_differs"]
    plan: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        for row in candidates:
            coordinates = json.loads(row["source_coordinates"])
            if len(coordinates) != 1:
                plan.append({"profile_id": row["profile_id"], "status": "ambiguous_audit_coordinate"})
                continue
            latitude, longitude, raw = coordinates[0]
            sites = con.execute(
                """SELECT DISTINCT s.site_id FROM site s
                   JOIN site_evidence se ON se.site_id=s.site_id
                   JOIN source_artifact a ON a.artifact_id=se.artifact_id
                   WHERE a.document_id=?
                     AND ABS(s.latitude - ?) < ? AND ABS(s.longitude - ?) < ?
                   ORDER BY s.site_id""",
                (row["document_id"], latitude, EPSILON, longitude, EPSILON),
            ).fetchall()
            if len(sites) != 1:
                plan.append({"profile_id": row["profile_id"], "status": "target_site_missing_or_ambiguous",
                             "latitude": latitude, "longitude": longitude, "matching_sites": [s["site_id"] for s in sites]})
                continue
            current = con.execute("SELECT site_id FROM profile WHERE profile_id=?", (row["profile_id"],)).fetchone()
            if not current:
                plan.append({"profile_id": row["profile_id"], "status": "profile_missing"})
                continue
            plan.append({"profile_id": row["profile_id"], "status": "ready",
                         "from_site_id": current["site_id"], "to_site_id": sites[0]["site_id"],
                         "latitude": latitude, "longitude": longitude, "raw_coordinate": raw})
        if args.apply:
            unsafe = [r for r in plan if r["status"] != "ready"]
            if unsafe:
                raise SystemExit("Refusing partial repair: " + json.dumps(unsafe, ensure_ascii=False))
            for row in plan:
                con.execute("UPDATE profile SET site_id=? WHERE profile_id=?", (row["to_site_id"], row["profile_id"]))
            con.commit()
    print(json.dumps({"apply": args.apply, "rows": plan}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
