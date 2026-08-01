#!/usr/bin/env python3
"""Extract literal author soil types and morphological profile formulae.

This is intentionally narrow.  It writes a value only when it occurs in the
same manuscript, close to an already explicit, coordinate-linked pit/profile.
Neither a taxonomy is inferred nor is a missing formula reconstructed from
horizon rows.  Every stored value has an evidence excerpt and source artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path


TYPE_TERMS = re.compile(
    r"(?:\b(?:Chernozem(?:ic)?|Phaeozem|Kastanozem|Retisol|Podzol(?:ic)?|Cambisol|"
    r"Fluvisol|Gleysol|Leptosol|Solonetz|Solonchak|Arenosol|Histosol|Cryosol)\b|"
    r"черноз[её]м\w*|дерново[- ]подзолист\w*|подзол\w*|каштанов\w*|"
    r"солонц\w*|солончак\w*|аллювиальн\w*|сероз[её]м\w*|буроз[её]м\w*|"
    r"торфян\w*|гле[её]в\w*|мерзлотн\w*|петроз[её]м\w*|пелоз[её]м\w*)", re.I)

LABEL_PREFIX = r"(?:pit|soil\s+pit|point|plot|site|sampling\s+point|borehole|core|разрез|точка|площадка|участок|скважина|керн|тп)"
FORMULA = re.compile(
    r"(?P<formula>(?:\[[A-Za-zА-Яа-яЁё0-9~+\-]+\]|[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9~+\-]{0,14})"
    r"\s*\(\s*\d{1,3}(?:\s*\([^)]{1,12}\))?\s*(?:-|–|—)\s*\d{1,3}"
    r"(?:\s*\([^)]{1,12}\))?\s*(?:cm|см)\s*\)"
    r"(?:\s*(?:-|–|—)\s*(?:\[[A-Za-zА-Яа-яЁё0-9~+\-]+\]|[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9~+\-]{0,14})"
    r"\s*\(\s*\d{1,3}(?:\s*\([^)]{1,12}\))?\s*(?:-|–|—)\s*\d{1,3}"
    r"(?:\s*\([^)]{1,12}\))?\s*(?:cm|см)\s*\)){2,12})",
    re.I,
)


def clean(text: str) -> str:
    """Join PDF line-wraps but retain the literal words/numbers of a statement."""
    text = text.replace("\u00ad", "")
    text = re.sub(r"(?<=\w)-\s*\n\s*(?=\w)", "", text)
    return re.sub(r"\s+", " ", text).strip()


def label_pattern(label: str) -> re.Pattern[str]:
    # Cyrillic Р/С/А and Latin P/C/A are often mixed by PDF extraction.
    swaps = {"P": "PРр", "Р": "PРр", "C": "CСс", "С": "CСс", "A": "AАа", "А": "AАа"}
    parts = []
    for char in label:
        parts.append("[" + swaps[char] + "]" if char in swaps else re.escape(char))
    return re.compile(r"\b" + "".join(parts) + r"(?=[^A-Za-zА-Яа-яЁё0-9]|$)", re.I)


def excerpt(text: str, start: int, end: int, width: int = 300) -> str:
    return text[max(0, start - width): min(len(text), end + width)].strip()


def type_candidates(window: str, label_re: re.Pattern[str]) -> list[tuple[str, int, int]]:
    out: list[tuple[str, int, int]] = []
    # Author type placed before the labelled pit: “... soil (pit P-2)”.
    before = re.compile(
        r"(?P<type>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9(),/ .–—-]{2,180}?(?:soil|почва|почвы))"
        r"\s*\(\s*" + LABEL_PREFIX + r"\s*(?:No\.?|№)?\s*" + label_re.pattern[2:] + r"\s*\)", re.I)
    # Author type printed after a coordinate-labelled pit, convention common in
    # Russian papers: “разрез X, ... координаты, петрозем ... (WRB name)”.
    after = re.compile(
        LABEL_PREFIX + r"\s*(?:No\.?|№)?\s*" + label_re.pattern[2:] +
        r"(?P<prefix>.{0,260}?)(?:[,;:]\s*)(?P<type>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9(),/ .–—-]{2,200})(?=[;.])", re.I)
    for m in before.finditer(window):
        val = clean(m.group('type').strip(' ,;:'))
        if TYPE_TERMS.search(val):
            out.append((val, m.start('type'), m.end('type')))
    for m in after.finditer(window):
        val = clean(m.group('type').strip(' ,;:'))
        # Do not turn a prose clause into a type.  A recognised literal soil
        # name is required, or an author explicitly writes “soil/почва”.
        has_coordinate = bool(re.search(r"(?:координат|latitude|longitude|\d{1,2}[°º]|\b[NS]\b.{0,80}\b[EW]\b)", m.group('prefix'), re.I))
        if has_coordinate and TYPE_TERMS.search(val):
            if not re.search(r"\b(?:located|laid|располож|заложен|наход)\b", val, re.I):
                out.append((val, m.start('type'), m.end('type')))
    return out


def ident(*parts: str) -> str:
    return "author-stmt:" + hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:24]


def ensure_schema(con: sqlite3.Connection) -> None:
    columns = {r[1] for r in con.execute("PRAGMA table_info(profile)")}
    for col in ("author_soil_type_raw", "author_profile_formula_raw"):
        if col not in columns:
            con.execute(f"ALTER TABLE profile ADD COLUMN {col} TEXT")
    con.execute("""CREATE TABLE IF NOT EXISTS profile_author_statement (
        statement_id TEXT PRIMARY KEY,
        profile_id TEXT NOT NULL REFERENCES profile(profile_id),
        field_name TEXT NOT NULL CHECK (field_name IN ('author_soil_type_raw','author_profile_formula_raw')),
        raw_value TEXT NOT NULL,
        artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
        extraction_id TEXT REFERENCES extraction(extraction_id),
        evidence_text TEXT NOT NULL,
        extractor TEXT NOT NULL,
        review_status TEXT NOT NULL DEFAULT 'unreviewed'
          CHECK (review_status IN ('unreviewed','accepted','flagged')),
        UNIQUE (profile_id, field_name, raw_value, artifact_id)
    )""")
    statement_columns = {r[1] for r in con.execute("PRAGMA table_info(profile_author_statement)")}
    if "review_status" not in statement_columns:
        con.execute("ALTER TABLE profile_author_statement ADD COLUMN review_status TEXT NOT NULL DEFAULT 'unreviewed'")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    stats = {"profiles_scanned": 0, "missing_text": 0, "author_type_statements": 0,
             "author_formula_statements": 0, "profiles_with_type": 0, "profiles_with_formula": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        rows = con.execute("""
            SELECT p.profile_id,p.profile_label,pe.artifact_id,pe.extraction_id,a.source_path
            FROM profile p JOIN profile_evidence pe ON pe.profile_id=p.profile_id
            JOIN source_artifact a ON a.artifact_id=pe.artifact_id
            WHERE p.profile_id LIKE 'profile:explicit_pit:%'
              AND a.artifact_type='text'
        """).fetchall()
        for row in rows:
            try:
                text = clean(Path(row['source_path']).read_text(encoding='utf-8', errors='replace'))
            except OSError:
                stats['missing_text'] += 1
                continue
            label_re = label_pattern(row['profile_label'])
            matches = list(label_re.finditer(text))
            if not matches:
                continue
            stats['profiles_scanned'] += 1
            # Labels such as P-1 recur in figure legends and running headers.
            # Prefer the occurrence with a coordinate marker in its immediate
            # context; only then use the first occurrence as a fallback.
            def anchor_score(m: re.Match[str]) -> tuple[int, int]:
                nearby = text[max(0, m.start()-120):m.end()+360]
                marker = bool(re.search(r"(?:координат|latitude|longitude|\d{1,2}[°º]|\b[NS]\b.{0,80}\b[EW]\b)", nearby, re.I))
                return (int(marker), -m.start())
            # The coordinate-linked phrase determines which same-label mention
            # is relevant; all formula/type search stays within 1.6 k chars.
            anchor = max(matches, key=anchor_score)
            window_start, window_end = max(0, anchor.start()-450), min(len(text), anchor.end()+1600)
            window = text[window_start:window_end]
            found_type = found_formula = False
            candidates: list[tuple[str, str, int, int]] = []
            for raw, start, end in type_candidates(window, label_re):
                candidates.append(('author_soil_type_raw', raw, window_start+start, window_start+end))
            for m in FORMULA.finditer(window):
                raw = clean(m.group('formula'))
                before_formula = window[max(0, m.start('formula')-280):m.start('formula')]
                cue = re.search(
                    r"(?:формул\w*.{0,45}профил\w*|морфологическ\w*.{0,45}профил\w*|"
                    r"soil\s+profile|profile\s+(?:formula|sequence|consists)|horizon\s+sequence|"
                    r"профил\w*.{0,60}(?:горизонт\w*|состо\w*))", before_formula, re.I)
                if cue:
                    candidates.append(('author_profile_formula_raw', raw, window_start+m.start('formula'), window_start+m.end('formula')))
            # Keep every distinct literal statement.  The closest statement of
            # each kind is surfaced on profile without erasing existing values.
            best: dict[str, tuple[str, int, int]] = {}
            for field, raw, start, end in candidates:
                if raw in {v[0] for v in best.values()} and field in best:
                    continue
                current = best.get(field)
                distance = abs(start-anchor.start())
                if current is None or distance < abs(current[1]-anchor.start()):
                    best[field] = (raw, start, end)
                if not args.dry_run:
                    con.execute("""INSERT INTO profile_author_statement
                        (statement_id,profile_id,field_name,raw_value,artifact_id,extraction_id,evidence_text,extractor)
                        VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(profile_id,field_name,raw_value,artifact_id) DO NOTHING""",
                        (ident(row['profile_id'], field, raw, row['artifact_id']), row['profile_id'], field, raw,
                         row['artifact_id'], row['extraction_id'], excerpt(text, start, end),
                         'extract_author_profile_metadata:v1'))
                if field == 'author_soil_type_raw': stats['author_type_statements'] += 1; found_type = True
                else: stats['author_formula_statements'] += 1; found_formula = True
            if not args.dry_run:
                for field, (raw, _start, _end) in best.items():
                    con.execute(f"UPDATE profile SET {field}=COALESCE({field},?) WHERE profile_id=?", (raw, row['profile_id']))
            stats['profiles_with_type'] += int(found_type)
            stats['profiles_with_formula'] += int(found_formula)
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
