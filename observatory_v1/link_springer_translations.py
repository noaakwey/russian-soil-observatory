#!/usr/bin/env python3
"""Link Springer/Eurasian Soil Science translations to Pochvovedenie originals.

No documents are ever merged — a link only asserts that two ``document`` rows
describe the same article, so downstream analysis can choose whether to
deduplicate them. Two independent methods populate ``document_link``, tried
in order of evidence strength:

1. **Printed footnote** (``confidence='confirmed'``). Many Eurasian Soil
   Science articles print "Original Russian Text (c) ..., published in
   Pochvovedenie, YEAR, No. ISSUE" — direct printed evidence. This practice
   stopped after 2018 in this corpus (verified: 1 974 hits across
   2006-2018, zero after), so it cannot link the 2019-2023 slice the local
   Pochvovedenie corpus actually covers, but is kept for when that corpus is
   extended backward.

2. **Value fingerprint** (``confidence='candidate'``). A translation prints
   the same tables as its original — the numbers survive translation even
   though the prose doesn't. For each Pochvovedenie document, compare its set
   of trusted table values against every Springer document published within
   one year (translation year is uncertain by up to a year for the
   continuous-submission DOI block; see infer_springer_publication_year.py).
   A match is written only when it is the **mutual** best match in both
   directions (this Pochvovedenie doc's best Springer match also lists this
   Pochvovedenie doc as ITS best match) and clears a Jaccard/margin bar —
   thresholds were chosen by inspecting the full score distribution: genuine
   matches cluster at Jaccard >= 0.25 with >= 1.8x separation from the
   runner-up; coincidental value overlap clusters at Jaccard < 0.15 with
   ~1.0-1.1x separation (no separation at all, i.e. noise).
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path

DDL = """
CREATE TABLE IF NOT EXISTS document_link (
  document_id_a TEXT NOT NULL REFERENCES document(document_id),
  document_id_b TEXT NOT NULL REFERENCES document(document_id),
  relation TEXT NOT NULL CHECK (relation IN ('translation_of','same_study','cites','possible_overlap')),
  confidence TEXT NOT NULL CHECK (confidence IN ('confirmed','candidate','rejected')),
  evidence_note TEXT,
  PRIMARY KEY (document_id_a, document_id_b, relation)
);
"""

# --------------------------------------------------------------------------
# Method 1: printed "Original Russian Text (c) ..." footnote
# --------------------------------------------------------------------------

FOOTNOTE = re.compile(
    r'Original Russian Text\s*©\s*([^,\n]+).*?published in Pochvovedenie,\s*(\d{4}),\s*No\.\s*(\d+)',
    re.I | re.S,
)
SURNAME = re.compile(r"[A-Za-zА-Яа-яЁё\-']{3,}")

# ``Pochved{YY}{II}{NNN}{Surname}`` — verified against all 625 local records:
# 2-digit year, 2-digit issue (or a 60+ continuous-submission block that does
# not correspond to a real issue number), 3-digit article-within-issue index.
POCHVED_ID = re.compile(r'pochvovedenie:Pochved(\d{2})(\d{2})(\d{3})(.+)$')


def link_by_footnote(con: sqlite3.Connection) -> dict:
    stats = {'springer_texts': 0, 'footnote_found': 0, 'surname_missing': 0,
             'unique_match': 0, 'ambiguous': 0, 'no_match': 0}
    payload = []
    rows = con.execute("""
        SELECT a.document_id, e.raw_text FROM source_artifact a
        JOIN extraction e ON e.artifact_id = a.artifact_id
        WHERE a.artifact_type = 'text' AND a.document_id LIKE 'springer:%'
    """).fetchall()
    stats['springer_texts'] = len(rows)

    for springer_id, text in rows:
        match = FOOTNOTE.search(text or '')
        if not match:
            continue
        stats['footnote_found'] += 1
        author, year, issue = match.groups()
        names = SURNAME.findall(author)
        if not names:
            stats['surname_missing'] += 1
            continue
        last = names[-1]
        yy = int(year) % 100
        candidates = con.execute("""
            SELECT document_id FROM document
            WHERE corpus = 'pochvovedenie' AND document_id LIKE ?
        """, (f'pochvovedenie:Pochved{yy:02d}{int(issue):02d}%{last}',)).fetchall()
        if len(candidates) == 1:
            stats['unique_match'] += 1
            note = (f'Printed footnote: "Original Russian Text (c) {author.strip()}, '
                    f'published in Pochvovedenie, {year}, No. {issue}."')
            payload.append((springer_id, candidates[0][0], note))
        elif len(candidates) > 1:
            stats['ambiguous'] += 1
        else:
            stats['no_match'] += 1

    con.executemany("""
        INSERT OR REPLACE INTO document_link
          (document_id_a, document_id_b, relation, confidence, evidence_note)
        VALUES (?, ?, 'translation_of', 'confirmed', ?)
    """, payload)
    stats['linked'] = len(payload)
    return stats


# --------------------------------------------------------------------------
# Method 2: value fingerprint (mutual best match)
# --------------------------------------------------------------------------

MIN_SHARED_VALUES = 5
MIN_JACCARD = 0.25
MIN_MARGIN = 1.8
MAX_YEAR_DIFF = 1


def value_sets(con: sqlite3.Connection, corpus: str, year_filter: str = '') -> dict[str, set[float]]:
    out: dict[str, set[float]] = defaultdict(set)
    query = f"""
        SELECT o.document_id, o.value_num_raw
        FROM table_observation o
        JOIN observation_quality_flag f ON f.observation_id = o.observation_id
        JOIN document d ON d.document_id = o.document_id
        {"JOIN document_publication_year y ON y.document_id = o.document_id" if year_filter else ""}
        WHERE d.corpus = '{corpus}' AND f.header_match_kind <> 'symbol_embedded'
          AND f.value_plausibility = 'ok' AND o.value_num_raw IS NOT NULL
          {year_filter}
    """
    for document_id, value in con.execute(query):
        out[document_id].add(round(value, 2))
    return out


def best_matches(source: dict[str, set], target: dict[str, set],
                 min_shared: int = MIN_SHARED_VALUES) -> dict[str, list[tuple[float, int, str]]]:
    scored_all = {}
    for source_id, source_set in source.items():
        if len(source_set) < min_shared:
            continue
        scored = []
        for target_id, target_set in target.items():
            shared = source_set & target_set
            if len(shared) < min_shared:
                continue
            jaccard = len(shared) / len(source_set | target_set)
            scored.append((jaccard, len(shared), target_id))
        scored.sort(reverse=True)
        if scored:
            scored_all[source_id] = scored
    return scored_all


def link_by_fingerprint(con: sqlite3.Connection, already_linked: set[str]) -> dict:
    stats = {'candidates_considered': 0, 'linked': 0, 'rejected_ambiguous': 0,
             'rejected_year_gap': 0}

    poch = value_sets(con, 'pochvovedenie')
    springer = value_sets(
        con, 'springer',
        "AND y.publication_year BETWEEN 2018 AND 2024")
    poch_year = dict(con.execute(
        "SELECT document_id, publication_year FROM document WHERE corpus='pochvovedenie'"))
    springer_year = dict(con.execute(
        "SELECT document_id, publication_year FROM document_publication_year"))

    p2s = best_matches(poch, springer)
    s2p = best_matches(springer, poch)
    stats['candidates_considered'] = len(p2s)

    payload = []
    for pochvovedenie_id, scored in p2s.items():
        if pochvovedenie_id in already_linked:
            continue
        best_jaccard, best_shared, best_springer_id = scored[0]
        if best_springer_id in already_linked:
            continue
        second_jaccard = scored[1][0] if len(scored) > 1 else 0.0
        margin = best_jaccard / second_jaccard if second_jaccard > 0 else 99.0

        back = s2p.get(best_springer_id, [])
        mutual = bool(back) and back[0][2] == pochvovedenie_id
        if not mutual:
            stats['rejected_ambiguous'] += 1
            continue
        if not (best_jaccard >= MIN_JACCARD and margin >= MIN_MARGIN):
            continue

        year_diff = abs(poch_year.get(pochvovedenie_id, 0)
                        - springer_year.get(best_springer_id, 0))
        if year_diff > MAX_YEAR_DIFF:
            stats['rejected_year_gap'] += 1
            continue

        note = (f'Value fingerprint: {best_shared} shared table values '
                f'(Jaccard {best_jaccard:.2f}, {margin:.1f}x runner-up, '
                f'mutual best match, year gap {year_diff}).')
        payload.append((best_springer_id, pochvovedenie_id, note))

    con.executemany("""
        INSERT OR REPLACE INTO document_link
          (document_id_a, document_id_b, relation, confidence, evidence_note)
        VALUES (?, ?, 'translation_of', 'candidate', ?)
    """, payload)
    stats['linked'] = len(payload)
    return stats


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        con.execute("DELETE FROM document_link WHERE relation = 'translation_of'")

        footnote_stats = link_by_footnote(con)
        con.commit()

        already = {row[0] for row in con.execute(
            "SELECT document_id_b FROM document_link WHERE relation='translation_of'")}
        already |= {row[0] for row in con.execute(
            "SELECT document_id_a FROM document_link WHERE relation='translation_of'")}

        fingerprint_stats = link_by_fingerprint(con, already)
        con.commit()

        total = con.execute(
            "SELECT COUNT(*) FROM document_link WHERE relation='translation_of'").fetchone()[0]

    report = {'footnote_method': footnote_stats, 'fingerprint_method': fingerprint_stats,
              'total_links': total}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
