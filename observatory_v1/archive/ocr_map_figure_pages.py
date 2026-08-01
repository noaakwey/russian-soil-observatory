#!/usr/bin/env python3
"""Run resumable OCR on an explicit queue of PDF map/scheme pages.

Output remains evidence only: one JSON record per rendered page.  A later
coordinate parser still has to validate coordinate syntax, country and study
context before it can create a site.
"""
from __future__ import annotations

import argparse
import csv
import json
import multiprocessing as mp
import subprocess
import tempfile
from pathlib import Path


def pdf_for(row: dict[str, str], root: Path) -> Path | None:
    stem = row["document_id"].split(":", 1)[1]
    dirs = ([root / "springer_pdfs"] if row["corpus"] == "springer" else
            [root / "pdfs_all", root / "pdfs_full", root / "pdfs"])
    for directory in dirs:
        path = directory / f"{stem}.pdf"
        if path.exists():
            return path
    return None


def done_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    out=set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            try: out.add(json.loads(line)["page_id"])
            except (ValueError, KeyError): continue
    return out


def text_from_result(result) -> str:
    if not result:
        return ""
    # RapidOCR returns (box, text, score) records in current releases.
    return "\n".join(str(item[1]) for item in result if len(item) > 1)


def ocr_in_child(image_path: str, queue) -> None:
    """One hung page must never stop the resumable queue."""
    from rapidocr_onnxruntime import RapidOCR
    result, _elapsed = RapidOCR()(image_path)
    queue.put(text_from_result(result))


def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--queue',type=Path,required=True); p.add_argument('--source-root',type=Path,required=True); p.add_argument('--output',type=Path,required=True); p.add_argument('--limit',type=int,default=0); p.add_argument('--dpi',type=int,default=120); p.add_argument('--page-timeout',type=int,default=75); a=p.parse_args()
    rows=list(csv.DictReader(a.queue.open(encoding='utf-8')))
    already=done_ids(a.output); a.output.parent.mkdir(parents=True,exist_ok=True)
    stats={'queue':len(rows),'already':len(already),'processed':0,'missing_pdf':0,'render_failed':0,'ocr_empty':0,'ocr_timeout':0,'ocr_failed':0}
    with a.output.open('a',encoding='utf-8') as output, tempfile.TemporaryDirectory(prefix='map-ocr-') as tmp:
        tmpdir=Path(tmp)
        for row in rows:
            page_id=f"{row['document_id']}:page:{row['page']}"
            if page_id in already: continue
            if a.limit and stats['processed'] >= a.limit: break
            pdf=pdf_for(row,a.source_root)
            if not pdf:
                stats['missing_pdf']+=1; continue
            image=tmpdir / 'page.png'
            command=['pdftoppm','-f',str(row['page']),'-l',str(row['page']),'-r',str(a.dpi),'-png','-singlefile',str(pdf),str(image.with_suffix(''))]
            proc=subprocess.run(command,capture_output=True,text=True)
            if proc.returncode or not image.exists():
                stats['render_failed']+=1; continue
            queue=mp.Queue(maxsize=1)
            worker=mp.Process(target=ocr_in_child,args=(str(image),queue)); worker.start(); worker.join(a.page_timeout)
            status='ok'
            if worker.is_alive():
                worker.terminate(); worker.join(); text=''; status='timeout'; stats['ocr_timeout']+=1
            elif worker.exitcode != 0 or queue.empty():
                text=''; status='failed'; stats['ocr_failed']+=1
            else:
                text=queue.get()
            stats['ocr_empty'] += int(not text.strip())
            record={**row,'page_id':page_id,'pdf_path':str(pdf),'ocr_text':text,'ocr_status':status,'dpi':a.dpi}
            output.write(json.dumps(record,ensure_ascii=False)+'\n'); output.flush()
            image.unlink(missing_ok=True)
            stats['processed']+=1
    print(json.dumps(stats,ensure_ascii=False))

if __name__=='__main__':main()
