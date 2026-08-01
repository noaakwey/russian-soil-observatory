#!/usr/bin/env python3
"""Independently verify every direct-profile coordinate against its raw text block.

This second-pass audit prevents a short profile label (for example, ``3``)
from accidentally inheriting a neighbouring profile's coordinate in an
extractor context window.  It changes no database row.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from extract_russian_abbreviated_coordinates import DECIMAL, DMS, dms_value, negative


# Russian papers often label the described soil body as ``Точка 2`` rather
# than ``Разрез 2``.  Both are direct sampling-object labels; keeping them in
# one pattern makes the audit stricter without losing this legitimate format.
PROFILE = re.compile(r"(?:Разрез|Точка|Point|Soil\s+(?:profile|pit)|Pit)\s+([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{0,24})", re.I)


def coordinates(text: str):
    for match in DMS.finditer(text):
        try:
            yield dms_value(match, "lat", match["lat_h"]), dms_value(match, "lon", match["lon_h"]), match.group(0)
        except ValueError:
            continue
    for match in DECIMAL.finditer(text):
        lat, lon = float(match["lat"].replace(",", ".")), float(match["lon"].replace(",", "."))
        if negative(match["lat_h"]): lat = -lat
        if negative(match["lon_h"]): lon = -lon
        yield lat, lon, match.group(0)


def main() -> None:
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--db", type=Path)
    source.add_argument("--profiles-csv", type=Path,
                        help="Exported profile_descriptions.csv; enables an offline audit.")
    parser.add_argument("--source-file", type=Path,
                        help="Raw article text for the offline, one-document audit.")
    parser.add_argument("--document-id",
                        help="Document ID to select from --profiles-csv.")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.profiles_csv and (not args.source_file or not args.document_id):
        parser.error("--profiles-csv requires --source-file and --document-id")
    rows: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    if args.db:
        with sqlite3.connect(args.db) as con:
            con.row_factory = sqlite3.Row
            direct = con.execute(
                """SELECT p.profile_id,p.profile_label,p.site_id,s.latitude,s.longitude,d.document_id,a.source_path
                   FROM profile p JOIN site s ON s.site_id=p.site_id
                   JOIN profile_evidence pe ON pe.profile_id=p.profile_id AND pe.evidence_kind='profile_description'
                   JOIN source_artifact a ON a.artifact_id=pe.artifact_id
                   JOIN document d ON d.document_id=a.document_id
                   WHERE p.notes='Direct profile-label-to-coordinate link in one source fragment.'
                   ORDER BY d.document_id,p.profile_label"""
            )
            records = [dict(record) for record in direct]
    else:
        with args.profiles_csv.open(encoding="utf-8", newline="") as handle:
            records = [row for row in csv.DictReader(handle)
                       if row.get("document_id") == args.document_id
                       and row.get("notes") == "Direct profile-label-to-coordinate link in one source fragment."]
        for rec in records:
            rec["latitude"] = float(rec["latitude"])
            rec["longitude"] = float(rec["longitude"])
            rec["source_path"] = str(args.source_file)

    for rec in records:
            path = Path(rec["source_path"])
            if not path.exists():
                rec["status"] = "missing_source"; rows.append(rec); stats[rec["status"]] += 1; continue
            text = path.read_text(encoding="utf-8", errors="replace")
            matches = [m for m in PROFILE.finditer(text) if m.group(1).casefold() == (rec["profile_label"] or "").casefold()]
            source_coordinates: list[tuple[float, float, str]] = []
            for match in matches:
                next_match = PROFILE.search(text, match.end())
                source_coordinates.extend(coordinates(text[match.start():next_match.start() if next_match else min(len(text), match.start()+2500)]))
            unique = {(round(lat, 8), round(lon, 8), raw) for lat, lon, raw in source_coordinates}
            rec["source_coordinates"] = json.dumps(sorted(unique), ensure_ascii=False)
            exact = [(lat, lon, raw) for lat, lon, raw in unique if abs(lat-rec["latitude"]) < 1e-6 and abs(lon-rec["longitude"]) < 1e-6]
            if exact:
                rec["status"] = "verified_source_coordinate"
            elif len(unique) == 1:
                rec["status"] = "source_coordinate_differs"
            elif not unique:
                rec["status"] = "no_coordinate_in_raw_profile_block"
            else:
                rec["status"] = "ambiguous_raw_profile_blocks"
            stats[rec["status"]] += 1
            rows.append(rec)
    fields = ["profile_id","document_id","profile_label","site_id","latitude","longitude","status","source_coordinates","source_path"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows([{field: row.get(field) for field in fields} for row in rows])
    print(json.dumps({"profiles": len(rows), "status": stats}, ensure_ascii=False))


if __name__ == "__main__":
    main()
