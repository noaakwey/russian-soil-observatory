#!/usr/bin/env python3
"""Stage explicit degree-and-decimal-minute coordinates from source text.

Scientific articles often print coordinates as ``51°37.348′ N, 35°15.847′ E``.
That is more precise than a map-grid tick, but was not covered by the former
decimal-degrees/DMS extractors.  This program only records source candidates;
country validation and sampling-context review remain separate gates.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path


PAIR = re.compile(
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?P<lat_h>[NSСЮ])\s*[,;()\-–— ]+"
    r"(?P<lon_d>\d{2,3})\s*[°º]\s*(?P<lon_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?P<lon_h>[EWВЗ])",
    re.I,
)

# Russian publications often spell cardinal directions out rather than using
# N/E.  Keep this as a distinct provenance class so it can be audited and
# deduplicated independently from the international notation above.
RUSSIAN_PAIR = re.compile(
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?:с\.\s*ш\.)\s*[,;()\-–— ]+"
    r"(?P<lon_d>\d{2,3})\s*[°º]\s*(?P<lon_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?:в\.\s*д\.)",
    re.I,
)

# Longitude-first ordering occurs in English figure captions and methods
# sections (``38°58′ E, 51°36′ N``).  It is opt-in because map-grid labels
# sometimes use the same visual order without denoting one study point.
REVERSED_PAIR = re.compile(
    r"(?P<lon_d>\d{2,3})\s*[°º]\s*(?P<lon_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?P<lon_h>[EWВЗ])\s*[,;()\-–— ]+"
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?P<lat_h>[NSСЮ])",
    re.I,
)

# PDF-to-text conversion commonly places the longitude on a new physical line
# after ``N,`` / ``с. ш.,``.  The regular pair deliberately did not cross that
# boundary, which meant a list of pits could yield only the one coordinate
# whose pair happened not to wrap.  Keep this separate from ``PAIR`` so old
# candidate ids and their audit history are never overwritten.
LINEBREAK_PAIR = re.compile(
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?P<lat_h>[NSСЮ])\s*[,;]?\s*\n\s*"
    r"(?P<lon_d>\d{2,3})\s*[°º]\s*(?P<lon_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?P<lon_h>[EWВЗ])",
    re.I,
)
LINEBREAK_RUSSIAN_PAIR = re.compile(
    r"(?P<lat_d>\d{1,2})\s*[°º]\s*(?P<lat_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?:с\.\s*ш\.)\s*[,;]?\s*\n\s*"
    r"(?P<lon_d>\d{2,3})\s*[°º]\s*(?P<lon_m>\d{1,2}(?:[.,]\d+)?)\s*[′'’]"
    r"\s*(?:в\.\s*д\.)",
    re.I,
)


def value(degrees: str, minutes: str, hemisphere: str) -> float:
    d = float(degrees)
    m = float(minutes.replace(",", "."))
    if not 0 <= m < 60:
        raise ValueError("minutes outside range")
    out = d + m / 60
    return -out if hemisphere.upper() in {"S", "Ю", "W", "З"} else out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--russian-only", action="store_true",
                        help="scan only с.ш./в.д. notation; avoids duplicating prior N/E candidates")
    parser.add_argument("--include-reversed", action="store_true",
                        help="also inspect longitude-first cardinal degree-minute pairs")
    parser.add_argument("--reversed-only", action="store_true",
                        help="scan only longitude-first cardinal degree-minute pairs")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--audit-output", type=Path)
    args = parser.parse_args()
    stats = {"artifacts": 0, "matches": 0, "added": 0, "invalid": 0}
    audit: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        rows = con.execute(
            """SELECT e.extraction_id,e.raw_text FROM extraction e
                 JOIN source_artifact a ON a.artifact_id=e.artifact_id
                WHERE a.artifact_type='text' AND e.raw_text IS NOT NULL"""
        )
        for extraction_id, raw in rows:
            stats["artifacts"] += 1
            patterns = (("russian_cardinal", RUSSIAN_PAIR),
                        ("russian_cardinal_multiline", LINEBREAK_RUSSIAN_PAIR)) if args.russian_only else (
                ("cardinal", PAIR), ("russian_cardinal", RUSSIAN_PAIR),
                ("cardinal_multiline", LINEBREAK_PAIR),
                ("russian_cardinal_multiline", LINEBREAK_RUSSIAN_PAIR),
            )
            if args.reversed_only:
                patterns = (("reversed_cardinal", REVERSED_PAIR),)
            elif args.include_reversed:
                patterns += (("reversed_cardinal", REVERSED_PAIR),)
            for kind, pattern in patterns:
              for index, match in enumerate(pattern.finditer(raw)):
                stats["matches"] += 1
                try:
                    lat = value(match["lat_d"], match["lat_m"], "N")
                    lon = value(match["lon_d"], match["lon_m"], "E")
                    if kind == "cardinal":
                        lat = value(match["lat_d"], match["lat_m"], match["lat_h"])
                        lon = value(match["lon_d"], match["lon_m"], match["lon_h"])
                    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
                        raise ValueError("coordinate outside range")
                except ValueError:
                    stats["invalid"] += 1
                    continue
                context = raw[max(0, match.start() - 280):min(len(raw), match.end() + 380)].replace("\n", " ")
                candidate_id = f"{extraction_id}:degree_decimal_minutes_{kind}:{index}"
                exists = bool(con.execute("SELECT 1 FROM location_candidate WHERE candidate_id=?", (candidate_id,)).fetchone())
                audit.append({"candidate_id": candidate_id, "extraction_id": extraction_id, "kind": kind,
                              "latitude": lat, "longitude": lon, "already_registered": exists,
                              "context_text": context})
                if not args.dry_run:
                    cur = con.execute(
                        """INSERT OR IGNORE INTO location_candidate
                           (candidate_id,extraction_id,latitude,longitude,place_text,country_candidate,precision_hint,context_text,status)
                           VALUES(?,?,?,?,NULL,NULL,?,?,'unreviewed')""",
                        (candidate_id, extraction_id, lat, lon, f"degree_decimal_minutes_{kind}", context),
                    )
                    stats["added"] += int(cur.rowcount > 0)
        if not args.dry_run:
            con.commit()
    if args.audit_output:
        fields = ["candidate_id", "extraction_id", "kind", "latitude", "longitude", "already_registered", "context_text"]
        with args.audit_output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields); writer.writeheader(); writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
