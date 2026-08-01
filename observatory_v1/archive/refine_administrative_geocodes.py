#!/usr/bin/env python3
"""Retry Russian administrative names in nominative form without losing history.

The first pass queried raw paper wording (often a genitive/prepositional
form), which can resolve to an office or a homonymous locality.  This tool
normalizes only district/region names, accepts only one administrative
boundary result, and stores every previous/new response in an append-only
attempt table before replacing the current cache row.
"""
from __future__ import annotations

import argparse
import json
import math
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from audit_unpromoted_geocodes import BROADER_STUDY
from promote_geocoded_places import REFERENCE_OR_AFFILIATION


ENDPOINT = "https://nominatim.openstreetmap.org/search"
GENERIC = {"карта района", "схема района", "район", "область", "край", "республика"}


def normalize(place: str, level: str) -> str | None:
    value = re.sub(r"\s+", " ", place or "").strip(" ,.;:")
    if value.casefold() in GENERIC:
        return None
    if level == "district":
        match = re.fullmatch(r"(.+?)\s+район(?:а|е|у|ом|ы)?", value, re.I)
        if match:
            adjective = match.group(1).strip()
            low = adjective.casefold()
            if low.endswith("ского"):
                # ``Ремонтненского`` -> ``Ремонтненский``: retain ``ск``
                # and replace only the genitive ending ``ого``.
                adjective = adjective[:-3] + "ий"
            elif low.endswith("ском"):
                # ``Прохоровском`` -> ``Прохоровский``.
                adjective = adjective[:-2] + "ий"
            return adjective + " район"
    if level == "region":
        match = re.fullmatch(r"(.+?)\s+област(?:ь|и|ью)", value, re.I)
        if match:
            adjective = match.group(1).strip()
            if adjective.casefold().endswith("ской"):
                adjective = adjective[:-4] + "ская"
            return adjective + " область"
        if value.casefold().startswith("республике "):
            return "Республика " + value.split(" ", 1)[1]
    return value


def precision(result: dict) -> float | None:
    box = result.get("boundingbox")
    if not box or len(box) != 4:
        return None
    south, north, west, east = map(float, box)
    lat = (south + north) / 2
    return math.hypot((north - south) * 111_000, (east - west) * 111_000 * math.cos(math.radians(lat))) / 2


def lookup(query: str) -> tuple[list[dict], str]:
    url = ENDPOINT + "?" + urlencode({"q": query + ", Russia", "format": "jsonv2", "limit": 10,
                                        "countrycodes": "ru", "addressdetails": "1"})
    req = Request(url, headers={"User-Agent": "RussianSoilObservatory/1.0 (research-provenance geocoder)"})
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode()), url


def administrative(results: list[dict]) -> list[dict]:
    return [r for r in results if r.get("type") == "administrative" or r.get("class") == "boundary"]


def ensure_schema(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS place_geocode_attempt (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id TEXT NOT NULL REFERENCES place_candidate(candidate_id),
        provider TEXT NOT NULL, query_text TEXT NOT NULL, display_name TEXT,
        country_code TEXT, latitude REAL, longitude REAL, geometry_kind TEXT,
        spatial_precision_m REAL, source_url TEXT, raw_json TEXT NOT NULL,
        status TEXT NOT NULL, reason TEXT NOT NULL, attempted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
    )""")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--limit-unique", type=int, default=0)
    ap.add_argument("--delay", type=float, default=1.1)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    stats: dict[str, int] = defaultdict(int)
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        ensure_schema(con)
        rows = con.execute("""
            SELECT pc.candidate_id,pc.place_text,pc.administrative_level,pc.context_text,pg.status AS old_status
            FROM place_candidate pc JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
            WHERE pc.status='unreviewed' AND pg.status='accepted'
              AND pc.administrative_level IN ('district','region')
        """).fetchall()
        grouped: dict[tuple[str, str], list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            context = row["context_text"] or ""
            if REFERENCE_OR_AFFILIATION.search(context) or not BROADER_STUDY.search(context):
                continue
            query = normalize(row["place_text"], row["administrative_level"])
            if not query:
                continue
            grouped[(row["administrative_level"], query)].append(row)
        items = sorted(grouped.items())
        if args.limit_unique:
            items = items[:args.limit_unique]
        for (level, query), candidates in items:
            stats["unique_queries"] += 1
            try:
                results, url = lookup(query)
                matches = administrative(results)
                if len(matches) == 1:
                    result = matches[0]
                    country = (result.get("address", {}).get("country_code") or "").upper()
                    status = "accepted" if country == "RU" else "rejected"
                    reason = "unique_administrative_boundary" if status == "accepted" else "non_russian_boundary"
                elif not matches:
                    result = None; status = "unresolved"; reason = "no_administrative_boundary"
                else:
                    result = None; status = "ambiguous"; reason = "multiple_administrative_boundaries"
            except Exception as exc:
                results = {"error": str(exc)}; url = None; result = None; status = "unresolved"; reason = "request_failed"
            stats[status] += 1
            for candidate in candidates:
                record = (candidate["candidate_id"], "Nominatim-normalized-admin-v1", query,
                          result.get("display_name") if result else None,
                          (result.get("address", {}).get("country_code") or "").upper() if result else None,
                          float(result["lat"]) if result else None, float(result["lon"]) if result else None,
                          "boundary_centroid" if result else "unresolved",
                          precision(result) if result else None, url,
                          json.dumps(result if result else results, ensure_ascii=False), status, reason)
                if args.apply:
                    old = con.execute("SELECT provider,query_text,display_name,country_code,latitude,longitude,geometry_kind,spatial_precision_m,source_url,raw_json,status FROM place_geocode WHERE candidate_id=?", (candidate["candidate_id"],)).fetchone()
                    if old:
                        con.execute("""INSERT INTO place_geocode_attempt(candidate_id,provider,query_text,display_name,country_code,latitude,longitude,geometry_kind,spatial_precision_m,source_url,raw_json,status,reason)
                            VALUES(?,?,?,?,?,?,?,?,?,?,?,?, 'superseded_current_cache')""", (candidate["candidate_id"], *old))
                    con.execute("""INSERT INTO place_geocode_attempt(candidate_id,provider,query_text,display_name,country_code,latitude,longitude,geometry_kind,spatial_precision_m,source_url,raw_json,status,reason)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)""", record)
                    if status == "accepted":
                        con.execute("""UPDATE place_geocode SET provider=?,query_text=?,display_name=?,country_code=?,latitude=?,longitude=?,geometry_kind=?,spatial_precision_m=?,source_url=?,raw_json=?,status=?,geocoded_at=CURRENT_TIMESTAMP WHERE candidate_id=?""",
                                    (*record[1:-1], candidate["candidate_id"]))
            if args.apply:
                con.commit()
            time.sleep(args.delay)
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
