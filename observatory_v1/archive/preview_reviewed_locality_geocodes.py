#!/usr/bin/env python3
"""Fetch a review-only Nominatim preview for selected locality candidates.

No SQLite table is changed.  The resulting CSV is inspected before the cached
geocode and low-precision ``site`` records are written.  This keeps a
geocoder's first answer from silently becoming spatial evidence.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import time
from pathlib import Path

from geocode_place_candidates import lookup, precision


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    ap.add_argument("--delay", type=float, default=1.1)
    args = ap.parse_args()
    rows = list(csv.DictReader(args.input.open(encoding="utf-8", newline="")))
    with sqlite3.connect(args.db) as con:
        for row in rows:
            found = con.execute(
                "SELECT place_text FROM place_candidate WHERE candidate_id=?",
                (row["candidate_id"],),
            ).fetchone()
            if not found:
                raise SystemExit(f"Unknown candidate_id: {row['candidate_id']}")
            row["place_text"] = found[0]
    result_rows: list[dict[str, str]] = []
    for row in rows:
        # The review file may provide an article-derived district/region to
        # disambiguate a common village.  The literal ``place_text`` remains
        # the evidence stored in SQLite; this is query context only.
        place = row.get("geocode_query") or row["place_text"]
        try:
            results, source_url = lookup(place)
            if len(results) == 1:
                item = results[0]
                country = (item.get("address", {}).get("country_code") or "").upper()
                result_rows.append({
                    **row, "preview_status": "accepted" if country == "RU" else "non_ru",
                    "display_name": item.get("display_name", ""), "country_code": country,
                    "latitude": item.get("lat", ""), "longitude": item.get("lon", ""),
                    "geometry_kind": "boundary_centroid" if item.get("class") == "boundary" or item.get("type") == "administrative" else "centroid",
                    "spatial_precision_m": str(precision(item) or ""), "source_url": source_url,
                    "raw_json": json.dumps(item, ensure_ascii=False),
                })
            else:
                result_rows.append({
                    **row, "preview_status": "ambiguous" if results else "unresolved",
                    "display_name": "", "country_code": "", "latitude": "", "longitude": "",
                    "geometry_kind": "", "spatial_precision_m": "", "source_url": source_url,
                    "raw_json": json.dumps(results, ensure_ascii=False),
                })
        except Exception as exc:
            result_rows.append({
                **row, "preview_status": "failed", "display_name": "", "country_code": "",
                "latitude": "", "longitude": "", "geometry_kind": "", "spatial_precision_m": "",
                "source_url": "", "raw_json": json.dumps({"error": str(exc)}, ensure_ascii=False),
            })
        time.sleep(args.delay)
    fields = list(rows[0]) + ["preview_status", "display_name", "country_code", "latitude", "longitude",
                               "geometry_kind", "spatial_precision_m", "source_url", "raw_json"] if rows else []
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(result_rows)
    print(json.dumps({"selected": len(rows), "by_status": {
        status: sum(item["preview_status"] == status for item in result_rows)
        for status in sorted({item["preview_status"] for item in result_rows})
    }}, ensure_ascii=False))


if __name__ == "__main__":
    main()
