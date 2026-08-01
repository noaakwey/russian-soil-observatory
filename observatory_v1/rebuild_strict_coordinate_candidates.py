#!/usr/bin/env python3
"""Rebuild explicit-coordinate candidates without accepting table numerals.

Only decimal pairs bearing both cardinal markers (N/S and E/W) enter the
operational coordinate workflow.  This is intentionally stricter than OCR
discovery and prevents a table's unrelated adjacent values from becoming a
false Russian site.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


COORD = re.compile(
    r"(?P<lat>\d{1,2}[.,]\d{2,7})\s*°?\s*[NSСЮ]\s*[,; ]+"
    r"(?P<lon>\d{2,3}[.,]\d{2,7})\s*°?\s*[EWВЗ]",
    re.I,
)
# Require an explicit UTM marker *and* a zone.  This excludes generic pairs of
# metre values in tables while allowing articles that report field coordinates
# as easting/northing.
UTM = re.compile(
    r"\bUTM\b[^\n]{0,100}?(?:zone|зона)\s*(?P<zone>\d{1,2})\s*(?P<hemisphere>[NSСЮ])?"
    r"[^\n]{0,120}?(?P<easting>\d{5,7}(?:[.,]\d+)?)\s*[,;\s]+(?P<northing>\d{6,8}(?:[.,]\d+)?)",
    re.I,
)


def number(value: str) -> float:
    return float(value.replace(",", "."))


def context(text: str, start: int, end: int) -> str:
    return text[max(0, start - 220):min(len(text), end + 260)].replace("\n", " ")


def utm_to_wgs84(zone: int, easting: float, northing: float, hemisphere: str | None) -> tuple[float, float]:
    """Convert UTM to WGS84 without a server-side GIS dependency.

    Snyder's transverse-Mercator inverse on the WGS84 ellipsoid.  It is used
    only after explicit ``UTM zone`` evidence has been found in the source.
    """
    import math

    a = 6378137.0
    ecc_sq = 0.0066943799901413165
    k0 = 0.9996
    x = easting - 500000.0
    y = northing - (10_000_000.0 if hemisphere and hemisphere.upper() in {"S", "Ю"} else 0.0)
    ecc_prime_sq = ecc_sq / (1 - ecc_sq)
    m = y / k0
    mu = m / (a * (1 - ecc_sq / 4 - 3 * ecc_sq**2 / 64 - 5 * ecc_sq**3 / 256))
    e1 = (1 - math.sqrt(1 - ecc_sq)) / (1 + math.sqrt(1 - ecc_sq))
    phi1 = mu + (3 * e1 / 2 - 27 * e1**3 / 32) * math.sin(2 * mu) + (21 * e1**2 / 16 - 55 * e1**4 / 32) * math.sin(4 * mu) + (151 * e1**3 / 96) * math.sin(6 * mu)
    n1 = a / math.sqrt(1 - ecc_sq * math.sin(phi1) ** 2)
    t1 = math.tan(phi1) ** 2
    c1 = ecc_prime_sq * math.cos(phi1) ** 2
    r1 = a * (1 - ecc_sq) / (1 - ecc_sq * math.sin(phi1) ** 2) ** 1.5
    d = x / (n1 * k0)
    lat = phi1 - (n1 * math.tan(phi1) / r1) * (d**2 / 2 - (5 + 3 * t1 + 10 * c1 - 4 * c1**2 - 9 * ecc_prime_sq) * d**4 / 24 + (61 + 90 * t1 + 298 * c1 + 45 * t1**2 - 252 * ecc_prime_sq - 3 * c1**2) * d**6 / 720)
    lon0 = math.radians((zone - 1) * 6 - 180 + 3)
    lon = lon0 + (d - (1 + 2 * t1 + c1) * d**3 / 6 + (5 - 2 * c1 + 28 * t1 - 3 * c1**2 + 8 * ecc_prime_sq + 24 * t1**2) * d**5 / 120) / math.cos(phi1)
    return math.degrees(lat), math.degrees(lon)


def sources(springer: Path, pochvovedenie: Path):
    for path in sorted(springer.glob("*.txt")):
        yield "springer", path, f"springer:{path.stem}"
    for path in sorted(pochvovedenie.glob("*.txt")):
        yield "pochvovedenie", path, f"pochvovedenie:{path.stem}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--springer-text-dir", type=Path, required=True)
    parser.add_argument("--pochvovedenie-text-dir", type=Path, required=True)
    args = parser.parse_args()
    stats = {"texts": 0, "decimal_cardinal": 0, "utm": 0, "unknown_documents": 0, "utm_errors": 0}
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        # These candidates and their country decisions are fully regenerable.
        con.execute("DELETE FROM location_validation")
        con.execute("DELETE FROM location_candidate")
        known = {row[0] for row in con.execute("SELECT document_id FROM document")}
        for _corpus, path, document_id in sources(args.springer_text_dir, args.pochvovedenie_text_dir):
            if document_id not in known:
                stats["unknown_documents"] += 1
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            extraction_id = f"{document_id}:text:raw"
            if not con.execute("SELECT 1 FROM extraction WHERE extraction_id=?", (extraction_id,)).fetchone():
                continue
            for index, match in enumerate(COORD.finditer(text)):
                lat, lon = number(match.group("lat")), number(match.group("lon"))
                if lat > 90 or lon > 180:
                    continue
                con.execute(
                    """INSERT INTO location_candidate
                    (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                    VALUES(?,?,?,?,NULL,NULL,'decimal_degrees_cardinal',?,'unreviewed')""",
                    (f"{extraction_id}:strict:l:{index}", extraction_id, lat, lon, context(text, match.start(), match.end())),
                )
                stats["decimal_cardinal"] += 1
            for index, match in enumerate(UTM.finditer(text)):
                try:
                    zone = int(match.group("zone"))
                    if not 1 <= zone <= 60:
                        raise ValueError("invalid UTM zone")
                    easting, northing = number(match.group("easting")), number(match.group("northing"))
                    if not 100_000 <= easting <= 900_000 or not 0 <= northing <= 10_000_000:
                        raise ValueError("invalid UTM coordinates")
                    lat, lon = utm_to_wgs84(zone, easting, northing, match.group("hemisphere"))
                    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                        raise ValueError("invalid UTM projection result")
                except Exception:
                    stats["utm_errors"] += 1
                    continue
                con.execute(
                    """INSERT INTO location_candidate
                    (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                    VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
                    (f"{extraction_id}:strict:utm:{index}", extraction_id, lat, lon,
                     f"utm_zone_{zone}", context(text, match.start(), match.end())),
                )
                stats["utm"] += 1
            stats["texts"] += 1
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
