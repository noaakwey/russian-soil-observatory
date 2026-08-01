#!/usr/bin/env python3
"""Extract author soil type/formula from a profile's *local* coordinate evidence.

This companion to ``stage_coordinate_first_labeled_profiles`` never searches
the complete article.  A value can therefore not leak from a neighbouring
profile merely because labels such as “Point 2” recur elsewhere in the paper.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import sqlite3
from pathlib import Path

from extract_author_profile_metadata import FORMULA, clean, ensure_schema, excerpt

RUSSIAN_TYPE = re.compile(
    r"(?:Почва|Почвы)\s*[:–—-]?\s*(?P<value>[А-Яа-яЁё][A-Za-zА-Яа-яЁё0-9(),/ .–—-]{2,300}?)"
    r"(?=\s+(?:с\s+формул\w*|формул\w*\s+(?:морфологическ\w+\s+)?строени\w*\s+профил\w*)|\.)",
    re.I,
)
ENGLISH_TYPE = re.compile(
    r"(?:\bthe\s+)?\bsoil\s+(?:was|is|is represented by|is classified as)?\s*[:–—-]?\s*"
    r"(?P<value>[A-Za-z][A-Za-z0-9(),/ .–—-]{2,260}?)"
    r"(?=\s+(?:with\s+(?:the\s+)?(?:soil\s+)?profile|the\s+following\s+horizons|profile\s+(?:was|is|consists))|\.)",
    re.I,
)
CUE = re.compile(
    r"(?:формул\w*.{0,50}профил\w*|морфологическ\w*.{0,50}профил\w*|"
    r"soil\s+profile|profile\s+(?:formula|sequence|consists)|horizon\s+sequence)", re.I)
# Russian papers often print a compact author formula without depth intervals:
# ``формула профиля AHca,dc–ТСНca,rr–Q1–Q2mc``.  It is extracted only with
# that literal cue in the same coordinate-local profile evidence; it is never
# reconstructed from a table of horizons.
SHORT_CUED_FORMULA = re.compile(
    r"формул\w*\s+(?:морфологическ\w+\s+строени\w*\s+)?(?:профил\w*\s*)?[:–—-]?\s*"
    r"(?P<formula>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9,~+()]*"
    r"(?:\s*-\s*\d+\s*[A-Za-zА-Яа-яЁё0-9,~+()]*)?\s*"
    r"(?:[-–—]\s*[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9,~+()]*"
    r"(?:\s*-\s*\d+\s*[A-Za-zА-Яа-яЁё0-9,~+()]*)?\s*){1,11})",
    re.I,
)
# Wider wording (for example, “the soil profile consists of …”) is parsed in
# two bounded stages below.  A single article-wide expression here can cause
# pathological backtracking on long OCR text.
PROFILE_SEQUENCE_CUE = re.compile(
    r"(?:"
    r"(?:the\s+)?soil\s+profile\s+(?:consists\s+of|had|has|includes|was)(?:\s+the\s+following\s+horizons?)?"
    r"|(?:soil\s+)?profile\s+(?:formula|sequence)"
    r"|(?:the\s+)?(?:following\s+)?horizon\s+sequence"
    r"|(?:морфологическ\w+\s+)?профил\w*\s+(?:почв\w*\s+)?(?:состо\w*|включа\w*|име\w*)"
    r")\s*[:–—-]?\s*", re.I)
HORIZON_SEQUENCE = re.compile(
    r"(?P<formula>[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9,~+()]{0,20}"
    r"(?:\s*[-–—]\s*[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9,~+()]{0,20}){2,11})")
TYPE_SIGNAL = re.compile(
    r"(?:черноз\w*|подбур\w*|подзол\w*|гле\w*|палевая|петроз\w*|пелоз\w*|литоз\w*|"
    r"псаммоз\w*|криоз\w*|карбопетроз\w*|"
    r"солон\w*|каштан\w*|сероз\w*|торф\w*|аллювиальн\w*|дернов\w*|"
    r"\b(?:Cryosol|Podzol|Podbur|Phaeozem|Chernozem|Leptosol|Fluvisol|Cambisol|"
    r"Gleysol|Stagnosol|Histosol|Solonetz|Solonchak|Arenosol)\b)", re.I)
BAD_TYPE = re.compile(r"\b(?:покрыт\w*|имеет|представлен\w*|располож\w*|заложен\w*|наход\w*|formed|covered|located)\b", re.I)
DEFINED_RUSSIAN_TYPE = re.compile(
    r"(?:Почва|почва)\s+(?:определен\w*|отнесен\w*)\s+(?:нами\s+)?как\s+"
    r"(?P<value>[А-Яа-яЁё][A-Za-zА-Яа-яЁё0-9(),/ .–—-]{2,260}?)(?=\.)", re.I)
FIELD_LABEL = re.compile(
    r"(?:\b(?:разрез|pit|profile)\s*(?:No\.?|№)?\s*)"
    r"(?P<label>[A-Za-zА-Яа-я]{0,8}-?\d+[A-Za-zА-Яа-я]?(?:[-–][A-Za-zА-Яа-я0-9]+)*)", re.I)
# A common English construction puts a literal author type immediately after
# the field identifier: ``Pit 28 characterizes a podzolized podbur``.  This
# is narrower than general prose: it requires the exact current pit label and
# stops before an explanatory clause or sentence boundary.
PIT_CHARACTERIZES_TYPE = re.compile(
    r"\b(?:pit|profile)\s*(?:No\.?\s*)?(?P<label>[A-Za-zА-Яа-я]{0,8}-?\d+[A-Za-zА-Яа-я]?(?:[-–][A-Za-zА-Яа-я0-9]+)*)"
    r"\s+(?:characteri[sz]es|represents)\s+(?P<value>(?:an?\s+)?[A-Za-z][A-Za-z0-9(),/ .–—-]{2,180}?)"
    r"(?=\s*(?:\(|,\s*(?:which|with|under|on|at)\b|(?:seen|on|under|with|at|in)\b|\.))", re.I)


def statement_id(*parts: str) -> str:
    return "author-stmt:" + hashlib.sha1("\x1f".join(parts).encode()).hexdigest()[:24]


def local_text(evidence: str) -> str:
    # Coordinate-first evidence begins with a JSON provenance header.
    return clean(evidence.split("\n", 1)[1] if "\n" in evidence else evidence)


def clean_type(value: str) -> str:
    """Remove a truncated figure-reference tail, not author soil wording."""
    return re.sub(r"\s*\((?:рис|fig)\.?$", "", value, flags=re.I).strip()


def clean_formula(value: str) -> str:
    value = clean(value)
    # PDF line wrapping may split a horizon index (``ТСН2- 7 ca``).  Joining
    # that typography restores the literally printed formula; no horizon is
    # invented or inferred.
    value = re.sub(r"(?<=[A-Za-zА-Яа-яЁё0-9])-\s+(?=\d)", "-", value)
    return re.sub(r"(?<=\d)\s+(?=[A-Za-zА-Яа-яЁё])", "", value)


def iter_cued_short_formulas(text: str):
    """Yield literal compact formulae and offsets without whole-text backtracking."""
    for match in SHORT_CUED_FORMULA.finditer(text):
        yield match.group("formula"), match.start("formula"), match.end("formula")
    for cue in PROFILE_SEQUENCE_CUE.finditer(text):
        match = HORIZON_SEQUENCE.match(text, cue.end())
        if match:
            yield match.group("formula"), match.start("formula"), match.end("formula")


def belongs_to_profile(text: str, profile_label: str, position: int) -> bool:
    """A field belongs only to the last explicit profile label before it.

    Coordinate snippets may contain a sequence of profiles.  Locality alone is
    insufficient: formula/type fields after ``Разрез B`` must never be copied
    to the preceding ``Разрез A``.
    """
    labels = [m.group("label") for m in FIELD_LABEL.finditer(text) if m.start() <= position]
    return bool(labels) and labels[-1].casefold() == profile_label.casefold()


def candidates(text: str, profile_label: str) -> list[tuple[str, str, int, int]]:
    result: list[tuple[str, str, int, int]] = []
    for pattern in (RUSSIAN_TYPE, ENGLISH_TYPE):
        for match in pattern.finditer(text):
            raw = clean_type(clean(match.group("value").strip(" ,;:")))
            # A type must be an explicit author phrase, not a full sentence.
            referred = re.findall(r"(?:разреза?|pit)\s*(?:No\.?|№)?\s*(\d+)", raw, re.I)
            same_label = not referred or not profile_label.isdigit() or all(value == profile_label for value in referred)
            if (len(raw) <= 260 and same_label and TYPE_SIGNAL.search(raw)
                    and not BAD_TYPE.search(raw) and belongs_to_profile(text, profile_label, match.start("value"))):
                result.append(("author_soil_type_raw", raw, match.start("value"), match.end("value")))
    for match in DEFINED_RUSSIAN_TYPE.finditer(text):
        raw = clean_type(clean(match.group("value").strip(" ,;:")))
        if (TYPE_SIGNAL.search(raw) and not BAD_TYPE.search(raw)
                and belongs_to_profile(text, profile_label, match.start("value"))):
            result.append(("author_soil_type_raw", raw, match.start("value"), match.end("value")))
    for match in PIT_CHARACTERIZES_TYPE.finditer(text):
        raw = clean_type(clean(match.group("value").strip(" ,;:")))
        if (match.group("label").casefold() == profile_label.casefold()
                and TYPE_SIGNAL.search(raw) and not BAD_TYPE.search(raw)
                and belongs_to_profile(text, profile_label, match.start("value"))):
            result.append(("author_soil_type_raw", raw, match.start("value"), match.end("value")))
    # In map captions the author frequently writes “разрез X, coordinate,
    # [literal type]” without the word “Почва”.  The label, coordinate and
    # type must all occur in this one profile evidence snippet.
    label = re.escape(profile_label)
    if label:
        after_coordinate = re.compile(
            r"(?:разрез|pit|profile)\s*(?:No\.?|№)?\s*" + label +
            r"[\s\S]{0,220}?\d{1,2}[°º][\s\S]{0,40}?\b[NSСЮ]\b"
            r"[\s\S]{0,100}?\d{1,3}[°º][\s\S]{0,40}?\b[EWВЗ]\b\s*[,;:]\s*"
            r"(?P<value>[А-Яа-яЁё][A-Za-zА-Яа-яЁё0-9(),/ .–—-]{2,240}?)(?=[;.])", re.I)
        for match in after_coordinate.finditer(text):
            raw = clean_type(clean(match.group("value").strip(" ,;:")))
            if (TYPE_SIGNAL.search(raw) and not BAD_TYPE.search(raw)
                    and belongs_to_profile(text, profile_label, match.start("value"))):
                result.append(("author_soil_type_raw", raw, match.start("value"), match.end("value")))
    for match in FORMULA.finditer(text):
        before = text[max(0, match.start("formula") - 240):match.start("formula")]
        if CUE.search(before) and belongs_to_profile(text, profile_label, match.start("formula")):
            raw = clean_formula(match.group("formula"))
            result.append(("author_profile_formula_raw", raw, match.start("formula"), match.end("formula")))
    for formula, start, end in iter_cued_short_formulas(text):
        if belongs_to_profile(text, profile_label, start):
            raw = clean_formula(formula.strip(" ,;:."))
            result.append(("author_profile_formula_raw", raw, start, end))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--profile-id", action="append", default=[],
                        help="Restrict extraction to explicitly audited profiles.")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = {"profiles_scanned": 0, "type_statements": 0, "formula_statements": 0}
    audit: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        if not args.dry_run:
            ensure_schema(con)
        rows = con.execute("""
            SELECT p.profile_id,p.profile_label,pe.artifact_id,pe.extraction_id,pe.evidence_text
            FROM profile p JOIN profile_evidence pe ON pe.profile_id=p.profile_id
            WHERE (p.profile_id LIKE 'profile:coordinate_first_label:%'
                   OR p.profile_id LIKE 'profile:explicit_pit:%'
                   OR p.notes LIKE 'Direct profile-label-to-coordinate%')
              AND pe.evidence_kind='profile_description'
        """).fetchall()
        allowed = set(args.profile_id)
        for row in rows:
            if allowed and row['profile_id'] not in allowed:
                continue
            text = local_text(row['evidence_text'])
            stats['profiles_scanned'] += 1
            # Preserve every literal author statement.  The convenience field
            # holds the nearest one rather than replacing an earlier value.
            best: dict[str, tuple[str, int, int]] = {}
            for field, raw, start, end in candidates(text, row['profile_label'] or ''):
                current = best.get(field)
                if current is None or abs(start) < abs(current[1]):
                    best[field] = (raw, start, end)
                audit.append({"profile_id": row['profile_id'], "profile_label": row['profile_label'] or '',
                              "field_name": field, "raw_value": raw,
                              "evidence_text": excerpt(text, start, end)})
                if not args.dry_run:
                    con.execute("""INSERT INTO profile_author_statement
                        (statement_id,profile_id,field_name,raw_value,artifact_id,extraction_id,evidence_text,extractor)
                        VALUES(?,?,?,?,?,?,?,?)
                        ON CONFLICT(profile_id,field_name,raw_value,artifact_id) DO NOTHING""",
                        (statement_id(row['profile_id'], field, raw, row['artifact_id']), row['profile_id'], field,
                         raw, row['artifact_id'], row['extraction_id'], excerpt(text, start, end),
                         'extract_coordinate_first_profile_metadata:v2'))
                stats['type_statements' if field == 'author_soil_type_raw' else 'formula_statements'] += 1
            if not args.dry_run:
                for field, (raw, _start, _end) in best.items():
                    con.execute(f"UPDATE profile SET {field}=COALESCE({field},?) WHERE profile_id=?", (raw, row['profile_id']))
        if not args.dry_run:
            con.commit()
    if args.output:
        fields = ['profile_id', 'profile_label', 'field_name', 'raw_value', 'evidence_text']
        with args.output.open('w', encoding='utf-8', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
