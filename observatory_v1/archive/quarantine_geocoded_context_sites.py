#!/usr/bin/env python3
"""Quarantine, without deleting, geocoded centroids that fail the strict audit."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path


SAFE = "verified_geocoded_study_context"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    with args.audit.open(encoding="utf-8", newline="") as handle:
        audit = list(csv.DictReader(handle))
    unsafe = [row for row in audit if row.get("audit_status") != SAFE]
    with sqlite3.connect(args.db) as con:
        existing = con.execute(
            "SELECT count(*) FROM site WHERE site_id IN ({}) AND spatial_confidence='geocoded'".format(
                ",".join("?" for _ in unsafe) or "''"
            ),
            [row["site_id"] for row in unsafe],
        ).fetchone()[0]
        if args.apply:
            for row in unsafe:
                con.execute(
                    """UPDATE site
                       SET spatial_confidence='unverified',
                           geometry_source=COALESCE(geometry_source,'') || ?
                       WHERE site_id=? AND spatial_confidence='geocoded'""",
                    (f" [quarantined geocode audit: {row['audit_status']}]", row["site_id"]),
                )
            con.commit()
    print({"audit_rows": len(audit), "quarantine_candidates": len(unsafe),
           "currently_geocoded_to_quarantine": existing, "apply": args.apply})


if __name__ == "__main__":
    main()
