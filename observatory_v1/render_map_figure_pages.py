#!/usr/bin/env python3
"""Render a finite map-page queue without an OCR dependency.

This runs beside the PDFs (where Poppler is available) and writes a manifest
for a different machine to OCR.  Rendering and OCR are therefore separately
resumable and each page preserves its document/page provenance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import subprocess
from pathlib import Path

from ocr_map_figure_pages import pdf_for


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--dpi", type=int, default=180)
    args = parser.parse_args()
    rows = list(csv.DictReader(args.queue.open(encoding="utf-8")))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    completed = set()
    if args.manifest.exists():
        for line in args.manifest.open(encoding="utf-8"):
            try: completed.add(json.loads(line)["page_id"])
            except (ValueError, KeyError): pass
    stats = {"queue": len(rows), "already": len(completed), "rendered": 0,
             "missing_pdf": 0, "render_failed": 0}
    with args.manifest.open("a", encoding="utf-8") as out:
        for row in rows:
            page_id = f"{row['document_id']}:page:{row['page']}"
            if page_id in completed:
                continue
            if args.limit and stats["rendered"] >= args.limit:
                break
            pdf = pdf_for(row, args.source_root)
            record = {**row, "page_id": page_id, "pdf_path": str(pdf) if pdf else None,
                      "dpi": args.dpi}
            if not pdf:
                record["render_status"] = "missing_pdf"; stats["missing_pdf"] += 1
            else:
                name = hashlib.sha1(page_id.encode("utf-8")).hexdigest()[:20]
                image = args.output_dir / f"{name}.png"
                command = ["pdftoppm", "-f", row["page"], "-l", row["page"], "-r", str(args.dpi),
                           "-png", "-singlefile", str(pdf), str(image.with_suffix(""))]
                proc = subprocess.run(command, capture_output=True, text=True)
                if proc.returncode or not image.exists():
                    record["render_status"] = "render_failed"; record["render_error"] = proc.stderr[-1000:]
                    stats["render_failed"] += 1
                else:
                    record["render_status"] = "ok"; record["image_name"] = image.name
                    stats["rendered"] += 1
            out.write(json.dumps(record, ensure_ascii=False) + "\n"); out.flush()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
