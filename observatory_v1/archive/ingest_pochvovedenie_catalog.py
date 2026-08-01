#!/usr/bin/env python3
"""Load the `Почвоведение` document/PDF catalogue without promoting old extracts.

This stage intentionally writes only documents and their source artifacts.
Coordinates, soil classes and measurements from legacy JSON remain candidates
until their source text/table is verified.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path


def title_from_legacy(row: dict) -> str | None:
    note = row.get("notes") or ""
    marker = "Extracted from article:"
    return note.split(marker, 1)[1].strip() if marker in note else None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()

    catalog = json.loads((args.source_root / "all_issues_metadata.json").read_text(encoding="utf-8"))
    legacy = json.loads((args.source_root / "pochved_database_professional.json").read_text(encoding="utf-8"))
    legacy_by_id = {row["article_id"]: row for row in legacy}
    pdf_root = args.source_root / "pdfs_full"

    stats = {"documents": 0, "local_pdfs": 0, "remote_pdfs": 0}
    with sqlite3.connect(args.db) as conn:
        conn.execute("PRAGMA foreign_keys = ON")
        for item in catalog["articles"]:
            source_id = item["article_id"]
            document_id = f"pochvovedenie:{source_id}"
            legacy_row = legacy_by_id.get(source_id, {})
            title = title_from_legacy(legacy_row)
            # Catalogue IDs include an author suffix; downloaded PDFs may use
            # either that full ID or only the stable numeric Pochved ID.
            core = re.match(r"Pochved\d+", source_id)
            patterns = [f"{source_id}*.pdf"]
            if core:
                patterns.append(f"{core.group(0)}*.pdf")
            actual = next((f for pattern in patterns for f in pdf_root.glob(pattern)), None)
            document_path = str(actual) if actual else item["article_url"]
            conn.execute(
                """INSERT INTO document(document_id, corpus, language, title, publication_year, source_path)
                   VALUES (?, 'pochvovedenie', 'ru', ?, ?, ?)
                   ON CONFLICT(document_id) DO UPDATE SET
                     title=COALESCE(excluded.title, document.title),
                     publication_year=excluded.publication_year,
                     source_path=excluded.source_path""",
                (document_id, title, item.get("year"), document_path),
            )
            artifact_path = str(actual) if actual else item["pdf_url"]
            metadata = json.dumps({
                "article_url": item.get("article_url"),
                "pdf_url": item.get("pdf_url"),
                "issue_url": item.get("issue_url"),
                "source_issue": item.get("source_issue"),
                "position_in_issue": item.get("position_in_issue"),
            }, ensure_ascii=False)
            conn.execute(
                """INSERT INTO source_artifact(artifact_id, document_id, artifact_type, source_path, metadata_json)
                   VALUES (?, ?, 'pdf', ?, ?)
                   ON CONFLICT(artifact_id) DO UPDATE SET
                     source_path=excluded.source_path,
                     metadata_json=excluded.metadata_json""",
                (f"{document_id}:pdf", document_id, artifact_path, metadata),
            )
            stats["documents"] += 1
            stats["local_pdfs" if actual else "remote_pdfs"] += 1
        conn.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
