#!/usr/bin/env python3
"""Backfill table_observation.horizon_label_raw from the row-label prefix.

Promoted and hardened from .scratch/extract_horizon_evidence.py (2026-08).
That script's regex accepted any of a handful of letters (O/H/A/.../D) followed
by up to 8 alphanumeric characters, with no check on what came after — enough
to also match ordinary Russian/English words that happen to start with a
horizon letter ("Светло-каштановые", "Control", "Bismuth", "Clay", ...). It
also was never part of the reproducible observatory_v1/ pipeline, so its
prior output (if any) did not survive later table_observation rebuilds.

This version requires two things before accepting a prefix as a horizon code:
1. the text immediately after the code (allowing only punctuation/brackets/
   quote marks in between, never another letter) must lead into a depth range
   ("NN-NN" / "NN–NN"), because that pairing is the actual structural marker
   of a genuine horizon row in these tables;
2. the matched token is not in REJECT — an explicit list of false positives
   found by manually reviewing every one of the 166 distinct tokens the
   regex-plus-depth-check rule accepted, before this list existed (chemical
   formulas, English/German words, sample IDs, ambiguous abbreviations that
   could not be confirmed as real horizon nomenclature).

Idempotent: only touches rows where horizon_label_raw is currently NULL/empty
and row_label_raw is present; safe to rerun after new candidates are added.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from pathlib import Path

PREFIX = re.compile(
    r"(?i)^[\[\(]?(O|H|A|AE|E|EL|BT|B|BC|C|R|AY|AУ|АY|АЕ|А|В|С|D)"
    r"[0-9a-zа-я’′˙.]{0,6}[\]\)]?"
)
TAIL = re.compile(r"^[\s,;|/()\[\]~*\"'’′-]{0,6}\d+\s*[–—-]\s*\d+")

# Found by manually reviewing all 166 distinct tokens the rule accepted
# before this list existed (see plan/session notes, 2026-08-05).
REJECT = {
    "Bismuth", "Burozem", "Clay", "Contro", "Control", "Ditto", "High",
    "Object", "Высокие", "Am.s.", "Oc.l.",
    "A304", "AlCl3", "CATq", "C0rr", "RZAM",
}

DDL = """
CREATE TABLE IF NOT EXISTS observation_horizon_evidence (
  observation_id TEXT PRIMARY KEY REFERENCES table_observation(observation_id),
  horizon_label TEXT NOT NULL,
  evidence_text TEXT NOT NULL,
  method TEXT NOT NULL,
  extracted_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


def match_horizon(row_label: str) -> str | None:
    m = PREFIX.match(row_label)
    if not m:
        return None
    label = m.group(0)
    if label in REJECT:
        return None
    if TAIL.match(row_label[m.end():]):
        return label
    return None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        rows = con.execute("""
            SELECT observation_id, row_label_raw FROM table_observation
            WHERE (horizon_label_raw IS NULL OR horizon_label_raw = '')
              AND row_label_raw IS NOT NULL AND row_label_raw <> ''
        """).fetchall()

        matched = []
        for observation_id, row_label in rows:
            label = match_horizon(str(row_label).strip())
            if label:
                matched.append((observation_id, label, str(row_label).strip()))

        con.executemany("""
            UPDATE table_observation SET horizon_label_raw = ?, updated_at = CURRENT_TIMESTAMP
            WHERE observation_id = ?
        """, [(label, oid) for oid, label, _ in matched])

        con.executemany("""
            INSERT INTO observation_horizon_evidence
              (observation_id, horizon_label, evidence_text, method, extracted_at)
            VALUES (?,?,?,'row_label_prefix',CURRENT_TIMESTAMP)
            ON CONFLICT(observation_id) DO UPDATE SET
              horizon_label=excluded.horizon_label,
              evidence_text=excluded.evidence_text,
              extracted_at=CURRENT_TIMESTAMP
        """, [(oid, label, evidence) for oid, label, evidence in matched])
        con.commit()

        total = con.execute("SELECT COUNT(*) FROM table_observation").fetchone()[0]
        has_horizon = con.execute("""
            SELECT COUNT(*) FROM table_observation
            WHERE horizon_label_raw IS NOT NULL AND horizon_label_raw <> ''
        """).fetchone()[0]

    report = {
        'candidates_considered': len(rows),
        'backfilled': len(matched),
        'total_observations': total,
        'has_horizon_after': has_horizon,
        'has_horizon_pct_after': round(has_horizon / total * 100, 1),
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
