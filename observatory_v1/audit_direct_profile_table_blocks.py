#!/usr/bin/env python3
"""Inventory line-oriented source-table blocks for direct-coordinate profiles.

No measurements are written.  The output lets the parser be designed from
the actual PDF-to-text layout: source header, profile label, horizon lines,
and raw value tokens remain together for manual verification.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from audit_vanchikova_table1 import source_text


PROFILE = re.compile(r"(?:Разрез|Soil\s+(?:profile|pit)|Pit)\s+([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9_-]{0,24})", re.I)
NUMERIC = re.compile(r"^(?:[-−]?\d+(?:[.,]\d+)?|[-−])$")


def clean_lines(text: str) -> list[str]:
    return [re.sub(r"\s+", " ", line).strip() for line in text.splitlines() if line.strip()]


def block_for_label(text: str, label: str) -> tuple[str, str] | None:
    matches = [m for m in PROFILE.finditer(text) if m.group(1).casefold() == label.casefold()]
    if len(matches) != 1:
        return None
    start = matches[0].start()
    next_match = PROFILE.search(text, matches[0].end())
    end = next_match.start() if next_match else min(len(text), start + 3000)
    return text[max(0, start - 900):start], text[start:end]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    rows: list[dict[str, object]] = []
    stats: Counter[str] = Counter()
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        query = """
        SELECT p.profile_id, p.profile_label, p.site_id, s.latitude, s.longitude,
               d.document_id, a.artifact_id, a.source_path
        FROM profile p
        JOIN profile_evidence pe ON pe.profile_id=p.profile_id AND pe.evidence_kind='profile_description'
        JOIN source_artifact a ON a.artifact_id=pe.artifact_id
        JOIN document d ON d.document_id=a.document_id
        JOIN site s ON s.site_id=p.site_id
        WHERE p.notes='Direct profile-label-to-coordinate link in one source fragment.'
        ORDER BY d.document_id, p.profile_label
        """
        for record in con.execute(query):
            rec = dict(record)
            text = source_text(con, rec["artifact_id"], rec["source_path"])
            if not text:
                stats["missing_source"] += 1
                continue
            found = block_for_label(text, rec["profile_label"] or "")
            if not found:
                stats["missing_or_ambiguous_profile_block"] += 1
                continue
            header, block = found
            lines = clean_lines(block)
            numeric_lines = [line for line in lines[1:] if NUMERIC.fullmatch(line)]
            rec.update({
                "header_excerpt": " | ".join(clean_lines(header)[-28:]),
                "profile_block": " | ".join(lines[:80]),
                "numeric_token_count": len(numeric_lines),
                "numeric_tokens": ";".join(numeric_lines[:40]),
            })
            rows.append(rec)
            stats["profile_blocks"] += 1
    fields = ["profile_id", "document_id", "profile_label", "latitude", "longitude", "source_path", "numeric_token_count", "numeric_tokens", "header_excerpt", "profile_block"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows([{field: row.get(field) for field in fields} for row in rows])
    print(json.dumps({"stats": stats, "rows": len(rows)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
