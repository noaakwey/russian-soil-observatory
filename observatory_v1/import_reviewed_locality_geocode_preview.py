#!/usr/bin/env python3
"""Import only an already inspected locality-geocode preview into SQLite.

The preview generator is read-only.  This separate step makes the transition
from an external answer to an auditable cached geocode explicit and accepts
only unique Russian results selected in the review CSV.
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
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    stats = {"rows": len(rows), "accepted": 0, "unresolved_or_ambiguous": 0,
             "inserted": 0, "replaced": 0}
    with sqlite3.connect(args.db) as con:
        for row in rows:
            accepted = row["preview_status"] == "accepted" and row["country_code"] == "RU"
            stats["accepted" if accepted else "unresolved_or_ambiguous"] += 1
            desired_status = "accepted" if accepted else row["preview_status"]
            exists = con.execute(
                """SELECT provider,query_text,display_name,country_code,latitude,longitude,geometry_kind,
                          spatial_precision_m,source_url,raw_json,status
                   FROM place_geocode WHERE candidate_id=?""",
                (row["candidate_id"],),
            ).fetchone()
            if not args.dry_run:
                if exists:
                    con.execute(
                        """INSERT INTO place_geocode_attempt(candidate_id,provider,query_text,display_name,country_code,
                                                              latitude,longitude,geometry_kind,spatial_precision_m,
                                                              source_url,raw_json,status,reason)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["candidate_id"], *exists,
                         "replaced_by_reviewed_locality_preview_with_article_context"),
                    )
                    con.execute(
                        """UPDATE place_geocode
                           SET provider=?,query_text=?,display_name=?,country_code=?,latitude=?,longitude=?,
                               geometry_kind=?,spatial_precision_m=?,source_url=?,raw_json=?,status=?,
                               geocoded_at=CURRENT_TIMESTAMP
                           WHERE candidate_id=?""",
                        ("Nominatim-reviewed-locality-v1", row.get("geocode_query") or row["place_text"],
                         row["display_name"] or None, row["country_code"] or None,
                         float(row["latitude"]) if row["latitude"] else None,
                         float(row["longitude"]) if row["longitude"] else None,
                         row["geometry_kind"] or "unresolved",
                         float(row["spatial_precision_m"]) if row["spatial_precision_m"] else None,
                         row["source_url"] or None, row["raw_json"], desired_status, row["candidate_id"]),
                    )
                    stats["replaced"] += 1
                else:
                    con.execute(
                        """INSERT INTO place_geocode(candidate_id,provider,query_text,display_name,country_code,
                                                       latitude,longitude,geometry_kind,spatial_precision_m,
                                                       source_url,raw_json,status)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["candidate_id"], "Nominatim-reviewed-locality-v1", row.get("geocode_query") or row["place_text"],
                         row["display_name"] or None, row["country_code"] or None,
                         float(row["latitude"]) if row["latitude"] else None,
                         float(row["longitude"]) if row["longitude"] else None,
                         row["geometry_kind"] or "unresolved",
                         float(row["spatial_precision_m"]) if row["spatial_precision_m"] else None,
                         row["source_url"] or None, row["raw_json"], desired_status),
                    )
                    stats["inserted"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
