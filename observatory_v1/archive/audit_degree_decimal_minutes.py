#!/usr/bin/env python3
"""Classify degree-minute candidates before any operational promotion.

The exact same typography is used for a soil pit and for a study-area extent.
Range endpoints are retained as evidence but are never promoted as sampling
sites.  A promotion-ready record must also name a concrete field object.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path

from audit_new_coordinate_context import classify


RANGE = re.compile(r"\d{1,3}\s*[°º]\s*\d{1,2}(?:[.,]\d+)?\s*[′'’]?\s*[–—-]\s*\d{1,3}", re.I)
DIRECT = re.compile(
    r"(?:\b(?:soil\s+)?(?:profile|pit|borehole|site|plot|point)\s*(?:no\.?\s*)?[A-Za-z0-9-]+\b|"
    r"(?:разрез|разр\.?|скважин|точк|профил|участ|площадк)\w*\s*(?:№\s*)?[A-Za-zА-Яа-я0-9-]+)",
    re.I,
)


def category(context: str) -> str:
    if RANGE.search(context):
        return "coordinate_range_or_extent"
    if DIRECT.search(context):
        return "direct_labeled_field_object"
    return classify(context)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--precision-hint", default="degree_decimal_minutes_cardinal")
    args = parser.parse_args()
    fields = ["candidate_id", "document_id", "corpus", "latitude", "longitude", "category", "context_text"]
    rows = []
    with sqlite3.connect(args.db) as con:
        for row in con.execute(
            """SELECT lc.candidate_id,d.document_id,d.corpus,lc.latitude,lc.longitude,lc.context_text
                 FROM location_candidate lc
                 JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
                 JOIN extraction e ON e.extraction_id=lc.extraction_id
                 JOIN source_artifact a ON a.artifact_id=e.artifact_id
                 JOIN document d ON d.document_id=a.document_id
                WHERE lc.precision_hint=?
                  AND lc.status='unreviewed' AND lv.country_code='RU' AND lv.result='inside'
                ORDER BY d.document_id,lc.candidate_id""",
            (args.precision_hint,)
        ):
            candidate_id, document_id, corpus, lat, lon, context = row
            rows.append({"candidate_id": candidate_id, "document_id": document_id, "corpus": corpus,
                         "latitude": lat, "longitude": lon, "category": category(context or ""),
                         "context_text": context})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    counts = {}
    for row in rows:
        counts[row["category"]] = counts.get(row["category"], 0) + 1
    print({"candidates": len(rows), "categories": counts})


if __name__ == "__main__":
    main()
