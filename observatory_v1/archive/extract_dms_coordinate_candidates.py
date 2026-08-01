#!/usr/bin/env python3
"""Append explicit DMS coordinates to the strict coordinate evidence layer.

The original strict rebuild intentionally avoided ambiguous decimal pairs.  It
did not, however, cover common paper notation such as ``51°31′ N, 36°07′ E``.
This append-only pass requires both cardinal directions, validates degree / 
minute / second bounds, and never alters existing coordinates or sites.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

DMS = re.compile(
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2})(?:\s*[′'’]\s*(?P<lat_s>\d{1,2}(?:[.,]\d+)?))?\s*[″\"”]?\s*(?P<lat_h>[NSСЮ])"
    r"\s*[,;()]?\s*(?P<lon_d>\d{1,3})\s*[°º]\s*(?P<lon_m>\d{1,2})(?:\s*[′'’]\s*(?P<lon_s>\d{1,2}(?:[.,]\d+)?))?\s*[″\"”]?\s*(?P<lon_h>[EWВЗ])",
    re.I,
)


def value(degrees: str, minutes: str, seconds: str | None, hemisphere: str) -> float:
    d, m = float(degrees), float(minutes)
    s = float((seconds or "0").replace(",", "."))
    if not 0 <= m < 60 or not 0 <= s < 60:
        raise ValueError("invalid DMS minute/second")
    number = d + m / 60 + s / 3600
    return -number if hemisphere.upper() in {"S", "Ю", "W", "З"} else number


def source_files(springer: Path, pochvovedenie: Path):
    for path in sorted(springer.glob("*.txt")):
        yield path, f"springer:{path.stem}"
    for path in sorted(pochvovedenie.glob("*.txt")):
        yield path, f"pochvovedenie:{path.stem}"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--springer-text-dir", type=Path, required=True)
    p.add_argument("--pochvovedenie-text-dir", type=Path, required=True)
    args = p.parse_args()
    stats = {"texts": 0, "dms_matches": 0, "added": 0, "invalid": 0, "unknown_document": 0}
    with sqlite3.connect(args.db) as con:
        known = {r[0] for r in con.execute("SELECT document_id FROM document")}
        for path, doc_id in source_files(args.springer_text_dir, args.pochvovedenie_text_dir):
            if doc_id not in known:
                stats["unknown_document"] += 1
                continue
            extraction_id = f"{doc_id}:text:raw"
            if not con.execute("SELECT 1 FROM extraction WHERE extraction_id=?", (extraction_id,)).fetchone():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for index, match in enumerate(DMS.finditer(text)):
                stats["dms_matches"] += 1
                try:
                    lat = value(match["lat_d"], match["lat_m"], match["lat_s"], match["lat_h"])
                    lon = value(match["lon_d"], match["lon_m"], match["lon_s"], match["lon_h"])
                    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                        raise ValueError("outside geographic bounds")
                except ValueError:
                    stats["invalid"] += 1
                    continue
                context = text[max(0, match.start() - 220):min(len(text), match.end() + 260)].replace("\n", " ")
                cursor = con.execute(
                    """INSERT OR IGNORE INTO location_candidate
                       (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                       VALUES(?,?,?,?,NULL,NULL,'dms_cardinal',?,'unreviewed')""",
                    (f"{extraction_id}:dms:l:{index}", extraction_id, lat, lon, context),
                )
                stats["added"] += int(cursor.rowcount > 0)
            stats["texts"] += 1
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
