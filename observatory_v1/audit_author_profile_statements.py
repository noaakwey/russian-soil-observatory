#!/usr/bin/env python3
"""Audit provenance invariants for literal author soil/profile statements.

This does not decide whether an author phrase belongs to a neighbouring pit:
that is a review question.  It verifies the mechanical conditions required for
every stored statement, and makes the review queue explicit rather than hiding
uncertain automated matches in ``profile`` convenience fields.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


def compact(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", "", value.casefold())


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        rows = con.execute("""
            SELECT pas.statement_id, pas.profile_id, p.profile_label,
                   pas.field_name, pas.raw_value, pas.review_status,
                   pas.artifact_id, pas.evidence_text, a.artifact_type,
                   a.source_path
            FROM profile_author_statement pas
            JOIN profile p ON p.profile_id = pas.profile_id
            LEFT JOIN source_artifact a ON a.artifact_id = pas.artifact_id
            ORDER BY pas.statement_id
        """).fetchall()

    issues: list[dict[str, str]] = []
    status_counts: dict[str, int] = {}
    field_counts: dict[str, int] = {}
    for row in rows:
        status_counts[row["review_status"]] = status_counts.get(row["review_status"], 0) + 1
        field_counts[row["field_name"]] = field_counts.get(row["field_name"], 0) + 1
        kinds: list[str] = []
        if row["artifact_type"] != "text":
            kinds.append("missing_primary_text_artifact")
        if not row["evidence_text"] or compact(row["raw_value"]) not in compact(row["evidence_text"]):
            kinds.append("value_not_literal_in_evidence")
        if not row["profile_label"] or compact(row["profile_label"]) not in compact(row["evidence_text"]):
            kinds.append("profile_label_not_in_evidence")
        source = Path(row["source_path"]) if row["source_path"] else None
        if not source or not source.is_file():
            kinds.append("source_text_missing")
        elif compact(row["raw_value"]) not in compact(source.read_text(encoding="utf-8", errors="replace")):
            kinds.append("value_not_literal_in_source")
        if kinds:
            issues.append({"statement_id": row["statement_id"], "profile_id": row["profile_id"],
                           "field_name": row["field_name"], "review_status": row["review_status"],
                           "issues": ";".join(kinds)})

    report = {
        "statements": len(rows), "by_status": status_counts,
        "by_field": field_counts, "invariant_violations": issues,
        "ready": not issues,
        "review_note": "unreviewed and flagged are retained evidence, not accepted profile facts",
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
