#!/usr/bin/env python3
"""Rate-limited, cached administrative geocoding for reported Russian places.

One request is made per distinct source spelling, never per mention.  The
result is then copied to every evidence-backed occurrence of that spelling.
Administrative centroids remain a separate, lower-confidence spatial tier.
"""
from __future__ import annotations

import argparse
import json
import math
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

ENDPOINT = "https://nominatim.openstreetmap.org/search"


def precision(result: dict) -> float | None:
    box = result.get("boundingbox")
    if not box or len(box) != 4:
        return None
    south, north, west, east = map(float, box)
    lat = (south + north) / 2
    return math.hypot((north - south) * 111_000, (east - west) * 111_000 * math.cos(math.radians(lat))) / 2


def lookup(query: str) -> tuple[list[dict], str]:
    url = ENDPOINT + "?" + urlencode({"q": query + ", Russia", "format": "jsonv2", "limit": "2", "countrycodes": "ru", "addressdetails": "1"})
    request = Request(url, headers={"User-Agent": "RussianSoilObservatory/1.0 (research-provenance geocoder)"})
    with urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8")), url


def insert(con: sqlite3.Connection, candidate_id: str, place: str, record: dict) -> None:
    con.execute(
        """INSERT INTO place_geocode(candidate_id,provider,query_text,display_name,country_code,latitude,longitude,
           geometry_kind,spatial_precision_m,source_url,raw_json,status)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (candidate_id, "Nominatim", place, record.get("display_name"), record.get("country_code"),
         record.get("latitude"), record.get("longitude"), record["geometry_kind"], record.get("spatial_precision_m"),
         record.get("source_url"), record["raw_json"], record["status"]),
    )


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--levels", default="district,region")
    p.add_argument("--delay", type=float, default=1.1)
    p.add_argument("--limit-unique", type=int, default=0, help="0 means all unique place spellings")
    a = p.parse_args()
    levels = tuple(x.strip() for x in a.levels.split(",") if x.strip())
    stats = defaultdict(int)
    with sqlite3.connect(a.db) as con:
        rows = con.execute(
            f"""SELECT pc.candidate_id, pc.place_text FROM place_candidate pc
                 LEFT JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
                 WHERE pc.status='unreviewed' AND pg.candidate_id IS NULL
                   AND pc.administrative_level IN ({','.join('?' * len(levels))})
                 ORDER BY pc.place_text, pc.candidate_id""", levels).fetchall()
        grouped: dict[str, list[str]] = defaultdict(list)
        for cid, place in rows:
            grouped[place].append(cid)
        places = sorted(grouped)
        if a.limit_unique:
            places = places[:a.limit_unique]
        for place in places:
            candidate_ids = grouped[place]
            stats["unique_queries"] += 1
            stats["candidate_mentions"] += len(candidate_ids)
            try:
                results, url = lookup(place)
                if len(results) == 1:
                    result = results[0]
                    country = (result.get("address", {}).get("country_code") or "").upper()
                    status = "accepted" if country == "RU" else "rejected"
                    kind = "boundary_centroid" if result.get("class") == "boundary" or result.get("type") == "administrative" else "centroid"
                    record = {"display_name": result.get("display_name"), "country_code": country,
                              "latitude": float(result["lat"]), "longitude": float(result["lon"]),
                              "geometry_kind": kind, "spatial_precision_m": precision(result), "source_url": url,
                              "raw_json": json.dumps(result, ensure_ascii=False), "status": status}
                    stats["accepted" if status == "accepted" else "rejected"] += 1
                elif len(results) > 1:
                    record = {"geometry_kind": "unresolved", "source_url": url, "raw_json": json.dumps(results, ensure_ascii=False), "status": "ambiguous"}
                    stats["ambiguous"] += 1
                else:
                    record = {"geometry_kind": "unresolved", "source_url": url, "raw_json": "[]", "status": "unresolved"}
                    stats["unresolved"] += 1
            except Exception as exc:
                record = {"geometry_kind": "unresolved", "raw_json": json.dumps({"error": str(exc)}, ensure_ascii=False), "status": "unresolved"}
                stats["failed"] += 1
            for cid in candidate_ids:
                insert(con, cid, place, record)
            con.commit()
            time.sleep(a.delay)
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
