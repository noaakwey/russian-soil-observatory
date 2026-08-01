#!/usr/bin/env python3
"""Annotate text-derived locality candidates before any geocoding.

This is intentionally a review-only operation.  It tells a reviewer whether
the source document already contains one or more author-reported coordinates,
so a named village/city is not accidentally promoted as a second sampling
point or a substitute for a more precise existing location.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    with args.input.open(encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    stats = {"input": len(rows), "documents_with_reported_sites": 0,
             "candidates_without_reported_site": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        for row in rows:
            sites = con.execute("""
                SELECT DISTINCT s.site_id,s.latitude,s.longitude,s.spatial_confidence
                FROM site s
                JOIN site_evidence se ON se.site_id=s.site_id
                JOIN source_artifact a ON a.artifact_id=se.artifact_id
                WHERE a.document_id=? AND s.spatial_confidence IN ('exact','reported')
                ORDER BY s.site_id
            """, (row["document_id"],)).fetchall()
            row["reported_site_count_in_document"] = str(len(sites))
            row["reported_site_ids_in_document"] = "; ".join(site["site_id"] for site in sites)
            row["reported_coordinates_in_document"] = "; ".join(
                f"{site['latitude']:.6f},{site['longitude']:.6f}" for site in sites
            )
            if sites:
                stats["documents_with_reported_sites"] += 1
            else:
                stats["candidates_without_reported_site"] += 1
    fields = list(rows[0]) + ["reported_site_count_in_document", "reported_site_ids_in_document",
                              "reported_coordinates_in_document"] if rows else []
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
