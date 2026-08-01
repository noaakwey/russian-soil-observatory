#!/usr/bin/env python3
"""Stage profiles when the source prints a coordinate before *or* after its label.

The older pit stage only accepted ``Pit LABEL ... coordinate``.  Journal text
and table captions also use the reverse order.  This pass starts from an
already country-validated coordinate candidate and accepts a label only when
exactly one explicit field-object label occurs in the coordinate's local text
window.  It never geocodes or associates a label across a document.
"""
from __future__ import annotations

import argparse
import csv
import csv
import hashlib
import json
import sqlite3
import re
from pathlib import Path

from audit_profile_context_coordinate import coords
from stage_explicit_labeled_pits import LABEL

SOIL_CONTEXT = re.compile(r"\bsoil\b|почв\w*|\bprofile\b|\bpit\b|разрез\w*|шурф\w*|\bcore\b|керн\w*", re.I)


def ident(*parts: str) -> str:
    return hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:20]


def local_labels(text: str, latitude: float, longitude: float) -> list[tuple[str, int, int]]:
    """Return a label that precedes its matching printed coordinate.

    PDF column order can put the next pit label visually after the previous
    pit's coordinate in extracted text.  A following label is therefore not
    sufficient automated evidence; retain those cases as candidates instead.
    """
    positions = [(start, end) for lat, lon, start, end in coords(text)
                 if abs(lat - latitude) < 1e-6 and abs(lon - longitude) < 1e-6]
    labels: list[tuple[str, int, int]] = []
    for start, end in positions:
        for label in LABEL.finditer(text):
            if label.end() <= start and start - label.end() <= 180:
                labels.append((label.group(1), label.start(), label.end()))
    # A repeated rendering of the same label is fine; competing labels are not.
    dedup = {(value.casefold(), value, start, end) for value, start, end in labels}
    return [(value, start, end) for _key, value, start, end in sorted(dedup)]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--candidate-id", action="append", default=[],
                        help="Restrict staging to audited coordinate candidate IDs.")
    parser.add_argument("--precision-suffix", default="",
                        help="optional candidate provenance suffix, e.g. _multiline")
    parser.add_argument("--candidate-csv", type=Path,
                        help="optional CSV with a candidate_id column; limits staging to that audited batch")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = {"coordinates_scanned": 0, "ambiguous_labels": 0, "missing_site": 0,
             "staged_profiles": 0}
    audit: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        rows = con.execute("""
            SELECT lc.candidate_id,lc.latitude,lc.longitude,lc.context_text,lc.precision_hint,
                   lc.extraction_id,a.artifact_id,d.document_id
            FROM location_candidate lc
            JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
            JOIN extraction e ON e.extraction_id=lc.extraction_id
            JOIN source_artifact a ON a.artifact_id=e.artifact_id
            JOIN document d ON d.document_id=a.document_id
            WHERE lc.status='accepted' AND lv.country_code='RU' AND lv.result='inside'
              AND a.artifact_type='text'
            ORDER BY d.document_id,lc.candidate_id
        """).fetchall()
        allowed = set(args.candidate_id)
        if args.candidate_csv:
            with args.candidate_csv.open(encoding="utf-8", newline="") as handle:
                allowed.update(row["candidate_id"] for row in csv.DictReader(handle) if row.get("candidate_id"))
        for row in rows:
            if allowed and row['candidate_id'] not in allowed:
                continue
            if args.precision_suffix and not (row['precision_hint'] or '').endswith(args.precision_suffix):
                continue
            stats['coordinates_scanned'] += 1
            # “Well 3” in a hydrogeological paragraph is not automatically a
            # soil profile.  A soil/profile term must occur in this same local
            # coordinate evidence.
            if not SOIL_CONTEXT.search(row['context_text'] or ''):
                continue
            labels = local_labels(row['context_text'] or '', row['latitude'], row['longitude'])
            names = {value.casefold() for value, _start, _end in labels}
            if len(names) != 1:
                if len(names) > 1:
                    stats['ambiguous_labels'] += 1
                continue
            label, start, end = labels[0]
            alias = con.execute(
                "SELECT site_id FROM site_coordinate_candidate WHERE candidate_id=?", (row['candidate_id'],)
            ).fetchone()
            site_id = alias['site_id'] if alias else 'site:' + row['candidate_id']
            if not con.execute("SELECT 1 FROM site WHERE site_id=?", (site_id,)).fetchone():
                stats['missing_site'] += 1
                continue
            profile_id = 'profile:coordinate_first_label:' + ident(row['document_id'], site_id, label)
            evidence = json.dumps({
                "spatial_linkage": "coordinate_local_explicit_profile_label",
                "coordinate_candidate_id": row['candidate_id'],
                "label_distance_characters": min(abs(start), abs(end)),
            }, ensure_ascii=False) + "\n" + (row['context_text'] or '')
            audit.append({"profile_id": profile_id, "document_id": row['document_id'],
                          "coordinate_candidate_id": row['candidate_id'], "profile_label": label,
                          "latitude": row['latitude'], "longitude": row['longitude'],
                          "context_text": row['context_text']})
            if not args.dry_run:
                con.execute("""INSERT INTO profile(profile_id,site_id,profile_label,notes)
                    VALUES(?,?,?,?) ON CONFLICT(profile_id) DO NOTHING""",
                    (profile_id, site_id, label,
                     'Explicit profile/pit label within 180 characters of an author-reported coordinate.'))
                con.execute("""INSERT INTO profile_evidence
                    (profile_id,artifact_id,extraction_id,evidence_text,evidence_kind)
                    VALUES(?,?,?,?, 'profile_description')
                    ON CONFLICT(profile_id,artifact_id,evidence_kind)
                    DO UPDATE SET evidence_text=excluded.evidence_text""",
                    (profile_id, row['artifact_id'], row['extraction_id'], evidence))
            stats['staged_profiles'] += 1
        if not args.dry_run:
            con.commit()
    if args.output:
        fields = ['profile_id','document_id','coordinate_candidate_id','profile_label','latitude','longitude','context_text']
        with args.output.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
