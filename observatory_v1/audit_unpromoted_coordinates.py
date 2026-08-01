#!/usr/bin/env python3
"""Read-only audit of explicit Russian coordinate candidates not on the map."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path

SOIL = re.compile(
    r"(?:\b(?:soil|sample|profile|horizon|site|pit|section)\b|"
    r"почв\w*|образц\w*|разрез\w*|разр\.?(?=\s|\d)|профил\w*|"
    r"горизонт\w*|точк\w*|участк\w*|площадк\w*|отбор\w*|проб\w*|грунт\w*)",
    re.I,
)
MAP = re.compile(r"\b(?:fig(?:ure)?|table|map|location|study area|sampling|"
                 r"рис(?:унок|\.)?|табл(?:ица|\.)?|карта|район исследования|"
                 r"место отбора|пробоотбор)\b", re.I)

SQL = """
SELECT lc.candidate_id, lc.precision_hint, lc.latitude, lc.longitude,
       lc.context_text, d.document_id, d.corpus,
       EXISTS(
         SELECT 1 FROM location_candidate x
         JOIN location_validation xv ON xv.candidate_id=x.candidate_id
         WHERE x.extraction_id LIKE d.document_id || ':%'
           AND x.status='accepted' AND xv.country_code='RU' AND xv.result='inside'
       ) AS document_already_mapped
FROM location_candidate lc
JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
JOIN extraction e ON e.extraction_id=lc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE lc.status='unreviewed' AND lv.country_code='RU' AND lv.result='inside'
ORDER BY d.corpus, d.document_id, lc.candidate_id
"""


def bucket(context: str) -> str:
    if SOIL.search(context or ""):
        return "soil_context"
    if MAP.search(context or ""):
        return "map_or_sampling_context"
    return "other_context"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    with sqlite3.connect(a.db) as con:
        con.row_factory = sqlite3.Row
        rows = [dict(r) for r in con.execute(SQL)]
    counts = Counter((r["precision_hint"], bucket(r["context_text"])) for r in rows)
    document_counts: defaultdict[str, set[str]] = defaultdict(set)
    for r in rows:
        document_counts[r["corpus"]].add(r["document_id"])
    payload = {
        "unpromoted_explicit_ru_candidates": len(rows),
        "documents": {k: len(v) for k, v in document_counts.items()},
        "by_precision_and_context": [
            {"precision_hint": precision, "context": context, "candidates": n}
            for (precision, context), n in sorted(counts.items(), key=lambda kv: -kv[1])
        ],
        "already_mapped_document": int(sum(r["document_already_mapped"] for r in rows)),
        "new_document": int(sum(not r["document_already_mapped"] for r in rows)),
        "examples": [
            {k: r[k] for k in ("candidate_id", "precision_hint", "latitude", "longitude", "document_id", "corpus", "document_already_mapped", "context_text")}
            for r in rows[:20]
        ],
    }
    if a.output:
        a.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
