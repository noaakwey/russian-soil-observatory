#!/usr/bin/env python3
"""Remove only the regenerable, document-single-site OCR table layer."""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--id-namespace", default="table")
    parser.add_argument("--reset-candidates", action="store_true",
                        help="Return table candidates to unreviewed after deleting a derived evaluation layer.")
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        ns = args.id_namespace
        measurements = [r[0] for r in con.execute("SELECT measurement_id FROM measurement WHERE measurement_id LIKE ?", (f'measurement:{ns}:%',))]
        analyses = [r[0] for r in con.execute("SELECT analysis_id FROM laboratory_analysis WHERE analysis_id LIKE ?", (f'analysis:{ns}:%',))]
        samples = [r[0] for r in con.execute("SELECT sample_id FROM sample WHERE sample_id LIKE ?", (f'sample:{ns}:%',))]
        con.executemany("DELETE FROM laboratory_analysis_measurement WHERE measurement_id=?", [(x,) for x in measurements])
        con.executemany("DELETE FROM measurement WHERE measurement_id=?", [(x,) for x in measurements])
        con.executemany("DELETE FROM laboratory_analysis WHERE analysis_id=?", [(x,) for x in analyses])
        con.executemany("DELETE FROM sample_evidence WHERE sample_id=?", [(x,) for x in samples])
        con.executemany("DELETE FROM sample WHERE sample_id=?", [(x,) for x in samples])
        con.execute("DELETE FROM horizon WHERE horizon_id LIKE ?", (f'horizon:{ns}:%',))
        con.execute("DELETE FROM profile WHERE profile_id LIKE ?", (f'profile:{ns}:%',))
        if args.reset_candidates:
            con.execute("UPDATE table_measurement_candidate SET status='unreviewed'")
        con.commit()
    print(json.dumps({"measurements_removed": len(measurements), "analyses_removed": len(analyses), "samples_removed": len(samples)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
