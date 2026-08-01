#!/usr/bin/env python3
"""Stage soil-classification and land-use descriptions from article prose."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

from ingest_pochvovedenie_text import SAMPLE, ctx

SOIL = re.compile(
    r'\b(?:Chernozem(?:ic)?|Phaeozem|Kastanozem|Retisol|Podzol(?:ic)?|'
    r'Cambisol|Fluvisol|Gleysol|Leptosol|Solonetz|Solonchak|Arenosol|Histosol|Cryosol|'
    r'черноз[её]м(?:н\w*)?|дерново[- ]подзолист\w*|подзол\w*|каштанов\w*|'
    r'солонц\w*|солончак\w*|аллювиальн\w*|сероз[её]м\w*|буроз[её]м\w*|'
    r'торфян\w*|гле[её]в\w*|мерзлотн\w*)\b', re.I)
LAND_USE = re.compile(
    r'\b(?:arable land|cropland|pasture|grassland|forest(?:ed)?|fallow|orchard|'
    r'пашн[яи]|сельскохозяйственн\w* угодь\w*|пастбищ\w*|сенокос\w*|лесн\w*|залеж\w*|сад\w*)\b', re.I)
WRB = {'chernozem', 'chernozemic', 'phaeozem', 'kastanozem', 'retisol', 'podzol', 'podzolic',
       'cambisol', 'fluvisol', 'gleysol', 'leptosol', 'solonetz', 'solonchak', 'arenosol',
       'histosol', 'cryosol'}


def system(term: str) -> str:
    return 'WRB' if term.casefold() in WRB else 'Russian/national term (unverified)'


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--text-dir', type=Path, required=True)
    p.add_argument('--corpus', choices=('springer', 'pochvovedenie'), required=True)
    p.add_argument('--db', type=Path, required=True)
    p.add_argument('--commit-every', type=int, default=50)
    args = p.parse_args()
    stats = {'texts': 0, 'soil_descriptions': 0, 'land_use_descriptions': 0, 'missing_document': 0}
    with sqlite3.connect(args.db) as con:
        con.execute('PRAGMA foreign_keys=ON')
        for file_no, path in enumerate(sorted(args.text_dir.glob('*.txt')), start=1):
            doc_id = f'{args.corpus}:{path.stem}'
            row = con.execute(
                '''SELECT e.extraction_id FROM extraction e JOIN source_artifact a ON a.artifact_id=e.artifact_id
                   WHERE a.document_id=? AND a.artifact_type='text' ORDER BY e.extraction_id LIMIT 1''', (doc_id,)
            ).fetchone()
            if not row:
                stats['missing_document'] += 1
                continue
            extraction_id = row[0]
            text = path.read_text(encoding='utf-8', errors='replace')
            n = 0
            for m in SOIL.finditer(text):
                window = ctx(text, m.start(), m.end())
                label = SAMPLE.search(window)
                con.execute(
                    '''INSERT INTO profile_candidate
                       (candidate_id,extraction_id,profile_label,soil_classification_raw,classification_system_candidate,land_use_raw,context_text,status)
                       VALUES(?,?,?,?,?,?,?,'unreviewed')
                       ON CONFLICT(candidate_id) DO UPDATE SET
                         profile_label=excluded.profile_label,
                         soil_classification_raw=excluded.soil_classification_raw,
                         classification_system_candidate=excluded.classification_system_candidate,
                         land_use_raw=excluded.land_use_raw,
                         context_text=excluded.context_text,
                         status=CASE WHEN profile_candidate.status='accepted' THEN 'accepted' ELSE 'unreviewed' END''',
                    (f'{extraction_id}:p:soil:{n}', extraction_id, label.group(1) if label else None,
                     m.group(0), system(m.group(0)), None, window),
                )
                n += 1; stats['soil_descriptions'] += 1
            for m in LAND_USE.finditer(text):
                window = ctx(text, m.start(), m.end())
                label = SAMPLE.search(window)
                con.execute(
                    '''INSERT INTO profile_candidate
                       (candidate_id,extraction_id,profile_label,soil_classification_raw,classification_system_candidate,land_use_raw,context_text,status)
                       VALUES(?,?,?,?,?,?,?,'unreviewed')
                       ON CONFLICT(candidate_id) DO UPDATE SET
                         profile_label=excluded.profile_label,
                         soil_classification_raw=excluded.soil_classification_raw,
                         classification_system_candidate=excluded.classification_system_candidate,
                         land_use_raw=excluded.land_use_raw,
                         context_text=excluded.context_text,
                         status=CASE WHEN profile_candidate.status='accepted' THEN 'accepted' ELSE 'unreviewed' END''',
                    (f'{extraction_id}:p:land:{n}', extraction_id, label.group(1) if label else None,
                     None, None, m.group(0), window),
                )
                n += 1; stats['land_use_descriptions'] += 1
            stats['texts'] += 1
            if file_no % args.commit_every == 0:
                con.commit()
        con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
