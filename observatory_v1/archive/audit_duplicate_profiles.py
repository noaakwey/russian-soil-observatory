#!/usr/bin/env python3
"""Report exact duplicate profiles created by parallel coordinate parsers."""
from __future__ import annotations

import argparse
import csv
import sqlite3
from collections import defaultdict
from pathlib import Path


def norm(label: str | None) -> str:
    return "".join((label or "").casefold().split())


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""SELECT DISTINCT d.document_id,p.profile_id,p.profile_label,p.site_id,
                    s.latitude,s.longitude,
                    (SELECT count(*) FROM horizon h WHERE h.profile_id=p.profile_id) horizons,
                    (SELECT count(*) FROM sample sm WHERE sm.profile_id=p.profile_id) samples,
                    (SELECT count(*) FROM measurement m WHERE m.profile_id=p.profile_id) measurements,
                    (SELECT count(*) FROM profile_author_statement ps WHERE ps.profile_id=p.profile_id) statements
             FROM profile p JOIN site s ON s.site_id=p.site_id
             JOIN site_evidence se ON se.site_id=s.site_id
             JOIN source_artifact a ON a.artifact_id=se.artifact_id
             JOIN document d ON d.document_id=a.document_id
             WHERE s.spatial_confidence IN ('exact','reported')""").fetchall()
    clusters: dict[tuple[str, float, float, str], list[sqlite3.Row]] = defaultdict(list)
    for row in rows:
        if not norm(row['profile_label']):
            continue
        clusters[(row['document_id'], round(row['latitude'], 7), round(row['longitude'], 7), norm(row['profile_label']))].append(row)
    output = []
    for (document_id, lat, lon, label), values in sorted(clusters.items()):
        ids = {row['profile_id'] for row in values}
        if len(ids) < 2:
            continue
        for row in values:
            output.append({"document_id": document_id, "latitude": lat, "longitude": lon,
                           "normalized_label": label, **dict(row)})
    fields = ['document_id','latitude','longitude','normalized_label','profile_id','profile_label','site_id',
              'horizons','samples','measurements','statements']
    with args.output.open('w', encoding='utf-8', newline='') as fh:
        writer = csv.DictWriter(fh, fieldnames=fields); writer.writeheader(); writer.writerows(output)
    print({"duplicate_clusters": len({(x['document_id'],x['latitude'],x['longitude'],x['normalized_label']) for x in output}),
           "profile_rows": len(output), "output": str(args.output)})


if __name__ == '__main__':
    main()
