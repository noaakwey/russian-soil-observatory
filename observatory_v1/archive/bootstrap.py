#!/usr/bin/env python3
"""Create the empty, provenance-first Russian soil observatory SQLite database."""
from pathlib import Path
import sqlite3

HERE = Path(__file__).resolve().parent
DB = HERE / "russian_soil_observatory.sqlite"
SCHEMA = HERE / "schema.sql"

with sqlite3.connect(DB) as conn:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    tables = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )]
print(f"Created {DB} with {len(tables)} tables: {', '.join(tables)}")
