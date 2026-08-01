#!/usr/bin/env python3
"""Extract dated source snippets for the currently staged Russian documents."""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from pathlib import Path

YEAR = re.compile(r"(?<!\d)(?:18|19|20)\d{2}(?!\d)")
FULL_DATE = re.compile(r"(?:\d{1,2}[./-]){2}(?:18|19|20)\d{2}|(?:Jan(?:uary)?|Feb(?:ruary)?|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+(?:18|19|20)\d{2}", re.I)
RANGE = re.compile(r"(?<!\d)((?:18|19|20)\d{2})\s*(?:–|—|-|to)\s*((?:18|19|20)\d{2})(?!\d)", re.I)
FIELD = re.compile(r"sample|sampling|collected|collection|field study|field work|monitor|monitoring|observation|soil was|soil samples|отбор|образц|полев|мониторинг|наблюден", re.I)
PALEO = re.compile(r"radiocarbon|calibrat|BP\b|paleo|палео|радиоуглерод", re.I)
PUBLICATION = re.compile(r"received|published|ISSN|vol\.\s*\d+|©", re.I)


def classify(context: str) -> str:
    if PALEO.search(context): return "paleochronology"
    if FIELD.search(context): return "field_or_monitoring"
    if PUBLICATION.search(context): return "publication_or_editorial"
    return "other_dated_context"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--text-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        docs = [row[0] for row in con.execute("SELECT DISTINCT a.document_id FROM measurement m JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id WHERE m.qa_status='flagged'")]
    rows = []
    for doc in docs:
        stem = doc.split(":", 1)[1]
        path = args.text_dir / f"{stem}.txt"
        if not path.exists():
            rows.append({"document_id": doc, "date_text": "", "year_start": "", "year_end": "", "date_type": "missing_fulltext", "context": "", "source_path": str(path)})
            continue
        text = path.read_text(encoding="utf-8", errors="replace").replace("\n", " ")
        # Record the strongest expressions first, then remaining year mentions.
        seen = set()
        for pattern in (FULL_DATE, RANGE, YEAR):
            for match in pattern.finditer(text):
                key = (match.start(), match.group(0))
                if key in seen: continue
                seen.add(key)
                context = text[max(0, match.start()-180):min(len(text), match.end()+220)]
                years = [int(y) for y in YEAR.findall(match.group(0))]
                rows.append({"document_id": doc, "date_text": match.group(0), "year_start": years[0] if years else "", "year_end": years[-1] if years else "", "date_type": classify(context), "context": context, "source_path": str(path)})
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["document_id", "date_text", "year_start", "year_end", "date_type", "context", "source_path"])
        writer.writeheader(); writer.writerows(rows)
    print(f"documents={len(docs)} date_snippets={len(rows)}")


if __name__ == "__main__":
    main()
