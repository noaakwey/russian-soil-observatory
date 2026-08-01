#!/usr/bin/env python3
"""Deduplicate a preclassified direct-coordinate queue before promotion.

The input is an evidence audit, not a parser result.  This program checks the
live database again for Russian validation, source type and an existing
same-document coordinate.  Its output is review-only and one row represents
one document-coordinate rather than parallel parser spellings.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from collections import Counter
from pathlib import Path


ALLOWED = {"direct_labeled_field_object", "explicit_sampling_or_profile_context"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--input", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    raw = [r for r in csv.DictReader(args.input.open(encoding="utf-8", newline=""))
           if r.get("category") in ALLOWED]
    groups: dict[tuple[str, float, float], dict[str, object]] = {}
    stats: Counter[str] = Counter(input_rows=len(raw))
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        for source in raw:
            candidate = con.execute(
                """SELECT lc.candidate_id,lc.latitude,lc.longitude,lc.precision_hint,lc.context_text,
                          d.document_id,a.artifact_type,a.artifact_id
                     FROM location_candidate lc
                     JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
                     JOIN extraction e ON e.extraction_id=lc.extraction_id
                     JOIN source_artifact a ON a.artifact_id=e.artifact_id
                     JOIN document d ON d.document_id=a.document_id
                    WHERE lc.candidate_id=? AND lc.status='unreviewed'
                      AND lv.result='inside' AND lv.country_code='RU'""",
                (source["candidate_id"],),
            ).fetchone()
            if not candidate:
                stats["missing_or_not_validated"] += 1
                continue
            row = dict(candidate)
            key = (row["document_id"], round(row["latitude"], 7), round(row["longitude"], 7))
            group = groups.setdefault(key, {
                "document_id": row["document_id"], "latitude": row["latitude"], "longitude": row["longitude"],
                "categories": set(), "precision_hints": set(), "candidate_ids": [], "artifact_types": set(),
                "context_text": row["context_text"], "existing_site_ids": [],
            })
            group["categories"].add(source["category"])
            group["precision_hints"].add(row["precision_hint"])
            group["candidate_ids"].append(row["candidate_id"])
            group["artifact_types"].add(row["artifact_type"])
        for group in groups.values():
            existing = con.execute(
                """SELECT DISTINCT s.site_id FROM site s
                   JOIN site_evidence se ON se.site_id=s.site_id
                   JOIN source_artifact a ON a.artifact_id=se.artifact_id
                   WHERE a.document_id=? AND s.spatial_confidence IN ('exact','reported')
                     AND abs(s.latitude-?) < 0.000001 AND abs(s.longitude-?) < 0.000001""",
                (group["document_id"], group["latitude"], group["longitude"]),
            ).fetchall()
            group["existing_site_ids"] = [r[0] for r in existing]
            stats["already_represented" if existing else "new_document_coordinates"] += 1
    rows = []
    for group in groups.values():
        rows.append({
            "document_id": group["document_id"], "latitude": group["latitude"], "longitude": group["longitude"],
            "categories": ";".join(sorted(group["categories"])),
            "precision_hints": ";".join(sorted(group["precision_hints"])),
            "candidate_ids": ";".join(group["candidate_ids"]),
            "artifact_types": ";".join(sorted(group["artifact_types"])),
            "existing_site_ids": ";".join(group["existing_site_ids"]),
            "context_text": group["context_text"],
        })
    rows.sort(key=lambda r: (r["document_id"], r["latitude"], r["longitude"]))
    fields = list(rows[0]) if rows else []
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    stats["unique_document_coordinates"] = len(rows)
    print(json.dumps(dict(stats), ensure_ascii=False))


if __name__ == "__main__":
    main()
