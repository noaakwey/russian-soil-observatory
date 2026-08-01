#!/usr/bin/env python3
"""Stage explicit Russian decimal-degree coordinate pairs from full-text sources."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


LAT, LON = r"(?:с\.\s*ш\.)", r"(?:в\.\s*д\.)"
LAT_FIRST = re.compile(rf"(?P<lat>\d{{1,2}}[.,]\d{{2,7}})\s*°?\s*{LAT}\s*[,;()\-–— ]+"
                       rf"(?P<lon>\d{{2,3}}[.,]\d{{2,7}})\s*°?\s*{LON}", re.I)
LON_FIRST = re.compile(rf"(?P<lon>\d{{2,3}}[.,]\d{{2,7}})\s*°?\s*{LON}\s*[,;()\-–— ]+"
                       rf"(?P<lat>\d{{1,2}}[.,]\d{{2,7}})\s*°?\s*{LAT}", re.I)


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--db", type=Path, required=True); a = p.parse_args()
    stats = {"artifacts": 0, "matches": 0, "added": 0, "invalid": 0}
    with sqlite3.connect(a.db) as con:
        for extraction_id, raw in con.execute("""SELECT e.extraction_id,e.raw_text FROM extraction e
            JOIN source_artifact a ON a.artifact_id=e.artifact_id WHERE a.artifact_type='text' AND e.raw_text IS NOT NULL"""):
            stats["artifacts"] += 1
            for kind, pattern in (("lat_first", LAT_FIRST), ("lon_first", LON_FIRST)):
                for index, m in enumerate(pattern.finditer(raw)):
                    stats["matches"] += 1
                    try:
                        lat, lon = float(m["lat"].replace(",", ".")), float(m["lon"].replace(",", "."))
                        if not (-90 <= lat <= 90 and -180 <= lon <= 180): raise ValueError
                    except ValueError:
                        stats["invalid"] += 1; continue
                    context = raw[max(0,m.start()-280):min(len(raw),m.end()+380)].replace("\n"," ")
                    cur = con.execute("""INSERT OR IGNORE INTO location_candidate
                        (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                        VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
                        (f"{extraction_id}:russian_decimal_degrees:{kind}:{index}", extraction_id, lat, lon,
                         "russian_decimal_degrees_cardinal", context))
                    stats["added"] += int(cur.rowcount > 0)
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__": main()
