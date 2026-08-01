#!/usr/bin/env python3
"""Audit or append explicit coordinates written with Russian hemisphere abbreviations.

Examples accepted by this narrowly scoped scanner are ``51°30′ с. ш.,
36°07′ в. д.`` and ``51.50 с.ш.; 36.12 в.д.``.  Both axes and their
hemispheres must be printed in one source fragment.  The default is dry-run;
``--apply`` merely stages candidates and never creates operational sites.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


LAT_HEM = r"(?:N|S|С\s*\.?\s*Ш\s*\.?|Ю\s*\.?\s*Ш\s*\.?)"
LON_HEM = r"(?:E|W|В\s*\.?\s*Д\s*\.?|З\s*\.?\s*Д\s*\.?)"
SEP = r"\s*[,;()\-–—]+\s*"
# A minute prime may appear without seconds: ``51°30′``.  If seconds are
# present they are nested inside the prime suffix, e.g. ``51°30′12.4″``.
DMS_PART = r"(?P<{p}_d>\d{{1,3}})\s*[°º]\s*(?P<{p}_m>\d{{1,2}})(?:\s*[′'’](?:\s*(?P<{p}_s>\d{{1,2}}(?:[.,]\d+)?)\s*[″\"”]?)?)?"
DMS = re.compile(
    DMS_PART.format(p="lat") + r"\s*(?P<lat_h>" + LAT_HEM + r")" + SEP
    + DMS_PART.format(p="lon") + r"\s*(?P<lon_h>" + LON_HEM + r")", re.I,
)
DECIMAL = re.compile(
    r"(?P<lat>\d{1,2}[.,]\d{2,7})\s*°?\s*(?P<lat_h>" + LAT_HEM + r")" + SEP
    + r"(?P<lon>\d{2,3}[.,]\d{2,7})\s*°?\s*(?P<lon_h>" + LON_HEM + r")", re.I,
)


def negative(hem: str) -> bool:
    return bool(re.search(r"(?:^|\s)(?:S|W|Ю|З)", hem.upper()))


def dms_value(match: re.Match[str], prefix: str, hem: str) -> float:
    degrees = float(match[f"{prefix}_d"])
    minutes = float(match[f"{prefix}_m"])
    seconds = float((match[f"{prefix}_s"] or "0").replace(",", "."))
    if not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("invalid DMS component")
    value = degrees + minutes / 60 + seconds / 3600
    return -value if negative(hem) else value


def source_files(springer: Path, pochvovedenie: Path):
    for path in sorted(springer.glob("*.txt")):
        yield path, f"springer:{path.stem}"
    for path in sorted(pochvovedenie.glob("*.txt")):
        yield path, f"pochvovedenie:{path.stem}"


def exists(con: sqlite3.Connection, extraction_id: str, lat: float, lon: float) -> bool:
    return bool(con.execute(
        """SELECT 1 FROM location_candidate WHERE extraction_id=?
           AND ABS(latitude-?) < 0.0000001 AND ABS(longitude-?) < 0.0000001 LIMIT 1""",
        (extraction_id, lat, lon),
    ).fetchone())


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--springer-text-dir", type=Path, required=True)
    p.add_argument("--pochvovedenie-text-dir", type=Path, required=True)
    p.add_argument("--apply", action="store_true")
    args = p.parse_args()
    stats = {"texts": 0, "dms_matches": 0, "decimal_matches": 0, "existing": 0,
             "new_candidates": 0, "invalid": 0, "unknown_document": 0}
    examples: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        known = {row[0] for row in con.execute("SELECT document_id FROM document")}
        for path, document_id in source_files(args.springer_text_dir, args.pochvovedenie_text_dir):
            if document_id not in known:
                stats["unknown_document"] += 1
                continue
            extraction_id = f"{document_id}:text:raw"
            if not con.execute("SELECT 1 FROM extraction WHERE extraction_id=?", (extraction_id,)).fetchone():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for kind, pattern in (("dms", DMS), ("decimal", DECIMAL)):
                for index, match in enumerate(pattern.finditer(text)):
                    stats[f"{kind}_matches"] += 1
                    try:
                        if kind == "dms":
                            lat, lon = dms_value(match, "lat", match["lat_h"]), dms_value(match, "lon", match["lon_h"])
                        else:
                            lat = float(match["lat"].replace(",", "."))
                            lon = float(match["lon"].replace(",", "."))
                            if negative(match["lat_h"]): lat = -lat
                            if negative(match["lon_h"]): lon = -lon
                        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                            raise ValueError("outside bounds")
                    except (ValueError, TypeError):
                        stats["invalid"] += 1
                        continue
                    if exists(con, extraction_id, lat, lon):
                        stats["existing"] += 1
                        continue
                    context = text[max(0, match.start()-240):min(len(text), match.end()+320)].replace("\n", " ")
                    stats["new_candidates"] += 1
                    if len(examples) < 20:
                        examples.append({"document_id": document_id, "kind": kind, "latitude": lat, "longitude": lon, "context": context})
                    if args.apply:
                        con.execute(
                            """INSERT OR IGNORE INTO location_candidate
                               (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                               VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
                            (f"{extraction_id}:ru_abbr:{kind}:{index}", extraction_id, lat, lon,
                             f"russian_abbreviated_{kind}", context),
                        )
            stats["texts"] += 1
        if args.apply:
            con.commit()
    stats["examples"] = examples
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
