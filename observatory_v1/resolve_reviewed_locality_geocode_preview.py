#!/usr/bin/env python3
"""Turn explicitly reviewed Nominatim result choices into a new preview CSV."""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from geocode_place_candidates import precision


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--preview", type=Path, required=True)
    ap.add_argument("--resolutions", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows = list(csv.DictReader(args.preview.open(encoding="utf-8", newline="")))
    decisions = {row["candidate_id"]: row for row in csv.DictReader(args.resolutions.open(encoding="utf-8", newline=""))}
    applied = 0
    for row in rows:
        decision = decisions.get(row["candidate_id"])
        if not decision:
            continue
        options = json.loads(row["raw_json"])
        index = int(decision["result_index"])
        if not isinstance(options, list) or index < 0 or index >= len(options):
            raise SystemExit(f"Invalid reviewed result index for {row['candidate_id']}")
        item = options[index]
        country = (item.get("address", {}).get("country_code") or "").upper()
        if country != "RU":
            raise SystemExit(f"Reviewed result is not Russian for {row['candidate_id']}")
        row.update({
            "preview_status": "accepted", "display_name": item.get("display_name", ""),
            "country_code": country, "latitude": item.get("lat", ""), "longitude": item.get("lon", ""),
            "geometry_kind": "boundary_centroid" if item.get("class") == "boundary" or item.get("type") == "administrative" else "centroid",
            "spatial_precision_m": str(precision(item) or ""), "raw_json": json.dumps(item, ensure_ascii=False),
            "reviewed_resolution_reason": decision["reason"],
        })
        applied += 1
    fields = list(rows[0])
    if "reviewed_resolution_reason" not in fields:
        fields.append("reviewed_resolution_reason")
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({"rows": len(rows), "reviewed_choices_applied": applied}, ensure_ascii=False))


if __name__ == "__main__":
    main()
