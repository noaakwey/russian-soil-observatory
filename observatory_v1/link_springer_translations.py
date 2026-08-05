#!/usr/bin/env python3
"""Link Springer/Eurasian Soil Science translations to Pochvovedenie originals.

No documents are ever merged — a link only asserts that two ``document`` rows
describe the same article, so downstream analysis can choose whether to
deduplicate them. Two independent methods populate ``document_link``, tried
in order of evidence strength:

1. **Printed citation match** (``confidence='confirmed'``). Two independent
   printed citations are cross-matched: each Pochvovedenie article prints its
   own bibliographic self-reference ("ПОЧВОВЕДЕНИЕ, YEAR, № ISSUE, с.
   PAGES-PAGES") somewhere in its text, and each Eurasian Soil Science article
   prints "(Original) Russian Text ... published in Pochvovedenie, YEAR,
   No. ISSUE, pp. PAGES-PAGES". When the parsed (year, issue, first page,
   last page) tuple matches exactly one Pochvovedenie document, the pair is
   confirmed. (Ported 2026-08 from the ad hoc `.scratch/match_translation_
   citations.py`, which is what actually produced the current 608 confirmed
   links for the 2019-2023 slice — the previous version of this method here,
   based on parsing only the Springer-side footnote and matching it against
   the Pochvovedenie document-ID encoding, could not link that slice at all
   by its own admission, so it was reproducing nothing.)

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
# Method 1: cross-matched printed citations (RU self-citation <-> EN footnote)
# --------------------------------------------------------------------------

RU_SELF_CITATION = re.compile(
    r'ПОЧВОВЕДЕНИЕ\s*,\s*(\d{4})\s*,\s*(?:№|N[oо]?\.?)\s*(\d+)\s*,\s*(?:с\.|pp?\.?)\s*'
    r'([0-9]+)\s*[–—-]\s*([0-9]+)',
    re.I,
)
EN_FOOTNOTE_PATTERNS = [
    re.compile(
        r'(?:Original )?Russian Text.*?published in Pochvovedenie,\s*(\d{4}),\s*'
        r'No\.?\s*(\d+),\s*pp?\.\s*([0-9]+)\s*[–—-]\s*([0-9]+)',
        re.I | re.S,
    ),
    re.compile(
        r'Russian text.*?Pochvovedenie,\s*(\d{4}),\s*(?:No\.?|№)\s*(\d+),\s*'
        r'(?:pp?\.?|с\.?)\s*([0-9]+)\s*[–—-]\s*([0-9]+)',
        re.I | re.S,
    ),
]


def _longest_text(con: sqlite3.Connection, document_id: str) -> str:
    row = con.execute("""
        SELECT e.raw_text FROM extraction e
        JOIN source_artifact a ON a.artifact_id = e.artifact_id
        WHERE a.document_id = ? AND a.artifact_type = 'text'
        ORDER BY length(e.raw_text) DESC LIMIT 1
    """, (document_id,)).fetchone()
    return (row[0] if row else '') or ''


def link_by_footnote(con: sqlite3.Connection) -> dict:
    stats = {'springer_texts': 0, 'citation_found': 0,
             'unique_match': 0, 'ambiguous': 0, 'no_match': 0}

    rus_by_key: dict[tuple[int, int, int, int], list[str]] = {}
    for (document_id,) in con.execute(
            "SELECT document_id FROM document WHERE corpus = 'pochvovedenie'"):
        match = RU_SELF_CITATION.search(_longest_text(con, document_id))
        if match:
            key = tuple(int(g) for g in match.groups())
            rus_by_key.setdefault(key, []).append(document_id)

    payload = []
    springer_ids = [r[0] for r in con.execute(
        "SELECT document_id FROM document WHERE corpus = 'springer'")]
    stats['springer_texts'] = len(springer_ids)

    for springer_id in springer_ids:
        text = _longest_text(con, springer_id)
        match = None
        for pattern in EN_FOOTNOTE_PATTERNS:
            match = pattern.search(text)
            if match:
                break
        if not match:
            continue
        stats['citation_found'] += 1
        key = tuple(int(g) for g in match.groups())
        candidates = rus_by_key.get(key, [])
        if len(candidates) == 1:
            stats['unique_match'] += 1
            note = (f'Exact original-Russian citation: year={key[0]}, issue={key[1]}, '
                     f'pages={key[2]}–{key[3]}; parsed from Springer text and '
                     f'cross-matched against the Pochvovedenie self-citation.')
            payload.append((springer_id, candidates[0], note))
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

    max_year = con.execute(
        "SELECT MAX(publication_year) FROM document WHERE corpus='pochvovedenie'").fetchone()[0]
    poch = value_sets(con, 'pochvovedenie')
    springer = value_sets(
        con, 'springer',
        f"AND y.publication_year BETWEEN 2018 AND {int(max_year) + 1}")
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


# --------------------------------------------------------------------------
# Method 3: raw table-cell fingerprint for the RCNI 2024+ archive
# --------------------------------------------------------------------------
# The 2024+ Pochvovedenie slice (RCNI archive import) has not, at the time of
# writing, gone all the way through table_measurement_candidate materialization
# for every article, so method 2's table_observation-based value sets are
# empty or thin for it. This method instead reads raw OCR cell text directly
# (table_cell.text_raw), for the Pochvovedenie side only — the Springer side
# still uses table_observation, which is materialized for that corpus. Ported
# 2026-08 from the ad hoc `.scratch/link_rcsi_ess_raw.py`, which is what
# produced the current 17 RCNI-slice candidate links.

RAW_NUM = re.compile(r'^[-+]?\d+(?:[.,]\d+)?$')


def raw_pochvovedenie_value_sets(con: sqlite3.Connection, min_year: int) -> dict[str, set[float]]:
    out: dict[str, set[float]] = defaultdict(set)
    rows = con.execute("""
        SELECT a.document_id, tc.text_raw FROM source_artifact a
        JOIN table_cell tc ON tc.artifact_id = a.artifact_id
        JOIN document d ON d.document_id = a.document_id
        WHERE d.corpus = 'pochvovedenie' AND d.publication_year >= ?
          AND a.artifact_type = 'table_json'
    """, (min_year,))
    for document_id, raw in rows:
        text = str(raw).replace(',', '.').replace('−', '-').strip()
        if not RAW_NUM.match(text):
            continue
        try:
            value = round(float(text), 2)
        except ValueError:
            continue
        if abs(value) <= 1_000_000:
            out[document_id].add(value)
    return out


def link_by_raw_fingerprint(con: sqlite3.Connection, already_linked: set[str],
                             min_year: int = 2024) -> dict:
    stats = {'candidates_considered': 0, 'linked': 0}

    poch = raw_pochvovedenie_value_sets(con, min_year)
    springer = value_sets(con, 'springer')
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
            continue
        if not (best_jaccard >= MIN_JACCARD and margin >= MIN_MARGIN):
            continue

        year_diff = abs(poch_year.get(pochvovedenie_id, 0)
                        - springer_year.get(best_springer_id, 0))
        if year_diff > MAX_YEAR_DIFF:
            continue

        note = (f'Raw table fingerprint: {best_shared} shared numeric cells '
                f'(Jaccard {best_jaccard:.2f}, {margin:.1f}x runner-up, '
                f'mutual best match).')
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

        already = {row[0] for row in con.execute(
            "SELECT document_id_b FROM document_link WHERE relation='translation_of'")}
        already |= {row[0] for row in con.execute(
            "SELECT document_id_a FROM document_link WHERE relation='translation_of'")}

        raw_fingerprint_stats = link_by_raw_fingerprint(con, already)
        con.commit()

        total = con.execute(
            "SELECT COUNT(*) FROM document_link WHERE relation='translation_of'").fetchone()[0]

    report = {'footnote_method': footnote_stats, 'fingerprint_method': fingerprint_stats,
              'raw_fingerprint_method': raw_fingerprint_stats, 'total_links': total}
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
