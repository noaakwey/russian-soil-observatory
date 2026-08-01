#!/usr/bin/env python3
"""Audit whether broader study-context place geocodes are safe to promote."""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from audit_unpromoted_geocodes import BROADER_STUDY
from promote_geocoded_places import REFERENCE_OR_AFFILIATION

GENERIC = {"карта", "схема", "район", "область", "край", "республика", "территория", "место"}
STOP = {"район", "районе", "района", "району", "районом", "область", "области", "областью", "край", "края", "республика", "республики"}
LATIN_ADMIN = {"district", "raion", "rayon", "oblast", "krai", "kray", "republic", "region", "federal", "okrug"}
CYRILLIC_LATIN = str.maketrans({
    "а":"a", "б":"b", "в":"v", "г":"g", "д":"d", "е":"e", "ё":"yo", "ж":"zh", "з":"z", "и":"i", "й":"i",
    "к":"k", "л":"l", "м":"m", "н":"n", "о":"o", "п":"p", "р":"r", "с":"s", "т":"t", "у":"u", "ф":"f",
    # Keep signs as a marker rather than dropping them.  Dropping ``ь`` made
    # distinct districts such as Ровеньский / Ровенский indistinguishable.
    "х":"kh", "ц":"ts", "ч":"ch", "ш":"sh", "щ":"shch", "ы":"y", "э":"e", "ю":"yu", "я":"ya", "ь":"q", "ъ":"q",
})

SQL = """
SELECT pc.candidate_id,pc.place_text,pc.administrative_level,pc.context_text,
       pg.display_name,pg.geometry_kind,pg.spatial_precision_m,d.document_id
FROM place_candidate pc JOIN place_geocode pg ON pg.candidate_id=pc.candidate_id
JOIN extraction e ON e.extraction_id=pc.extraction_id JOIN source_artifact a ON a.artifact_id=e.artifact_id
JOIN document d ON d.document_id=a.document_id
WHERE pc.status='unreviewed' AND pg.status='accepted' AND pg.country_code='RU'
"""

def tokens(value: str) -> list[str]:
    return [x for x in re.findall(r"[A-Za-zА-Яа-яЁё]{3,}", (value or '').casefold()) if x not in STOP]


def latin_tokens(value: str) -> list[str]:
    """Compare article Romanization to Nominatim's Russian display safely.

    This is not a gazetteer inference: it only removes the language barrier
    after Nominatim has already returned one Russian administrative boundary.
    Administrative suffixes are ignored; every remaining article-name token
    must match a substantial prefix in the transliterated provider name.
    """
    normalized = (value or "").casefold().translate(CYRILLIC_LATIN).replace("x", "ks")
    return [x for x in re.findall(r"[a-z]{3,}", normalized) if x not in LATIN_ADMIN]

def name_matches(place: str, display: str) -> bool:
    meaningful = [x for x in tokens(place) if x not in GENERIC]
    if not meaningful:
        return False
    d = " ".join(tokens(display))
    # Six letters avoid accepting a completely different one-letter root while
    # allowing Russian grammatical endings (района / район).
    if all(token[:min(6, len(token))] in d for token in meaningful):
        return True
    source_latin = latin_tokens(place)
    display_latin = latin_tokens(display)
    if not source_latin or not display_latin:
        return False
    return all(any(candidate.startswith(token[:min(7, len(token))])
                   or token.startswith(candidate[:min(7, len(candidate))])
                   for candidate in display_latin)
               for token in source_latin)

def tier(row: dict) -> str:
    context = row['context_text'] or ''
    if REFERENCE_OR_AFFILIATION.search(context): return 'reference_or_affiliation'
    if not BROADER_STUDY.search(context): return 'context_insufficient'
    if not name_matches(row['place_text'], row['display_name']): return 'geocoder_name_mismatch'
    if row['geometry_kind'] != 'boundary_centroid': return 'not_administrative_boundary'
    return 'candidate_geocoded_study_context'

def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);a=p.parse_args()
    with sqlite3.connect(a.db) as c:
        c.row_factory=sqlite3.Row; rows=[dict(r) for r in c.execute(SQL)]
    counts=Counter((tier(r),r['administrative_level']) for r in rows)
    examples=[]
    for r in rows:
        if tier(r)=='candidate_geocoded_study_context' and len(examples)<20:
            examples.append({k:r[k] for k in ('candidate_id','place_text','administrative_level','display_name','geometry_kind','spatial_precision_m','document_id','context_text')})
    print(json.dumps({'candidates':len(rows),'by_tier_and_level':[
        {'tier':k[0],'administrative_level':k[1],'candidates':v} for k,v in sorted(counts.items(), key=lambda x:-x[1])], 'examples':examples},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
