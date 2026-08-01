#!/usr/bin/env python3
"""Load Springer OCR evidence into staging; do not infer measurements yet."""
from __future__ import annotations

import argparse
import gzip
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, required=True)
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    stats = {"documents": set(), "crops": 0, "ocr_texts": 0}
    with sqlite3.connect(args.db) as conn, gzip.open(args.index, "rt", encoding="utf-8") as src:
        conn.execute("PRAGMA foreign_keys = ON")
        for line in src:
            row = json.loads(line)
            document_id = row["document_id"]
            source_pdf = row.get("source_pdf") or "unknown.pdf"
            conn.execute(
                """INSERT INTO document(document_id, corpus, language, source_path)
                   VALUES (?, 'springer', 'en', ?)
                   ON CONFLICT(document_id) DO NOTHING""",
                (document_id, f"srv-ecology:C:/ocr_work/{source_pdf}"),
            )
            crop_id = row["artifact_id"]
            crop_metadata = json.dumps({
                key: row.get(key) for key in (
                    "source_pdf", "page_start", "page_end", "table_label", "metadata_path",
                    "ocr_status", "selected_chars", "selected_score", "warnings", "rows", "cols",
                )
            }, ensure_ascii=False)
            conn.execute(
                """INSERT INTO source_artifact(
                     artifact_id, document_id, artifact_type, source_path, page_start, page_end, table_label, metadata_json)
                   VALUES (?, ?, 'crop', ?, ?, ?, ?, ?)
                   ON CONFLICT(artifact_id) DO UPDATE SET metadata_json=excluded.metadata_json""",
                (crop_id, document_id, row["crop_path"], row.get("page_start"), row.get("page_end"),
                 str(row.get("table_label") or ""), crop_metadata),
            )
            markdown_id = f"{crop_id}:ocr_markdown"
            conn.execute(
                """INSERT INTO source_artifact(artifact_id, document_id, artifact_type, source_path, parent_artifact_id)
                   VALUES (?, ?, 'ocr_markdown', ?, ?)
                   ON CONFLICT(artifact_id) DO NOTHING""",
                (markdown_id, document_id, row["markdown_path"], crop_id),
            )
            conn.execute(
                """INSERT INTO extraction(extraction_id, artifact_id, extractor, extractor_version, raw_text, parsed_json, status, quality_score)
                   VALUES (?, ?, 'unlimited-ocr', 'table-ocr-0deg', ?, ?, 'raw', ?)
                   ON CONFLICT(extraction_id) DO UPDATE SET raw_text=excluded.raw_text, parsed_json=excluded.parsed_json""",
                (f"{markdown_id}:raw", markdown_id, row.get("ocr_text") or "", crop_metadata,
                 row.get("selected_score")),
            )
            stats["documents"].add(document_id)
            stats["crops"] += 1
            stats["ocr_texts"] += bool(row.get("ocr_text"))
        conn.commit()
    stats["documents"] = len(stats["documents"])
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
