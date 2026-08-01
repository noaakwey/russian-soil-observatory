#!/usr/bin/env python3
"""Windows-side, resumable `pdftotext` extraction for missing Springer text."""
from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument('--list', type=Path, required=True)
    p.add_argument('--pdf-dir', type=Path, required=True)
    p.add_argument('--output-dir', type=Path, required=True)
    p.add_argument('--pdftotext', type=Path, required=True)
    p.add_argument('--manifest', type=Path, required=True)
    a = p.parse_args()
    a.output_dir.mkdir(parents=True, exist_ok=True)
    # PowerShell writes UTF-8 with a BOM on some Windows versions.
    stems = [line.strip() for line in a.list.read_text(encoding='utf-8-sig').splitlines() if line.strip()]
    stats = {'requested': len(stems), 'done': 0, 'skipped_existing': 0, 'missing_pdf': 0, 'failed': 0}
    with a.manifest.open('a', encoding='utf-8') as log:
        for index, stem in enumerate(stems, start=1):
            src, dst = a.pdf_dir / f'{stem}.pdf', a.output_dir / f'{stem}.txt'
            rec = {'index': index, 'doi_stem': stem, 'pdf': str(src), 'text': str(dst)}
            if dst.exists() and dst.stat().st_size > 200:
                rec['status'] = 'skipped_existing'; stats['skipped_existing'] += 1
            elif not src.exists():
                rec['status'] = 'missing_pdf'; stats['missing_pdf'] += 1
            else:
                run = subprocess.run([str(a.pdftotext), '-layout', '-enc', 'UTF-8', str(src), str(dst)],
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if run.returncode == 0 and dst.exists() and dst.stat().st_size > 0:
                    rec['status'] = 'done'; rec['bytes'] = dst.stat().st_size; stats['done'] += 1
                else:
                    rec['status'] = 'failed'; rec['returncode'] = run.returncode
                    rec['stderr'] = run.stderr[-1000:]; stats['failed'] += 1
            log.write(json.dumps(rec, ensure_ascii=False) + '\n'); log.flush()
            if index % 100 == 0:
                print(json.dumps({'progress': index, **stats}, ensure_ascii=False), flush=True)
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == '__main__':
    main()
