"""Apply the 2026-08-10 targeted quality repairs to the operational database."""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path


RADIOACTIVE = ('potassium_40_activity', 'cesium_137_activity', 'strontium_90_activity')


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        con.execute('PRAGMA foreign_keys = ON')
        con.executemany(
            "UPDATE property_definition SET category='soil_property', "
            "description='Canonical soil measurement retained from an explicit source header.' "
            "WHERE property_id=?",
            [('horizon_thickness',), ('air_capacity_field_capacity',), ('ph_salt_extract',)],
        )

        # silicon_dioxide is the established canonical ID. Move every
        # operational/staging reference before removing the duplicate row.
        tables = [row[0] for row in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND sql LIKE '%property_id%'"
        )]
        for table in tables:
            if table == 'property_definition':
                continue
            columns = {row[1] for row in con.execute(f'PRAGMA table_info("{table}")')}
            if 'property_id' in columns:
                con.execute(
                    f'UPDATE "{table}" SET property_id=? WHERE property_id=?',
                    ('silicon_dioxide', 'silicon_dioxide_sio2'),
                )
        con.execute("DELETE FROM property_definition WHERE property_id='silicon_dioxide_sio2'")
        con.commit()

        print({
            'radioactivity_categories': con.execute(
                "SELECT property_id, category FROM property_definition "
                "WHERE property_id IN (?,?,?)", RADIOACTIVE
            ).fetchall(),
            'silicon_dioxide_observations': con.execute(
                "SELECT COUNT(*) FROM table_observation WHERE property_id='silicon_dioxide'"
            ).fetchone()[0],
        })


if __name__ == '__main__':
    main()
