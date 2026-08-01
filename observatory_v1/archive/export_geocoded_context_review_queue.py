#!/usr/bin/env python3
"""Export, never promote, the mechanically eligible region/district queue."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from audit_geocode_quality import SQL, tier


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = []
        for source in con.execute(SQL):
            row = dict(source)
            if tier(row) != "candidate_geocoded_study_context":
                continue
            artifact = con.execute(
                """SELECT a.source_path FROM place_candidate pc
                   JOIN extraction e ON e.extraction_id=pc.extraction_id
                   JOIN source_artifact a ON a.artifact_id=e.artifact_id
                   WHERE pc.candidate_id=?""", (row["candidate_id"],)
            ).fetchone()
            row["source_path"] = artifact[0] if artifact else ""
            rows.append(row)
    fields = ["candidate_id", "document_id", "administrative_level", "place_text", "display_name",
              "geometry_kind", "spatial_precision_m", "source_path", "context_text"]
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows([{key: row.get(key, "") for key in fields} for row in rows])
    print(f"exported={len(rows)}")


if __name__ == "__main__":
    main()
