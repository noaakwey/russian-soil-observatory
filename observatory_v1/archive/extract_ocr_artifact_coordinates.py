#!/usr/bin/env python3
"""Append only explicit cardinal coordinates found within OCR table artifacts.

This recovers evidence from Springer records that have table crops but lack a
full article PDF/text.  A coordinate must occur as one continuous, explicitly
labelled string inside the OCR extraction; independent numeric cells are never
joined into a coordinate pair.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

DECIMAL = re.compile(r"(?P<lat>\d{1,2}[.,]\d{2,7})\s*°?\s*[NSСЮ]\s*[,; ]+\s*(?P<lon>\d{2,3}[.,]\d{2,7})\s*°?\s*[EWВЗ]", re.I)
REVERSED_DECIMAL = re.compile(r"(?P<lon>\d{2,3}[.,]\d{2,7})\s*°?\s*[EWВЗ]\s*[,; ]+\s*(?P<lat>\d{1,2}[.,]\d{2,7})\s*°?\s*[NSСЮ]", re.I)
DMS = re.compile(
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2})(?:\s*[′'’]\s*(?P<lat_s>\d{1,2}(?:[.,]\d+)?))?\s*[″\"”]?\s*(?P<lat_h>[NSСЮ])"
    r"\s*[,;()]?\s*(?P<lon_d>\d{1,3})\s*[°º]\s*(?P<lon_m>\d{1,2})(?:\s*[′'’]\s*(?P<lon_s>\d{1,2}(?:[.,]\d+)?))?\s*[″\"”]?\s*(?P<lon_h>[EWВЗ])", re.I)
# Table headers often place longitude before latitude.  This remains a
# separate extraction class: a map-grid-like pair is still only a raw
# candidate until it passes country and local-object review.
REVERSED_DMS = re.compile(
    r"(?P<lon_d>\d{1,3})\s*[°º]\s*(?P<lon_m>\d{1,2})(?:\s*[′'’]\s*(?P<lon_s>\d{1,2}(?:[.,]\d+)?))?\s*[″\"”]?\s*(?P<lon_h>[EWВЗ])"
    r"\s*[,;()]?\s*(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2})(?:\s*[′'’]\s*(?P<lat_s>\d{1,2}(?:[.,]\d+)?))?\s*[″\"”]?\s*(?P<lat_h>[NSСЮ])", re.I)


def dms(d, m, s, h):
    degrees, minutes, seconds = float(d), float(m), float((s or "0").replace(",", "."))
    if not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError
    x = degrees + minutes / 60 + seconds / 3600
    return -x if h.upper() in {"S", "Ю", "W", "З"} else x


def add(con, extraction_id, index, lat, lon, raw, start, end, kind, stats):
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        stats["invalid"] += 1; return
    context = raw[max(0, start - 220): min(len(raw), end + 260)].replace("\n", " ")
    cur = con.execute(
        """INSERT OR IGNORE INTO location_candidate
           (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
           VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
        (f"{extraction_id}:ocr_coord:{kind}:{index}", extraction_id, lat, lon, f"ocr_{kind}_cardinal", context),
    )
    stats["added"] += int(cur.rowcount > 0)


def main():
    p = argparse.ArgumentParser(); p.add_argument("--db", type=Path, required=True); a = p.parse_args()
    stats = {"artifacts": 0, "decimal_matches": 0, "reversed_decimal_matches": 0, "dms_matches": 0, "reversed_dms_matches": 0, "added": 0, "invalid": 0}
    with sqlite3.connect(a.db) as con:
        con.execute("PRAGMA busy_timeout=30000")
        rows = con.execute("""SELECT e.extraction_id,e.raw_text FROM extraction e
                            JOIN source_artifact a ON a.artifact_id=e.artifact_id
                            WHERE a.artifact_type='ocr_markdown' AND e.raw_text IS NOT NULL""")
        for extraction_id, raw in rows:
            stats["artifacts"] += 1
            for i, match in enumerate(DECIMAL.finditer(raw)):
                stats["decimal_matches"] += 1
                add(con, extraction_id, i, float(match['lat'].replace(',', '.')), float(match['lon'].replace(',', '.')), raw, match.start(), match.end(), "decimal", stats)
            for i, match in enumerate(REVERSED_DECIMAL.finditer(raw)):
                stats["reversed_decimal_matches"] += 1
                add(con, extraction_id, i, float(match['lat'].replace(',', '.')), float(match['lon'].replace(',', '.')), raw, match.start(), match.end(), "reversed_decimal", stats)
            for i, match in enumerate(DMS.finditer(raw)):
                stats["dms_matches"] += 1
                try: lat, lon = dms(match['lat_d'], match['lat_m'], match['lat_s'], match['lat_h']), dms(match['lon_d'], match['lon_m'], match['lon_s'], match['lon_h'])
                except ValueError: stats["invalid"] += 1; continue
                add(con, extraction_id, i, lat, lon, raw, match.start(), match.end(), "dms", stats)
            for i, match in enumerate(REVERSED_DMS.finditer(raw)):
                stats["reversed_dms_matches"] += 1
                try:
                    lat = dms(match['lat_d'], match['lat_m'], match['lat_s'], match['lat_h'])
                    lon = dms(match['lon_d'], match['lon_m'], match['lon_s'], match['lon_h'])
                except ValueError:
                    stats["invalid"] += 1; continue
                add(con, extraction_id, i, lat, lon, raw, match.start(), match.end(), "reversed_dms", stats)
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__': main()
