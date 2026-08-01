#!/usr/bin/env python3
"""Classify every remaining validated Russian coordinate candidate consistently."""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import Counter
from pathlib import Path

from audit_degree_decimal_minutes import DIRECT, RANGE
from audit_new_coordinate_context import MAP_GRID, classify


def category(context: str) -> str:
    if MAP_GRID.search(context or "") and (context or "").count("°") >= 4:
        return "coordinate_range_or_extent"
    if RANGE.search(context):
        return "coordinate_range_or_extent"
    if DIRECT.search(context):
        return "direct_labeled_field_object"
    return classify(context)


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument("--db", type=Path, required=True); p.add_argument("--output", type=Path, required=True); a = p.parse_args()
    fields = ["candidate_id", "precision_hint", "document_id", "corpus", "latitude", "longitude", "category", "context_text"]
    rows = []
    with sqlite3.connect(a.db) as con:
        for rec in con.execute("""SELECT lc.candidate_id,lc.precision_hint,d.document_id,d.corpus,lc.latitude,lc.longitude,lc.context_text
            FROM location_candidate lc JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
            JOIN extraction e ON e.extraction_id=lc.extraction_id JOIN source_artifact a ON a.artifact_id=e.artifact_id
            JOIN document d ON d.document_id=a.document_id
            WHERE lc.status='unreviewed' AND lv.country_code='RU' AND lv.result='inside'
            ORDER BY d.corpus,d.document_id,lc.candidate_id"""):
            item = dict(zip(fields[:-2] + ["context_text"], rec))
            item["category"] = category(item["context_text"] or "")
            rows.append(item)
    with a.output.open("w", encoding="utf-8", newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    print({"candidates":len(rows),"categories":dict(Counter(r["category"] for r in rows))})


if __name__ == "__main__": main()
