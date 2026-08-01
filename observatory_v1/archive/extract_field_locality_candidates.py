#!/usr/bin/env python3
"""Discover literal field-locality mentions without assigning coordinates.

Administrative districts alone cannot recover every study location.  This
stage records nearby named villages, stations, lakes, quarries and reserves,
but only when the same short fragment contains a study/soil/sampling marker.
It intentionally does not geocode or promote anything.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

from audit_profile_context_coordinate import coords


EN_LOCALITY = re.compile(
    r"\b(?:near|nearby|at|in|within|around|vicinity\s+of|west\s+of|east\s+of|north\s+of|south\s+of)\s+"
    r"(?:the\s+)?(?P<kind>village|settlement|town|city|station|lake|river|quarry|reserve|"
    r"national\s+park|experimental\s+station|field\s+station)\s+(?:of\s+)?"
    r"(?P<name>[A-Z][A-Za-z'’-]{2,}(?:\s+[A-Z][A-Za-z'’-]{2,}){0,3})\b",
)
RU_LOCALITY = re.compile(
    r"\b(?P<kind>села|деревни|пос[её]лка|станции|ст\.|озера|реки|карьера|заповедника|"
    r"национального\s+парка|опытной\s+станции|полигона)\s+"
    r"(?P<name>[А-ЯЁ][А-Яа-яЁё'’.-]{2,}(?:\s+[А-ЯЁ][А-Яа-яЁё'’.-]{2,}){0,3})\b"
)
DIRECT_FIELD_ACTION = re.compile(
    r"(?:\b(?:stud(?:y|ies)\s+(?:was|were)\s+(?:conducted|carried\s+out)|"
    r"research\s+was\s+(?:conducted|carried\s+out)|samples?\s+(?:were\s+)?(?:collected|taken)|"
    r"soil\s+samples?\s+(?:were\s+)?(?:collected|taken)|field\s+(?:work|study)|"
    r"(?:plot|site|station)\s+(?:was|were)\s+(?:located|laid|established))\b|"
    r"(?:исследования\s+(?:проводил|выполнен|осуществля)|полевые\s+исследован|"
    r"(?:образц|проб)\w*\s+(?:были\s+)?(?:отобран|взят)|отбор\s+(?:образц|проб)|"
    r"(?:участок|стационар|площадк)\w*\s+(?:расположен|заложен)|"
    r"объект\w*\s+исследован|ключев\w*\s+участок|"
    r"(?:исследован|отбор|разрез|почв)\w*[^.]{0,100}(?:в\s+окрестност|вблизи|рядом\s+с)))",
    re.I,
)
AFFILIATION_OR_REFERENCE = re.compile(
    r"(?:\b(?:e-?mail|received|university|institute|department|street|ul\.)\b|"
    r"(?:электронн\w*\s+почт|поступил\w*\s+в\s+редакц|университет|институт|кафедр|ул\.?\s*[А-ЯA-Z]))",
    re.I,
)
BIBLIOGRAPHY = re.compile(r"(?:^|\n)\s*(?:REFERENCES|ЛИТЕРАТУРА|СПИСОК\s+ЛИТЕРАТУРЫ)\s*(?:$|\n)", re.I)

# These are OCR/header words which match the English capitalised-name pattern,
# not toponyms.  Keep this deliberately short: an unfamiliar real locality is
# safer in the review queue than silently discarded.
NOT_A_TOPONYM = {"the", "samples", "sample", "chemical", "properties", "methods", "materials"}
FOREIGN_CONTEXT = re.compile(
    r"\b(?:Czech\s+Republic|Vietnam|Iran|Poland|Norway|Spitsbergen|China|Japan|Mongolia|Kazakhstan|Ukraine|"
    r"Вьетнам\w*|Чех\w*|Иран\w*|Польш\w*|Норвег\w*|Шпицберген\w*|Кита\w*|Япон\w*|Монгол\w*|Казахстан\w*|Украин\w*)\b",
    re.I,
)
BIBLIOGRAPHY_ITEM = re.compile(r"(?:^|\s)\d+\.\s+[^\n]{0,130}(?:\b(?:19|20)\d{2}\b|\bpp\.)", re.I)


def level(kind: str) -> str:
    return "settlement" if re.search(r"village|settlement|town|city|station|села|деревни|пос[её]лка|станции", kind, re.I) else "other"


def context(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - 380): min(len(text), end + 380)]).strip()


def is_english_toponym(name: str) -> bool:
    """Reject known OCR/header artefacts while retaining uncommon place names."""
    words = re.findall(r"[A-Za-z]+", name.casefold())
    return bool(words) and not any(word in NOT_A_TOPONYM for word in words)


def discovered(text: str):
    bibliography = BIBLIOGRAPHY.search(text)
    bibliography_start = bibliography.start() if bibliography else len(text)
    for pattern in (EN_LOCALITY, RU_LOCALITY):
        for match in pattern.finditer(text):
            if match.start() >= bibliography_start:
                continue
            # Two-column PDF extraction can split ``Yekaterin-burg`` and
            # insert another column between its parts.  A prefix is not a
            # locality; leave it out rather than inventing a place name.
            if match.end() < len(text) and text[match.end()] in "-‐‑\u00ad":
                continue
            evidence = context(text, match.start(), match.end())
            if not DIRECT_FIELD_ACTION.search(evidence) or AFFILIATION_OR_REFERENCE.search(evidence):
                continue
            # A printed coordinate belongs in the direct-coordinate pipeline,
            # where it receives a stronger country and profile-context audit.
            if (list(coords(evidence)) or FOREIGN_CONTEXT.search(evidence)
                    or len(BIBLIOGRAPHY_ITEM.findall(evidence)) >= 2):
                continue
            kind = re.sub(r"\s+", " ", match.group("kind")).strip()
            name = re.sub(r"\s+", " ", match.group("name")).strip(" ,.;:")
            if pattern is EN_LOCALITY and not is_english_toponym(name):
                continue
            # Keeping the locality kind makes an eventual Nominatim query less
            # ambiguous than a bare, often duplicated, toponym.
            locality_level = level(kind)
            if locality_level == "settlement":
                yield f"{kind} {name}", locality_level, evidence


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = {"artifacts_scanned": 0, "missing_text": 0, "candidates": 0, "settlement": 0, "other": 0}
    audit: list[dict[str, str]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT a.artifact_id,a.source_path,e.extraction_id,d.document_id
            FROM source_artifact a JOIN extraction e ON e.artifact_id=a.artifact_id
            JOIN document d ON d.document_id=a.document_id
            WHERE a.artifact_type='text' ORDER BY d.document_id,a.artifact_id,e.extraction_id
        """).fetchall()
        for row in rows:
            try:
                text = Path(row["source_path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                stats["missing_text"] += 1
                continue
            stats["artifacts_scanned"] += 1
            seen: set[tuple[str, str]] = set()
            for index, (place, admin_level, evidence) in enumerate(discovered(text)):
                key = (place.casefold(), evidence)
                if key in seen:
                    continue
                seen.add(key)
                record = {"candidate_id": f"{row['extraction_id']}:field_locality:{index}",
                          "extraction_id": row["extraction_id"], "document_id": row["document_id"],
                          "place_text": place, "administrative_level": admin_level,
                          "context_text": evidence}
                audit.append(record)
                stats["candidates"] += 1; stats[admin_level] += 1
                if not args.dry_run:
                    con.execute("""
                        INSERT INTO place_candidate(candidate_id,extraction_id,place_text,administrative_level,context_text,status)
                        VALUES(:candidate_id,:extraction_id,:place_text,:administrative_level,:context_text,'unreviewed')
                        ON CONFLICT(candidate_id) DO UPDATE SET place_text=excluded.place_text,
                          administrative_level=excluded.administrative_level,context_text=excluded.context_text
                    """, record)
        if not args.dry_run:
            con.commit()
    if args.output:
        fields = ["candidate_id", "document_id", "place_text", "administrative_level", "context_text"]
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows([{key: row[key] for key in fields} for row in audit])
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
