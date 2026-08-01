#!/usr/bin/env python3
"""Clear regenerable operational sites before a stricter coordinate rebuild.

Raw documents, OCR cells, parsed table candidates, place candidates and
geocoding responses are retained.  Only derived observations/sites are
removed so they cannot survive a corrected coordinate interpretation.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    args = parser.parse_args()
    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        before = {name: con.execute(f"SELECT count(*) FROM {name}").fetchone()[0] for name in ("site", "measurement", "sample", "profile", "location_candidate")}
        con.execute("DELETE FROM laboratory_analysis_measurement")
        con.execute("DELETE FROM measurement")
        con.execute("DELETE FROM laboratory_analysis")
        con.execute("DELETE FROM sample_evidence")
        con.execute("DELETE FROM sample")
        con.execute("DELETE FROM horizon")
        con.execute("DELETE FROM profile")
        con.execute("DELETE FROM site_evidence")
        con.execute("DELETE FROM site")
        con.execute("DELETE FROM location_validation")
        con.execute("DELETE FROM location_candidate")
        # A geocode remains reproducible, but its prior promotion must not
        # resurrect a site without the current spatial review.
        con.execute("UPDATE place_candidate SET status='unreviewed' WHERE status='accepted'")
        con.commit()
    print(json.dumps({"before": before, "cleared": True}, ensure_ascii=False))


if __name__ == "__main__":
    main()
