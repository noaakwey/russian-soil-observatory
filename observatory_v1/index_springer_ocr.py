#!/usr/bin/env python3
"""Create a portable evidence index from Springer Neural Table OCR output.

One JSONL record represents one cropped table fragment.  It keeps the OCR text
and all source locators, but deliberately makes no claim that a row is a soil
measurement or a Russian study point.
"""
from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path


def document_key(meta: dict, fallback: str) -> str:
    pdf = Path(meta.get("source_pdf") or "").stem
    return pdf or fallback.split("_p", 1)[0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ocr-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata_dir = args.ocr_dir / "metadata"
    markdown_dir = args.ocr_dir / "markdown"
    stats = {"records": 0, "ok": 0, "missing_markdown": 0}
    with gzip.open(args.output, "wt", encoding="utf-8") as out:
        for meta_file in sorted(metadata_dir.glob("*.json")):
            meta = json.loads(meta_file.read_text(encoding="utf-8"))
            crop_name = meta.get("crop_name") or f"{meta_file.stem}.png"
            key = document_key(meta, meta_file.stem)
            markdown_path = markdown_dir / f"{meta_file.stem}.md"
            raw_text = markdown_path.read_text(encoding="utf-8", errors="replace") if markdown_path.exists() else ""
            if not raw_text:
                stats["missing_markdown"] += 1
            record = {
                "document_id": f"springer:{key}",
                "artifact_id": f"springer:{key}:crop:{meta_file.stem}",
                "artifact_type": "crop",
                "corpus": "springer",
                "source_pdf": meta.get("source_pdf"),
                "page_start": meta.get("start_page"),
                "page_end": meta.get("end_page"),
                "table_label": meta.get("table_number"),
                "crop_path": meta.get("crop"),
                "markdown_path": str(markdown_path),
                "metadata_path": str(meta_file),
                "ocr_text": raw_text,
                "ocr_status": meta.get("status"),
                "selected_chars": meta.get("selected_chars"),
                "selected_score": meta.get("selected_score"),
                "warnings": meta.get("warnings"),
                "rows": meta.get("rows"),
                "cols": meta.get("cols"),
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            stats["records"] += 1
            stats["ok"] += meta.get("status") == "ok"
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
