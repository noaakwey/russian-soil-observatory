#!/usr/bin/env python3
from __future__ import annotations
import argparse, sqlite3
from pathlib import Path
from method_catalog import METHOD_CATALOG
def main() -> None:
 p=argparse.ArgumentParser(); p.add_argument('--db',type=Path,required=True); a=p.parse_args()
 with sqlite3.connect(a.db) as c:
  c.executemany('INSERT INTO method_definition(method_id,canonical_name,domain,description) VALUES(?,?,?,?) ON CONFLICT(method_id) DO UPDATE SET canonical_name=excluded.canonical_name,domain=excluded.domain,description=excluded.description',METHOD_CATALOG)
 print(f'seeded_or_updated={len(METHOD_CATALOG)}')
if __name__=='__main__': main()
