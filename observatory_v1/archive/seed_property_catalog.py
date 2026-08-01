#!/usr/bin/env python3
"""Seed canonical properties without asserting that any source measured them."""
from __future__ import annotations
import argparse
import sqlite3
from pathlib import Path
from property_catalog import PROPERTY_CATALOG

def main() -> None:
    p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); a=p.parse_args()
    with sqlite3.connect(a.db) as con:
        con.executemany(
            '''INSERT INTO property_definition(property_id,canonical_name,category,canonical_unit,description)
               VALUES(?,?,?,?,?) ON CONFLICT(property_id) DO UPDATE SET
                 canonical_name=excluded.canonical_name,category=excluded.category,canonical_unit=excluded.canonical_unit''',
            [(pid,name,cat,unit,'Canonical vocabulary; source observations remain separately evidenced.')
             for pid,name,cat,unit in PROPERTY_CATALOG],
        )
    print(f'seeded_or_updated={len(PROPERTY_CATALOG)}')

if __name__ == '__main__': main()
