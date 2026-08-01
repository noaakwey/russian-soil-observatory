#!/usr/bin/env python3
"""Define the property classes the header matcher could not previously express.

Auditing the OCR matrices showed 43 259 numeric cells sitting under headers
that the catalog had no entry for.  They are not exotic: they are four routine
kinds of Russian soil analysis whose headers happen not to be words.

``Ca2+``, ``Cl-``          water extract and exchange complex, reported as ions
``0.05-0.01``, ``<0.001``  Kachinsky particle-size fractions, named by size
``SiO2``, ``TiO2``         bulk chemical composition
``C:N``, ``C:P``           elemental ratios

Two deliberate choices:

*Ions get their own properties rather than being folded into the existing
exchangeable ones.*  A header reading ``Ca2+`` does not say whether the value
came from a water extract or from the exchange complex, and those are different
quantities.  Qualified headers ("exchangeable Ca2+") still match the existing
exchangeable properties, which are tested first.

*Ion properties carry no canonical unit.*  Without the extraction method the
unit cannot be asserted, so values arrive flagged ``missing_unit`` rather than
silently converted — the same treatment ``pH (method unspecified)`` gets.
"""
from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path

# (property_id, canonical_name, category, canonical_unit, description)
NEW_PROPERTIES: list[tuple[str, str, str, str | None, str]] = [
    # --- ions, extraction method unstated -----------------------------------
    ('calcium_ion', 'calcium ion Ca2+', 'soil_solution', None,
     'Ca2+ reported as an ion; water extract or exchange complex not stated'),
    ('magnesium_ion', 'magnesium ion Mg2+', 'soil_solution', None,
     'Mg2+ reported as an ion; extraction not stated'),
    ('sodium_ion', 'sodium ion Na+', 'soil_solution', None,
     'Na+ reported as an ion; extraction not stated'),
    ('potassium_ion', 'potassium ion K+', 'soil_solution', None,
     'K+ reported as an ion; extraction not stated'),
    ('ammonium_ion', 'ammonium ion NH4+', 'soil_solution', None,
     'NH4+ reported as an ion; extraction not stated'),
    ('hydrogen_ion', 'hydrogen ion H+', 'soil_solution', None,
     'H+ reported as an ion; extraction not stated'),
    ('aluminium_ion', 'aluminium ion Al3+', 'soil_solution', None,
     'Al3+ reported as an ion; extraction not stated'),
    ('chloride_ion', 'chloride ion Cl-', 'soil_solution', None,
     'Cl- in the water extract; unit as printed'),
    ('sulfate_ion', 'sulfate ion SO4 2-', 'soil_solution', None,
     'SO4 2- in the water extract; unit as printed'),
    ('bicarbonate_ion', 'bicarbonate ion HCO3-', 'soil_solution', None,
     'HCO3- in the water extract; unit as printed'),
    ('carbonate_ion', 'carbonate ion CO3 2-', 'soil_solution', None,
     'CO3 2- in the water extract; unit as printed'),
    ('nitrate_ion', 'nitrate ion NO3-', 'soil_solution', None,
     'NO3- reported as an ion; extraction not stated'),

    # --- Kachinsky particle-size fractions -----------------------------------
    # The Russian scheme names a fraction by its size limits in millimetres.
    # coarse_sand (1-0.25), fine_sand (0.25-0.05), physical_clay (<0.01) and
    # fine_fraction_lt_0_001mm (<0.001) already exist; these fill the gaps.
    ('coarse_silt', 'coarse silt 0.05-0.01 mm', 'particle_size', '%',
     'Kachinsky coarse silt fraction'),
    ('medium_silt', 'medium silt 0.01-0.005 mm', 'particle_size', '%',
     'Kachinsky medium silt fraction'),
    ('fine_silt', 'fine silt 0.005-0.001 mm', 'particle_size', '%',
     'Kachinsky fine silt fraction'),
    ('very_coarse_sand', 'very coarse sand 3-1 mm', 'particle_size', '%',
     'Fraction coarser than 1 mm'),

    # --- bulk chemical composition -------------------------------------------
    ('titanium_dioxide', 'titanium dioxide TiO2', 'geochemical', '%',
     'Bulk TiO2 content'),
    ('manganese_oxide_mno', 'manganese oxide MnO', 'geochemical', '%',
     'Bulk MnO content'),

    # --- elemental ratios -----------------------------------------------------
    ('carbon_nitrogen_ratio', 'C:N ratio', 'organic', None,
     'Dimensionless ratio of organic carbon to total nitrogen'),
    ('carbon_phosphorus_ratio', 'C:P ratio', 'organic', None,
     'Dimensionless ratio of organic carbon to phosphorus'),
    ('hydrogen_carbon_ratio', 'H:C ratio', 'organic', None,
     'Dimensionless atomic ratio, used in humus chemistry'),
    ('oxygen_carbon_ratio', 'O:C ratio', 'organic', None,
     'Dimensionless atomic ratio, used in humus chemistry'),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    args = parser.parse_args()

    with sqlite3.connect(args.db) as con:
        before = con.execute('SELECT COUNT(*) FROM property_definition').fetchone()[0]
        con.executemany("""
            INSERT OR IGNORE INTO property_definition
              (property_id, canonical_name, category, canonical_unit, description)
            VALUES (?,?,?,?,?)
        """, NEW_PROPERTIES)
        con.commit()
        after = con.execute('SELECT COUNT(*) FROM property_definition').fetchone()[0]

    print(f'property_definition: {before} -> {after} (+{after - before})')


if __name__ == '__main__':
    main()
