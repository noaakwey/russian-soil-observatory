#!/usr/bin/env python3
"""Discover explicit cardinal-coordinate formats missed by the primary parser.

This scanner accepts only pairs that carry both latitude and longitude
cardinal letters.  It starts in ``--dry-run`` mode by default and can append
deduplicated candidates only when ``--apply`` is supplied.  It never creates
sites or measurements.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

# Direction before its decimal degree, e.g. ``N 55.12, E 37.56``.
LEADING_DECIMAL = re.compile(
    r"(?P<lat_h>[NSСЮ])\s*(?P<lat>\d{1,2}[.,]\d{2,7})\s*°?"
    r"\s*[,;()\-–— ]+\s*(?P<lon_h>[EWВЗ])\s*(?P<lon>\d{2,3}[.,]\d{2,7})\s*°?",
    re.I,
)
# Explicit but longitude-first notation, e.g. ``37.56 E; 55.12 N``.
REVERSED_DECIMAL = re.compile(
    r"(?P<lon>\d{2,3}[.,]\d{2,7})\s*°?\s*(?P<lon_h>[EWВЗ])"
    r"\s*[,;()\-–— ]+\s*(?P<lat>\d{1,2}[.,]\d{2,7})\s*°?\s*(?P<lat_h>[NSСЮ])",
    re.I,
)

DMS_VALUE = r"(?P<{p}_d>\d{{1,3}})\s*[°º]\s*(?P<{p}_m>\d{{1,2}})(?:\s*[′'’]\s*(?P<{p}_s>\d{{1,2}}(?:[.,]\d+)?))?\s*[″\"”]?"
LEADING_DMS = re.compile(
    r"(?P<lat_h>[NSСЮ])\s*" + DMS_VALUE.format(p="lat") +
    r"\s*[,;()\-–— ]+\s*(?P<lon_h>[EWВЗ])\s*" + DMS_VALUE.format(p="lon"), re.I,
)
REVERSED_DMS = re.compile(
    DMS_VALUE.format(p="lon") + r"\s*(?P<lon_h>[EWВЗ])"
    r"\s*[,;()\-–— ]+\s*" + DMS_VALUE.format(p="lat") + r"\s*(?P<lat_h>[NSСЮ])", re.I,
)


def dec(value: str) -> float:
    return float(value.replace(",", "."))


def dms(match: re.Match[str], prefix: str, hemisphere: str) -> float:
    degrees = dec(match[f"{prefix}_d"])
    minutes = dec(match[f"{prefix}_m"])
    seconds = dec(match[f"{prefix}_s"] or "0")
    if not 0 <= minutes < 60 or not 0 <= seconds < 60:
        raise ValueError("invalid DMS component")
    value = degrees + minutes / 60 + seconds / 3600
    return -value if hemisphere.upper() in {"S", "Ю", "W", "З"} else value


def signed(value: float, hemisphere: str) -> float:
    return -value if hemisphere.upper() in {"S", "Ю", "W", "З"} else value


def files(springer: Path, pochvovedenie: Path):
    for path in sorted(springer.glob("*.txt")):
        yield path, f"springer:{path.stem}"
    for path in sorted(pochvovedenie.glob("*.txt")):
        yield path, f"pochvovedenie:{path.stem}"


def has_same_coordinate(con: sqlite3.Connection, extraction_id: str, lat: float, lon: float) -> bool:
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
    p.add_argument("--include-leading", action="store_true",
                   help="also inspect latitude-first cardinal decimal pairs; use dry-run before --apply")
    p.add_argument("--include-dms", action="store_true",
                   help="also inspect cardinal DMS pairs; use dry-run before --apply")
    p.add_argument("--limit-texts", type=int, help="diagnostic cap; omit for the full corpus")
    p.add_argument("--start-offset", type=int, default=0, help="number of source texts to skip")
    p.add_argument("--audit-output", type=Path,
                   help="write every valid match with its source context to CSV; does not alter the database")
    a = p.parse_args()
    # A leading direction and DMS map-grid labels can appear as visually
    # adjacent but unrelated labels after PDF text extraction.  Keep the
    # proven longitude-first decimal form as the safe default.  The broader
    # patterns are deliberately opt-in, so they can be audited on the full
    # text corpus before any candidate is staged.
    patterns: tuple[tuple[str, re.Pattern[str]], ...] = (("reversed_decimal", REVERSED_DECIMAL),)
    if a.include_leading:
        patterns += (("leading_decimal", LEADING_DECIMAL),)
    if a.include_dms:
        patterns += (("leading_dms", LEADING_DMS), ("reversed_dms", REVERSED_DMS))
    stats = {"texts": 0, "raw_matches": 0, "existing_coordinate": 0, "new_candidates": 0, "invalid": 0, "unknown_document": 0,
             "by_kind": {kind: 0 for kind, _ in patterns}}
    examples: list[dict[str, object]] = []
    audit_rows: list[dict[str, object]] = []
    with sqlite3.connect(a.db) as con:
        documents = {r[0] for r in con.execute("SELECT document_id FROM document")}
        for file_number, (path, document_id) in enumerate(files(a.springer_text_dir, a.pochvovedenie_text_dir), start=1):
            if file_number <= a.start_offset:
                continue
            if a.limit_texts and file_number > a.start_offset + a.limit_texts:
                break
            if document_id not in documents:
                stats["unknown_document"] += 1
                continue
            extraction_id = f"{document_id}:text:raw"
            if not con.execute("SELECT 1 FROM extraction WHERE extraction_id=?", (extraction_id,)).fetchone():
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for kind, pattern in patterns:
                for index, m in enumerate(pattern.finditer(text)):
                    stats["raw_matches"] += 1
                    stats["by_kind"][kind] += 1
                    try:
                        if "dms" in kind:
                            lat, lon = dms(m, "lat", m["lat_h"]), dms(m, "lon", m["lon_h"])
                        else:
                            lat, lon = signed(dec(m["lat"]), m["lat_h"]), signed(dec(m["lon"]), m["lon_h"])
                        if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                            raise ValueError("outside bounds")
                    except (ValueError, TypeError):
                        stats["invalid"] += 1
                        continue
                    if has_same_coordinate(con, extraction_id, lat, lon):
                        stats["existing_coordinate"] += 1
                    context = text[max(0, m.start() - 240):min(len(text), m.end() + 320)].replace("\n", " ")
                    audit_rows.append({
                        "document_id": document_id, "extraction_id": extraction_id,
                        "kind": kind, "latitude": lat, "longitude": lon,
                        "already_registered": has_same_coordinate(con, extraction_id, lat, lon),
                        "matched_text": m.group(0), "context": context,
                    })
                    if audit_rows[-1]["already_registered"]:
                        continue
                    stats["new_candidates"] += 1
                    if len(examples) < 20:
                        examples.append({"document_id": document_id, "kind": kind, "latitude": lat, "longitude": lon, "context": context})
                    if a.apply:
                        con.execute(
                            """INSERT OR IGNORE INTO location_candidate
                               (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                               VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
                            (f"{extraction_id}:variant:{kind}:{index}", extraction_id, lat, lon,
                             f"variant_{kind}", context),
                        )
            stats["texts"] += 1
        if a.apply:
            con.commit()
    stats["examples"] = examples
    if a.audit_output:
        with a.audit_output.open("w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["document_id", "extraction_id", "kind", "latitude", "longitude", "already_registered", "matched_text", "context"])
            writer.writeheader()
            writer.writerows(audit_rows)
    print(json.dumps(stats, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
