#!/usr/bin/env python3
"""Find actual PDF pages containing a map/scheme caption.

The corpus text files are useful for document discovery, but some have lost
form-feed page boundaries.  They must never be used to infer a PDF page
number.  This program accepts that document queue and runs Poppler against the
source PDF page-by-page, producing the only queue suitable for page rendering.
"""
from __future__ import annotations

import argparse
import csv
import re
import subprocess
from pathlib import Path

from inventory_map_figure_pages import MAP_CAPTION, clean
from ocr_map_figure_pages import pdf_for


PAGES = re.compile(r"^Pages:\s+(\d+)\s*$", re.M)


def page_count(pdf: Path) -> int | None:
    result = subprocess.run(["pdfinfo", str(pdf)], capture_output=True, text=True)
    match = PAGES.search(result.stdout)
    return int(match.group(1)) if result.returncode == 0 and match else None


def page_text(pdf: Path, page: int) -> str:
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page), str(pdf), "-"],
        capture_output=True,
    )
    return result.stdout.decode("utf-8", errors="replace") if result.returncode == 0 else ""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--document-queue", type=Path, required=True,
                        help="CSV from inventory_map_figure_pages.py; used only for document IDs")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    documents: dict[str, dict[str, str]] = {}
    for row in csv.DictReader(args.document_queue.open(encoding="utf-8")):
        documents.setdefault(row["document_id"], row)

    out: list[dict[str, object]] = []
    stats = {"documents": len(documents), "missing_pdf": 0, "pdfinfo_failed": 0,
             "pages_scanned": 0, "candidate_pages": 0}
    for row in documents.values():
        pdf = pdf_for(row, args.source_root)
        if not pdf:
            stats["missing_pdf"] += 1
            continue
        total = page_count(pdf)
        if total is None:
            stats["pdfinfo_failed"] += 1
            continue
        for page in range(1, total + 1):
            text = page_text(pdf, page)
            stats["pages_scanned"] += 1
            match = MAP_CAPTION.search(text)
            if not match:
                continue
            out.append({
                "corpus": row["corpus"], "document_id": row["document_id"],
                "page": page, "caption_fragment": clean(match.group(0))[:450],
            })
            stats["candidate_pages"] += 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fields = ["corpus", "document_id", "page", "caption_fragment"]
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader(); writer.writerows(out)
    print(stats)


if __name__ == "__main__":
    main()
