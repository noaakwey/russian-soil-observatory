#!/usr/bin/env python3
"""Retry evidence-backed Russian administrative places with nominative queries.

The original cached request is never discarded: before replacement it is
copied to ``place_geocode_attempt``.  Only a unique Nominatim administrative
boundary result is allowed to replace an office/settlement centroid.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import time
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from audit_unpromoted_geocodes import BROADER_STUDY
from promote_geocoded_places import REFERENCE_OR_AFFILIATION
from geocode_place_candidates import precision


def normalize(place: str) -> str:
    value = re.sub(r"\s+", " ", place.replace("\u00ad", "")).strip(" ,.;:")
    # Common Russian oblique forms in article prose.  This is intentionally
    # conservative: uncertain names are queried unchanged and remain review
    # candidates rather than being guessed into a different municipality.
    rules = (
        (r"\b([А-Яа-яЁё-]+)ского\s+района\b", r"\1ский район"),
        (r"\b([А-Яа-яЁё-]+)ском\s+районе\b", r"\1ский район"),
        (r"\b([А-Яа-яЁё-]+)скому\s+району\b", r"\1ский район"),
        (r"\b([А-Яа-яЁё-]+)ской\s+области\b", r"\1ская область"),
        (r"\b([А-Яа-яЁё-]+)ской\s+областью\b", r"\1ская область"),
        (r"\b([А-Яа-яЁё-]+)ском\s+крае\b", r"\1ский край"),
        (r"\b([А-Яа-яЁё-]+)ском\s+округе\b", r"\1ский округ"),
    )
    for pattern, replacement in rules:
        value = re.sub(pattern, replacement, value, flags=re.I)
    return value


def lookup(query: str) -> tuple[dict | None, str, list[dict]]:
    url = "https://nominatim.openstreetmap.org/search?" + urlencode({
        "q": query + ", Russia", "format": "jsonv2", "limit": "10",
        "countrycodes": "ru", "addressdetails": "1",
    })
    request = Request(url, headers={"User-Agent": "RussianSoilObservatory/1.0 (research-provenance geocoder)"})
    with urlopen(request, timeout=30) as response:
        results = json.loads(response.read().decode())
    administrative = [r for r in results if r.get("type") == "administrative"
                      and (r.get("address", {}).get("country_code") or "").upper() == "RU"]
    return (administrative[0] if len(administrative) == 1 else None), url, results


def ensure_history(con: sqlite3.Connection) -> None:
    con.execute("""CREATE TABLE IF NOT EXISTS place_geocode_attempt (
        attempt_id INTEGER PRIMARY KEY AUTOINCREMENT,
        candidate_id TEXT NOT NULL REFERENCES place_candidate(candidate_id),
        provider TEXT NOT NULL, query_text TEXT NOT NULL, display_name TEXT,
        country_code TEXT, latitude REAL, longitude REAL, geometry_kind TEXT,
        spatial_precision_m REAL, source_url TEXT, raw_json TEXT, status TEXT NOT NULL,
        replaced_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(candidate_id, provider, query_text, raw_json)
    )""")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--limit-unique", type=int, default=0)
    p.add_argument("--delay", type=float, default=1.1)
    p.add_argument("--include-unchanged", action="store_true",
                   help="Also retry already nominative spellings with boundary-only selection.")
    p.add_argument("--dry-run", action="store_true")
    a = p.parse_args()
    stats: dict[str, int] = defaultdict(int)
    with sqlite3.connect(a.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT pc.candidate_id,pc.place_text,pc.context_text,pg.geometry_kind,pg.display_name
            FROM place_candidate pc JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
            WHERE pc.status='unreviewed' AND pg.status='accepted' AND pg.country_code='RU'
              AND pc.administrative_level IN ('district','region')
        """).fetchall()
        grouped: dict[str, list[sqlite3.Row]] = defaultdict(list)
        for row in rows:
            context = row["context_text"] or ""
            if REFERENCE_OR_AFFILIATION.search(context) or not BROADER_STUDY.search(context):
                continue
            query = normalize(row["place_text"])
            if query and (query != row["place_text"] or a.include_unchanged):
                grouped[query].append(row)
        queries = sorted(grouped)
        if a.limit_unique:
            queries = queries[:a.limit_unique]
        if not a.dry_run:
            ensure_history(con)
        for query in queries:
            stats["unique_queries"] += 1
            try:
                result, url, results = lookup(query)
            except Exception:
                stats["network_error"] += 1
                time.sleep(a.delay)
                continue
            if not result:
                stats["not_unique_administrative_boundary"] += 1
                time.sleep(a.delay)
                continue
            record = {
                "provider": "Nominatim-normalized-v1", "query_text": query,
                "display_name": result.get("display_name"), "country_code": "RU",
                "latitude": float(result["lat"]), "longitude": float(result["lon"]),
                "geometry_kind": "boundary_centroid", "spatial_precision_m": precision(result),
                "source_url": url, "raw_json": json.dumps(result, ensure_ascii=False), "status": "accepted",
            }
            for row in grouped[query]:
                stats["candidate_mentions"] += 1
                if not a.dry_run:
                    con.execute("""INSERT OR IGNORE INTO place_geocode_attempt
                        (candidate_id,provider,query_text,display_name,country_code,latitude,longitude,geometry_kind,
                         spatial_precision_m,source_url,raw_json,status)
                        SELECT candidate_id,provider,query_text,display_name,country_code,latitude,longitude,geometry_kind,
                               spatial_precision_m,source_url,raw_json,status
                        FROM place_geocode WHERE candidate_id=?""", (row["candidate_id"],))
                    con.execute("""UPDATE place_geocode SET provider=:provider,query_text=:query_text,
                        display_name=:display_name,country_code=:country_code,latitude=:latitude,longitude=:longitude,
                        geometry_kind=:geometry_kind,spatial_precision_m=:spatial_precision_m,source_url=:source_url,
                        raw_json=:raw_json,status=:status,geocoded_at=CURRENT_TIMESTAMP WHERE candidate_id=:candidate_id""",
                        {**record, "candidate_id": row["candidate_id"]})
                stats["replaced"] += 1
            if not a.dry_run:
                con.commit()
            time.sleep(a.delay)
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
