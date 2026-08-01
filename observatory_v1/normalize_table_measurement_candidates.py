#!/usr/bin/env python3
"""Normalize every OCR table candidate without changing raw evidence or spatial tier."""
from __future__ import annotations

import argparse
import json
import sqlite3
from collections import Counter
from pathlib import Path

from normalize_measurement_candidates import convert


DDL = """
CREATE TABLE IF NOT EXISTS table_measurement_candidate_normalization (
  candidate_id TEXT PRIMARY KEY REFERENCES table_measurement_candidate(candidate_id),
  value_normalized REAL,
  unit_normalized TEXT,
  normalization_status TEXT NOT NULL CHECK (normalization_status IN ('exact','converted','incompatible','missing_unit','missing_value')),
  warning TEXT,
  normalizer_version TEXT NOT NULL,
  normalized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def main() -> None:
    p=argparse.ArgumentParser();p.add_argument('--db',type=Path,required=True);a=p.parse_args(); stats=Counter()
    with sqlite3.connect(a.db) as con:
        con.execute(DDL)
        rows=con.execute("""SELECT t.candidate_id,t.value_num,t.unit_raw,t.property_id,p.canonical_unit
            FROM table_measurement_candidate t LEFT JOIN property_definition p ON p.property_id=t.property_id""")
        for candidate_id,value,raw,property_id,canonical_unit in rows:
            normalized,unit,status,warning=convert(value,raw,canonical_unit,property_id)
            con.execute("""INSERT INTO table_measurement_candidate_normalization
              (candidate_id,value_normalized,unit_normalized,normalization_status,warning,normalizer_version)
              VALUES(?,?,?,?,?,'v1') ON CONFLICT(candidate_id) DO UPDATE SET
              value_normalized=excluded.value_normalized,unit_normalized=excluded.unit_normalized,
              normalization_status=excluded.normalization_status,warning=excluded.warning,
              normalizer_version=excluded.normalizer_version,normalized_at=CURRENT_TIMESTAMP""",
              (candidate_id,normalized,unit,status,warning))
            stats[status]+=1
        con.commit()
    print(json.dumps({'candidates':sum(stats.values()),'by_status':dict(stats)},ensure_ascii=False))


if __name__=='__main__':main()
