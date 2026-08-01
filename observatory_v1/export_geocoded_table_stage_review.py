#!/usr/bin/env python3
"""Export would-stage geocoded table values with their spatial evidence.

This is deliberately a review artifact.  A document having one geocoded
context does not prove that every table inside it belongs to that locality.
The CSV puts the table cell, the selected locality evidence and all other
place mentions of the document side by side before any flagged measurement is
created.
"""
from __future__ import annotations

import argparse
import csv
import sqlite3
from pathlib import Path

from normalize_measurement_candidates import convert
from stage_supported_table_measurements import observation_reason, plausible, query_for


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    rows: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        cur = con.execute(query_for("geocoded"))
        for raw in cur:
            rec = dict(raw)
            value, unit, status, _warning = convert(rec["value_num"], rec["unit_raw"], rec["canonical_unit"], rec["property_id"])
            if status not in {"exact", "converted"} or not plausible(value, unit) or observation_reason(rec, value, unit):
                continue
            contexts = con.execute(
                """SELECT pc.place_text,pc.administrative_level,pg.display_name,s.site_id,se.evidence_text
                   FROM site s
                   JOIN site_evidence se ON se.site_id=s.site_id AND se.evidence_kind='location_text'
                   JOIN source_artifact a ON a.artifact_id=se.artifact_id
                   LEFT JOIN place_candidate pc ON s.site_id='site:place:'||pc.candidate_id
                   LEFT JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
                   WHERE a.document_id=? AND s.spatial_confidence='geocoded'
                   ORDER BY s.site_id""", (rec["document_id"],),
            ).fetchall()
            places = con.execute(
                """SELECT pc.place_text,pc.administrative_level,pc.status
                   FROM place_candidate pc
                   JOIN extraction e ON e.extraction_id=pc.extraction_id
                   JOIN source_artifact a ON a.artifact_id=e.artifact_id
                   WHERE a.document_id=? ORDER BY place_text""", (rec["document_id"],),
            ).fetchall()
            rows.append({
                "candidate_id": rec["candidate_id"], "document_id": rec["document_id"], "site_id": rec["site_id"],
                "property_id": rec["property_id"], "header": rec["property_header_raw"],
                "value_normalized": value, "unit_normalized": unit, "value_raw": rec["value_num"],
                "unit_raw": rec["unit_raw"], "row_label": rec["row_label_raw"], "horizon_label": rec["horizon_label"],
                "depth_top_cm": rec["depth_top_cm"], "depth_bottom_cm": rec["depth_bottom_cm"],
                "geocoded_contexts": "\n---\n".join(
                    f"{r['site_id']} | {r['place_text']} | {r['administrative_level']} | {r['display_name']}\n{r['evidence_text']}"
                    for r in contexts),
                "all_document_place_mentions": "; ".join(
                    f"{r['place_text']} ({r['administrative_level']},{r['status']})" for r in places),
            })
    fields = list(rows[0]) if rows else []
    with args.output.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(f"would_stage={len(rows)} documents={len({r['document_id'] for r in rows})}")


if __name__ == "__main__":
    main()
