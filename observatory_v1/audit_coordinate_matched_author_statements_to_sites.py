#!/usr/bin/env python3
"""Stage strict author-statement-to-site links without changing operational data.

The source statement itself must print a coordinate, and exactly one reported
site with evidence from that same document must have that coordinate.  This is
stronger than document-level co-occurrence and intentionally produces a review
CSV instead of filling ``profile`` automatically.
"""
from __future__ import annotations

import argparse
import csv
import json
import sqlite3
from pathlib import Path

from audit_profile_context_coordinate import coords


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    rows: list[dict[str, object]] = []
    stats = {"statements_scanned": 0, "with_printed_coordinate": 0,
             "unique_site_match": 0, "ambiguous_site_match": 0}
    with sqlite3.connect(a.db) as con:
        con.row_factory = sqlite3.Row
        statements = con.execute("""
            SELECT c.candidate_id,c.document_id,c.artifact_id,c.field_name,
                   c.profile_label_raw,c.raw_value,c.evidence_text,c.linkable
            FROM document_author_statement_candidate c
            ORDER BY c.document_id,c.candidate_id
        """).fetchall()
        for stmt in statements:
            stats["statements_scanned"] += 1
            printed = list(coords(stmt["evidence_text"] or ""))
            if not printed:
                continue
            stats["with_printed_coordinate"] += 1
            matches: set[str] = set()
            for lat, lon, _start, _end in printed:
                found = con.execute("""
                    SELECT DISTINCT s.site_id
                    FROM site s
                    JOIN site_evidence se ON se.site_id=s.site_id
                    JOIN source_artifact sa ON sa.artifact_id=se.artifact_id
                    WHERE sa.document_id=?
                      AND abs(s.latitude-?) < 0.000001
                      AND abs(s.longitude-?) < 0.000001
                      AND s.spatial_confidence IN ('exact','reported')
                """, (stmt["document_id"], lat, lon)).fetchall()
                matches.update(r[0] for r in found)
            if len(matches) != 1:
                stats["ambiguous_site_match"] += int(bool(matches))
                continue
            stats["unique_site_match"] += 1
            site_id = next(iter(matches))
            site = con.execute("SELECT latitude,longitude FROM site WHERE site_id=?", (site_id,)).fetchone()
            rows.append({
                "candidate_id": stmt["candidate_id"], "document_id": stmt["document_id"],
                "artifact_id": stmt["artifact_id"], "site_id": site_id,
                "latitude": site[0], "longitude": site[1], "field_name": stmt["field_name"],
                "profile_label_raw": stmt["profile_label_raw"] or "", "raw_value": stmt["raw_value"],
                "linkable": stmt["linkable"], "evidence_text": stmt["evidence_text"],
            })
    fields = ["candidate_id", "document_id", "artifact_id", "site_id", "latitude", "longitude",
              "field_name", "profile_label_raw", "raw_value", "linkable", "evidence_text"]
    with a.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(rows)
    print(json.dumps({**stats, "selected": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
