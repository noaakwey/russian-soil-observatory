#!/usr/bin/env python3
"""Extract Springer PDF text reproducibly with pdftotext, resuming safely."""
from __future__ import annotations
import argparse, concurrent.futures, subprocess
from pathlib import Path

def convert(pdf: Path, out_dir: Path) -> tuple[str, bool, str]:
    out = out_dir / f"{pdf.stem}.txt"
    if out.exists() and out.stat().st_size > 100:
        return pdf.name, True, "existing"
    tmp = out.with_suffix(".tmp")
    result = subprocess.run(["pdftotext", "-layout", str(pdf), str(tmp)], capture_output=True, text=True)
    if result.returncode or not tmp.exists():
        return pdf.name, False, (result.stderr or "pdftotext failed")[:300]
    tmp.replace(out)
    return pdf.name, True, "created"

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--pdf-dir',type=Path,required=True); p.add_argument('--out-dir',type=Path,required=True); p.add_argument('--workers',type=int,default=4); a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=True)
    pdfs=sorted(a.pdf_dir.rglob('*.pdf')); ok=fail=existing=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as ex:
        for name, success, state in ex.map(lambda f:convert(f,a.out_dir),pdfs):
            ok += success; fail += not success; existing += state=='existing'
            if (ok+fail)%100==0: print(f'progress total={ok+fail}/{len(pdfs)} ok={ok} fail={fail}',flush=True)
    print(f'complete total={len(pdfs)} ok={ok} existing={existing} fail={fail}',flush=True)
if __name__=='__main__': main()
