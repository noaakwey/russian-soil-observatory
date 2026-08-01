#!/usr/bin/env python3
"""Find only explicit table-label -> coordinate-label links in multi-site papers.

An ordinary horizon (A, B, Bt) is deliberately not a spatial label.  A row is
reported only when its text contains a named profile/pit/site/plot/section and
the exact normalized named label occurs in evidence for exactly one validated
Russian coordinate from the same document.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


LABEL = re.compile(
    r"\b(?:profile|soil\s+pit|pit|site|plot|section|transect|"
    r"разрез|профил(?:ь)?|участ(?:ок|ке)?|точк[аи])\s*(?:no\.?|№|#)?\s*"
    r"([A-Za-zА-Яа-я]{1,4}[0-9]{0,4}|[0-9]{1,4}[A-Za-zА-Яа-я]{0,4})\b",
    re.I,
)

# A bare ``A`` or ``P-12`` is not spatial evidence by itself: it may be a
# horizon or a table footnote.  It becomes eligible only in the opt-in audit
# when the *same OCR table* contains a series of such labels and every label
# resolves to one named field/profile in coordinate prose from the same paper.
BARE_ROW_LABEL = re.compile(r"^\s*([A-Za-zА-Яа-я]{1,4}[0-9]{0,4}(?:-[A-Za-zА-Яа-я0-9]{1,8})?|[0-9]{1,4}[A-Za-zА-Яа-я]{0,4}(?:-[A-Za-zА-Яа-я0-9]{1,8})?)\s*$")
# Captions often enumerate pits as ``(a) 40X-12`` instead of repeating the
# word "pit" before every code.  A captured code must carry a digit.
CAPTION_CODE_LABEL = re.compile(r"\([A-Za-zА-Яа-я]\)\s*([A-Za-zА-Яа-я0-9-]*\d[A-Za-zА-Яа-я0-9-]*)\b")


def labels(text: str, min_length: int = 2) -> set[str]:
    return {m.group(1).casefold() for m in LABEL.finditer(text or "") if len(m.group(1)) >= min_length}


def bare_row_label(text: str | None) -> str | None:
    match = BARE_ROW_LABEL.match(text or "")
    return match.group(1).casefold() if match else None


def coordinate_labels(text: str, min_length: int = 2) -> set[str]:
    found = labels(text, min_length)
    found.update(m.group(1).casefold() for m in CAPTION_CODE_LABEL.finditer(text or ""))
    return found


COORDINATE_SQL = """
SELECT a.document_id, lc.candidate_id AS coordinate_candidate_id,
       lc.latitude, lc.longitude, lc.context_text AS coordinate_context
FROM location_candidate lc
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
JOIN extraction e ON e.extraction_id=lc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
WHERE lc.status='accepted' AND lv.country_code='RU' AND lv.result='inside'
"""

TABLE_SQL = """
SELECT t.candidate_id, t.artifact_id, t.row_index, t.column_index,
       t.property_id, t.property_header_raw, t.value_num, t.unit_raw,
       t.row_label_raw, t.horizon_label, t.depth_top_cm, t.depth_bottom_cm,
       d.document_id
FROM table_measurement_candidate t
JOIN source_artifact a ON a.artifact_id=t.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE t.status='unreviewed' AND t.unit_raw IS NOT NULL
ORDER BY t.candidate_id
"""


def main() -> None:
    p = argparse.ArgumentParser(); p.add_argument('--db', type=Path, required=True); p.add_argument('--output', type=Path)
    p.add_argument('--document-id', help='restrict the audit to one source document')
    p.add_argument('--allow-bare-table-labels', action='store_true',
                   help='audit only: permit a short row label after a same-table series check')
    a = p.parse_args(); candidates: dict[str, list[dict]] = defaultdict(list); table_labels: dict[str, set[str]] = {}
    rows: list[dict] = []
    with sqlite3.connect(a.db) as con:
        con.row_factory = sqlite3.Row
        coordinates_by_document: dict[str, list[dict]] = defaultdict(list)
        for coordinate in con.execute(COORDINATE_SQL):
            coordinates_by_document[coordinate["document_id"]].append(dict(coordinate))
        sql, params = TABLE_SQL, ()
        if a.document_id:
            sql = TABLE_SQL.replace("WHERE t.status='unreviewed'", "WHERE d.document_id=? AND t.status='unreviewed'")
            params = (a.document_id,)
        for row in con.execute(sql, params):
            rec = dict(row)
            if rec["document_id"] not in coordinates_by_document:
                continue
            labs = labels((rec['row_label_raw'] or '') + ' ' + (rec['horizon_label'] or ''))
            if a.allow_bare_table_labels:
                bare = bare_row_label(rec['row_label_raw'])
                if bare:
                    labs.add(bare)
            if not labs: continue
            table_labels[rec['candidate_id']] = labs
            rows.append(rec)
            for coordinate in coordinates_by_document[rec["document_id"]]:
                if labs & coordinate_labels(coordinate['coordinate_context'], 1 if a.allow_bare_table_labels else 2):
                    candidates[rec['candidate_id']].append({**rec, **coordinate})
    # A short label needs corroboration from a repeated table structure.  The
    # check is applied per artifact and document, so unrelated page fragments
    # cannot make a bare label look like a sampling-point identifier.
    bare_allowed: set[str] = set()
    if a.allow_bare_table_labels:
        by_table: dict[tuple[str, str], set[str]] = defaultdict(set)
        coord_labels: dict[tuple[str, str], set[str]] = defaultdict(set)
        for rec in rows:
            key = (rec['document_id'], rec['artifact_id'])
            bare = bare_row_label(rec['row_label_raw'])
            if bare:
                by_table[key].add(bare)
            for coordinate in coordinates_by_document[rec['document_id']]:
                coord_labels[key].update(coordinate_labels(coordinate['coordinate_context'], 1))
        for key, seen in by_table.items():
            matched = seen & coord_labels[key]
            if len(matched) >= 2:
                bare_allowed.update(
                    rec['candidate_id'] for rec in rows
                    if (rec['document_id'], rec['artifact_id']) == key
                    and bare_row_label(rec['row_label_raw']) in matched
                )
    stats: Counter[str] = Counter(); out = []
    for cid, matches in candidates.items():
        rec_labs = table_labels[cid]
        if a.allow_bare_table_labels and cid not in bare_allowed:
            explicit = labels((matches[0]['row_label_raw'] or '') + ' ' + (matches[0]['horizon_label'] or ''))
            if not explicit:
                stats['bare_label_without_same_table_series'] += 1
                continue
        coordinate_ids = {m['coordinate_candidate_id'] for m in matches}
        if len(coordinate_ids) != 1:
            stats['ambiguous_coordinate_label'] += 1; continue
        r = matches[0]; common = sorted(table_labels[cid] & coordinate_labels(r['coordinate_context'], 1 if a.allow_bare_table_labels else 2))
        stats['unique_explicit_label_link'] += 1
        out.append({**{k: r[k] for k in ('candidate_id','document_id','artifact_id','row_index','column_index','property_id','property_header_raw','value_num','unit_raw','row_label_raw','horizon_label','depth_top_cm','depth_bottom_cm','coordinate_candidate_id','latitude','longitude','coordinate_context')}, 'matching_labels': ';'.join(common)})
    if a.output:
        fields = list(out[0]) if out else ['candidate_id']
        with a.output.open('w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(out)
    print(json.dumps({'table_candidates_with_explicit_spatial_label': len(table_labels), 'results': len(out), 'stats': dict(stats)}, ensure_ascii=False))


if __name__ == '__main__': main()
