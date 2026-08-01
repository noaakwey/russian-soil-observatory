#!/usr/bin/env python3
"""Read-only parser audit for Vanchikova et al. (Pochvovedenie 2021, Table 1).

The PDF-to-text table is vertical rather than delimited.  A row is emitted
only when a direct-coordinate profile label is followed by a horizon, a depth
interval and exactly 12 scalar cells in the published column order.  This is
an auditable template, not a generic OCR guesser.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

from extract_russian_abbreviated_coordinates import DECIMAL, DMS, dms_value


DOCUMENT = "pochvovedenie:Pochved2102015Vanchikova"
PROFILE = re.compile(r"Разрез\s+([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{0,24})", re.I)
DEPTH = re.compile(r"^\d+(?:[.,]\d+)?\s*[–-]\s*\d+(?:[.,]\d+)?$")
SCALAR = re.compile(r"^(?:\d+(?:[.,]\d+)?|[-−])$")
SIGNATURE = ("Характеристика образцов почв", "Горизонт", "Глубина", "Н2О", "KCl", "Сорг", "SiO2", "Fe2O3", "Al2O3", "Na2O")


def lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", row).strip() for row in text.splitlines() if row.strip()]


def parse_depth(value: str) -> tuple[float, float]:
    left, right = re.split(r"\s*[–-]\s*", value)
    return float(left.replace(",", ".")), float(right.replace(",", "."))


def coordinate_matches(block: str, latitude: float, longitude: float) -> bool:
    for match in DMS.finditer(block):
        try:
            lat, lon = dms_value(match, "lat", match["lat_h"]), dms_value(match, "lon", match["lon_h"])
            if abs(lat - latitude) < 1e-6 and abs(lon - longitude) < 1e-6:
                return True
        except ValueError:
            continue
    for match in DECIMAL.finditer(block):
        lat, lon = float(match["lat"].replace(",", ".")), float(match["lon"].replace(",", "."))
        if abs(lat - latitude) < 1e-6 and abs(lon - longitude) < 1e-6:
            return True
    return False


def profile_block(text: str, label: str, latitude: float, longitude: float) -> tuple[str, str] | None:
    matches = [m for m in PROFILE.finditer(text) if m.group(1).casefold() == label.casefold()]
    for match in matches:
        start = match.start()
        next_match = PROFILE.search(text, match.end())
        block = text[start:next_match.start() if next_match else min(len(text), start + 2500)]
        if coordinate_matches(block, latitude, longitude):
            return text[max(0, start - 1100):start], block
    return None


def first_coordinate_end(text: str) -> int | None:
    found = [m.end() for pat in (DMS, DECIMAL) for m in pat.finditer(text)]
    return min(found) if found else None


def source_text(con: sqlite3.Connection, artifact_id: str, source_path: str) -> str | None:
    """Read the immutable source artifact, falling back to its DB copy.

    Early ingestion ran on Linux and retained absolute source paths.  Those
    paths are not portable, while ``extraction.raw_text`` is the actual
    provenance-preserving copy used by the database.
    """
    path = Path(source_path)
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    row = con.execute(
        """SELECT raw_text FROM extraction
           WHERE artifact_id=? AND raw_text IS NOT NULL
           ORDER BY length(raw_text) DESC LIMIT 1""",
        (artifact_id,),
    ).fetchone()
    return row[0] if row and row[0] else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    stats = {"direct_profiles": 0, "signature_mismatch": 0, "unparseable": 0, "parsed": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        profiles = con.execute(
            """SELECT p.profile_id,p.profile_label,p.site_id,s.latitude,s.longitude,a.artifact_id,a.source_path
               FROM profile p JOIN site s ON s.site_id=p.site_id
               JOIN profile_evidence pe ON pe.profile_id=p.profile_id AND pe.evidence_kind='profile_description'
               JOIN source_artifact a ON a.artifact_id=pe.artifact_id
               WHERE p.notes='Direct profile-label-to-coordinate link in one source fragment.'
                 AND a.document_id=?""", (DOCUMENT,)
        ).fetchall()
        for profile in profiles:
            stats["direct_profiles"] += 1
            text = source_text(con, profile["artifact_id"], profile["source_path"])
            if not text:
                stats["missing_source"] = stats.get("missing_source", 0) + 1
                continue
            found = profile_block(text, profile["profile_label"], profile["latitude"], profile["longitude"])
            if not found:
                stats["unparseable"] += 1; continue
            header, block = found
            # Table 1 has a single header followed by many profiles; for later
            # rows the header lies farther back than the local profile window.
            if not all(token.casefold() in text.casefold() for token in SIGNATURE):
                stats["signature_mismatch"] += 1; continue
            coord_end = first_coordinate_end(block)
            if coord_end is None:
                stats["unparseable"] += 1; continue
            tail = lines(block[coord_end:])
            while tail and re.fullmatch(r"\[\d+(?:[–-]\d+)?\]", tail[0]):
                tail.pop(0)
            if len(tail) < 14 or not DEPTH.fullmatch(tail[1]):
                stats["unparseable"] += 1; continue
            values = tail[2:14]
            if len(values) != 12 or not all(SCALAR.fullmatch(v) for v in values):
                stats["unparseable"] += 1; continue
            top, bottom = parse_depth(tail[1])
            rows.append({
                "profile_id": profile["profile_id"], "profile_label": profile["profile_label"],
                "site_id": profile["site_id"], "latitude": profile["latitude"], "longitude": profile["longitude"],
                "horizon_label": tail[0], "depth_top_cm": top, "depth_bottom_cm": bottom,
                "ph_h2o_raw": values[0], "ph_kcl_raw": values[1], "water_soluble_carbon_mgkg_raw": values[2],
                "soil_organic_carbon_pct_raw": values[3], "sio2_pct_raw": values[4], "fe2o3_pct_raw": values[5],
                "al2o3_pct_raw": values[6], "cao_pct_raw": values[7], "mgo_pct_raw": values[8],
                "k2o_pct_raw": values[9], "na2o_pct_raw": values[10], "fine_fraction_pct_raw": values[11],
                "source_block": " | ".join(lines(block)[:40]),
            })
            stats["parsed"] += 1
    fields = list(rows[0]) if rows else ["profile_id"]
    with args.output.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
