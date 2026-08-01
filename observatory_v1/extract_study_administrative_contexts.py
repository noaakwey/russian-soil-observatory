#!/usr/bin/env python3
"""Discover administrative study contexts without turning them into points.

The broad administrative-place harvest is useful as an index but includes
references, affiliations, and geographical background.  This companion pass
keeps only occurrences in the primary text that are locally tied to a field,
soil, sampling, profile, or study action.  It creates evidence candidates;
geocoding and any later low-precision site promotion are separate steps.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from pathlib import Path

from extract_place_candidates import DISTRICT, REGION


BIBLIOGRAPHY = re.compile(r"(?:^|\n)\s*(?:REFERENCES|ЛИТЕРАТУРА|СПИСОК\s+ЛИТЕРАТУРЫ)\s*(?:$|\n)", re.I)
AFFILIATION = re.compile(
    r"(?:\b(?:e-?mail|received|university|institute|department|street|ul\.)\b|"
    r"(?:электронн\w*\s+почт|поступил\w*\s+в\s+редакц|университет|институт|кафедр|ул\.?\s*[А-ЯA-Z]))",
    re.I,
)
GENERIC_PLACE = re.compile(
    r"^(?:данн\w*|карт[аы]-?схем[аы]?|рельеф|климат|атлас|территори\w*|"
    r"исследуем\w*|study\s+area|map\s+of)\s+(?:район|област|край|республик)\w*$",
    re.I,
)
STUDY_ACTION = re.compile(
    r"(?:\b(?:study|research|field\s+study|fieldwork|survey)\s+(?:was|were)\s+(?:conducted|carried)|"
    r"\b(?:soil\s+samples?|samples?|soil\s+profiles?|pits?)\s+(?:were|was)\s+(?:collected|taken|studied|examined)|"
    r"\b(?:we\s+)?(?:studied|investigated|examined|sampled)\b|\bstudy\s+(?:area|site|object)\b|"
    r"(?:территор\w*|участк\w*|почв\w*|образц\w*|разрез\w*|профил\w*)\s+"
    r"(?:исследован|изучен|отобран|заложен|расположен|проводил|выполнял)|"
    r"(?:исследования|отбор\s+(?:образц|проб)|полевые\s+исследован)\s+(?:проводил|выполнен|осуществля))",
    re.I,
)
METHODS_HEADING = re.compile(
    r"(?:ОБЪЕКТЫ\s+И\s+МЕТОДЫ|МАТЕРИАЛЫ\s+И\s+МЕТОДЫ|"
    r"OBJECTS\s+AND\s+METHODS|MATERIALS\s+AND\s+METHODS|STUDY\s+AREA)",
    re.I,
)


def context(text: str, start: int, end: int) -> str:
    return re.sub(r"\s+", " ", text[max(0, start - 420):min(len(text), end + 420)]).strip()


def has_local_study_action(raw: str, place_start: int, place_end: int) -> bool:
    """Require an action close to the place, not elsewhere in the page window."""
    return any(
        min(abs(action.start() - place_end), abs(place_start - action.end())) <= 220
        for action in STUDY_ACTION.finditer(raw)
    )


def in_methods_section(heading_ends: list[int], position: int) -> bool:
    """A local action is stronger evidence when it occurs in Methods, not an introduction."""
    return any(position - 2200 <= end <= position for end in heading_ends)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    audit: list[dict[str, str]] = []
    stats = {"artifacts_scanned": 0, "missing_text": 0, "candidates": 0,
             "district": 0, "region": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT e.extraction_id,a.artifact_id,a.source_path,d.document_id
            FROM extraction e JOIN source_artifact a ON a.artifact_id=e.artifact_id
            JOIN document d ON d.document_id=a.document_id
            WHERE a.artifact_type='text' ORDER BY d.document_id,e.extraction_id
        """).fetchall()
        for row in rows:
            try:
                text = Path(row["source_path"]).read_text(encoding="utf-8", errors="replace")
            except OSError:
                stats["missing_text"] += 1
                continue
            stats["artifacts_scanned"] += 1
            bibliography = BIBLIOGRAPHY.search(text)
            limit = bibliography.start() if bibliography else len(text)
            methods_heading_ends = [match.end() for match in METHODS_HEADING.finditer(text[:limit])]
            for level, pattern in (("district", DISTRICT), ("region", REGION)):
                for match in pattern.finditer(text[:limit]):
                    if GENERIC_PLACE.fullmatch(match.group(0).strip()):
                        continue
                    if not in_methods_section(methods_heading_ends, match.start()):
                        continue
                    window_start = max(0, match.start() - 420)
                    raw_evidence = text[window_start:min(len(text), match.end() + 420)]
                    local_start, local_end = match.start() - window_start, match.end() - window_start
                    evidence = re.sub(r"\s+", " ", raw_evidence).strip()
                    if AFFILIATION.search(evidence) or not has_local_study_action(raw_evidence, local_start, local_end):
                        continue
                    record = {
                        "candidate_id": f"{row['extraction_id']}:study_admin:{level}:{match.start()}",
                        "document_id": row["document_id"], "extraction_id": row["extraction_id"],
                        "place_text": match.group(0), "administrative_level": level,
                        "context_text": evidence,
                    }
                    audit.append(record)
                    stats["candidates"] += 1; stats[level] += 1
                    if not args.dry_run:
                        con.execute(
                            """INSERT INTO place_candidate(candidate_id,extraction_id,place_text,administrative_level,context_text,status)
                               VALUES(:candidate_id,:extraction_id,:place_text,:administrative_level,:context_text,'unreviewed')
                               ON CONFLICT(candidate_id) DO UPDATE SET place_text=excluded.place_text,
                                 administrative_level=excluded.administrative_level,context_text=excluded.context_text""",
                            record,
                        )
        if not args.dry_run:
            con.commit()
    if args.output:
        fields = ["candidate_id", "document_id", "extraction_id", "place_text", "administrative_level", "context_text"]
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows(audit)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
