#!/usr/bin/env python3
"""Read-only audit of accepted Russian administrative geocodes awaiting promotion."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from promote_geocoded_places import REFERENCE_OR_AFFILIATION, is_study_context

# Broader than the automatic promotion rule, but still requires an explicit
# study-object or sampling action tied to the administrative name.
BROADER_STUDY = re.compile(
    r"(?:\b(?:study|research|experimental|field|sampling|survey)\b|"
    r"(?:объект|район|территор|участк|площадк|полигон|стационар)\w*\s+(?:исследован|изучен|наблюден|отбор|опытн)|"
    r"(?:исследован|изучен|отбор|проводил|заложен|расположен)\w*\s+(?:в|на|для|территор|район|участк|площадк)|"
    r"(?:почв|образц|разрез|профил)\w*[^.]{0,80}(?:район|област|край|республик)\w*)",
    re.I,
)

SQL = """
SELECT pc.candidate_id,pc.place_text,pc.administrative_level,pc.context_text,
       pg.display_name,pg.spatial_precision_m,d.corpus,d.document_id
FROM place_candidate pc JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
JOIN extraction e ON e.extraction_id=pc.extraction_id
JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE pc.status='unreviewed' AND pg.status='accepted' AND pg.country_code='RU'
"""

def tier(context: str) -> str:
    if REFERENCE_OR_AFFILIATION.search(context or ""):
        return "reference_or_affiliation"
    if is_study_context(context or ""):
        return "existing_direct_rule"
    if BROADER_STUDY.search(context or ""):
        return "broader_study_context"
    return "context_insufficient"

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--db', type=Path, required=True); a=p.parse_args()
    with sqlite3.connect(a.db) as con:
        con.row_factory=sqlite3.Row; rows=[dict(r) for r in con.execute(SQL)]
    counts=Counter((tier(r['context_text']),r['administrative_level']) for r in rows)
    examples=[]
    for r in rows:
        if tier(r['context_text'])=='broader_study_context' and len(examples)<20:
            examples.append({k:r[k] for k in ('candidate_id','place_text','administrative_level','display_name','spatial_precision_m','document_id','context_text')})
    print(json.dumps({'unpromoted_accepted_geocodes':len(rows),'by_tier_and_level':[
        {'tier':k[0],'administrative_level':k[1],'candidates':v} for k,v in sorted(counts.items(),key=lambda x:-x[1])], 'examples':examples},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
