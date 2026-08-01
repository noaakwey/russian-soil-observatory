#!/usr/bin/env python3
"""OCR rendered map pages locally with the installed Tesseract binary."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import os
import subprocess
from pathlib import Path


def recognize(row: dict, image_dir: Path, languages: str) -> tuple[dict, str]:
    """Run one isolated OCR process and return a durable evidence record."""
    image = image_dir / row["image_name"]
    if not image.exists():
        return row, "missing_image"
    # One core per Tesseract process keeps --workers bounded and avoids nested
    # OpenMP oversubscription on a shared workstation.
    env = {**os.environ, "OMP_THREAD_LIMIT": "1"}
    proc = subprocess.run(
        ["tesseract", str(image), "stdout", "-l", languages, "--psm", "11"],
        capture_output=True,
        env=env,
    )
    text = proc.stdout.decode("utf-8", errors="replace")
    error = proc.stderr.decode("utf-8", errors="replace")
    return {
        **row,
        "ocr_status": "ok" if not proc.returncode else "failed",
        "ocr_text": text,
        "ocr_error": error[-1000:] if proc.returncode else None,
        "ocr_engine": "tesseract",
        "ocr_languages": languages,
    }, "ocr_ok" if not proc.returncode else "ocr_failed"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--image-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--languages", default="rus+eng")
    parser.add_argument("--workers", type=int, default=1)
    args = parser.parse_args()
    done = set()
    if args.output.exists():
        for line in args.output.open(encoding="utf-8"):
            try: done.add(json.loads(line)["page_id"])
            except (ValueError, KeyError): pass
    stats = {"manifest_rows": 0, "already": len(done), "ocr_ok": 0, "ocr_failed": 0, "missing_image": 0}
    pending = []
    for line in args.manifest.open(encoding="utf-8"):
        row = json.loads(line); stats["manifest_rows"] += 1
        if row.get("render_status") != "ok" or row["page_id"] in done:
            continue
        pending.append(row)
    with args.output.open("a", encoding="utf-8") as out, ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(recognize, row, args.image_dir, args.languages) for row in pending]
        for future in as_completed(futures):
            record, status = future.result()
            if status == "missing_image":
                stats["missing_image"] += 1
                continue
            out.write(json.dumps(record, ensure_ascii=False) + "\n"); out.flush()
            stats[status] += 1
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
