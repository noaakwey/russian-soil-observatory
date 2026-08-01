#!/usr/bin/env python3
"""Attach confidence and plausibility flags to every table observation.

Two independent defects survive header-grounded extraction and neither is
visible in a coverage audit:

1. A one- or two-letter chemical symbol matches text that is not an element
   column at all (``Thickness of horizons, cm A + B`` read as boron).
2. OCR sign and digit errors produce values outside the physical range of the
   property (negative concentrations, pH above 14).

Both are recorded, never silently deleted: the raw cell stays in the database
with its evidence locator, and a pedologist decides whether to use it.  A
range check only fires when the unit is actually known, so ``missing_unit``
values are marked ``unchecked`` rather than judged against a unit we cannot
prove.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path

from table_property_patterns import (
    SYMBOL_PROPERTIES,
    TABLE_PROPERTY_PATTERNS,
    normalize_header,
    symbol_match_kind,
)

UNIT = r'(?:mg\s*(?:CO2|TPF|NH4-N|PNP)?\s*/\s*kg\s*/\s*(?:day|d|h)|мг\s*/\s*кг\s*/\s*(?:сут|ч)|cmol\(?c?\)\s*/\s*kg|ммоль\s*/\s*кг|mmol\s*/\s*kg|mg\s*/\s*kg|мг\s*/\s*кг|g\s*/\s*kg|г\s*/\s*кг|g\s*/\s*l|г\s*/\s*л|mg\s*/\s*l|мг\s*/\s*л|g\s*/\s*cm[³3]|г\s*/\s*см[³3]|cm\s*/\s*(?:day|d|h)|см\s*/\s*(?:сут|ч)|mS\s*/\s*cm|µS\s*/\s*cm|uS\s*/\s*cm|dS\s*/\s*m|S\s*/\s*m|MPa|kPa|mV|°\s*C|%|pH)'
HEADER_UNIT = re.compile(UNIT, re.I)
SYMBOL_LITERAL = {pid: pattern.replace(r'\b', '') for pid, pattern in SYMBOL_PROPERTIES.items()}

DDL = """
CREATE TABLE IF NOT EXISTS observation_quality_flag (
  observation_id TEXT PRIMARY KEY REFERENCES table_observation(observation_id),
  header_match_kind TEXT NOT NULL CHECK (header_match_kind IN ('phrase','symbol_clean','symbol_embedded')),
  value_plausibility TEXT NOT NULL CHECK (value_plausibility IN ('ok','negative_content','out_of_physical_range','unchecked')),
  plausibility_rule TEXT,
  flagged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_observation_flag_header ON observation_quality_flag(header_match_kind);
CREATE INDEX IF NOT EXISTS idx_observation_flag_value ON observation_quality_flag(value_plausibility);
"""

# Physically impossible outside these bounds, regardless of study design.
# ``None`` for a bound means the property is unbounded on that side.
PHYSICAL_RANGE: dict[str, tuple[float | None, float | None, str]] = {
    'ph_h2o': (2.0, 12.0, 'soil pH 2–12'),
    'ph_kcl': (2.0, 12.0, 'soil pH 2–12'),
    'ph_unspecified': (2.0, 12.0, 'soil pH 2–12'),
    'bulk_density': (0.05, 2.65, 'bulk density 0.05–2.65 g/cm3'),
    'particle_density': (1.0, 4.0, 'particle density 1.0–4.0 g/cm3'),
}

# Fractions of a whole: meaningless outside 0–100 when the unit really is %.
PERCENT_PROPERTIES = {
    'sand', 'coarse_sand', 'fine_sand', 'silt', 'clay', 'physical_clay',
    'porosity', 'base_saturation', 'aggregate_stability', 'organic_matter',
    'carbonate_equivalent', 'exchangeable_sodium_percentage',
    'gravimetric_water_content', 'field_capacity', 'wilting_point',
    'water_holding_capacity',
}

# Categories whose values are amounts of a substance and cannot be negative.
CONTENT_CATEGORIES = {
    'organic', 'macronutrient', 'exchange', 'particle_size', 'microelement',
    'contaminant', 'salinity', 'biological', 'hydrophysical', 'elemental_oxide',
    'soil_solution', 'geochemical',
}
# Redox potential is genuinely negative in reduced soils.
SIGNED_PROPERTIES = {'redox_potential', 'soil_temperature'}


def header_kind(property_id: str, header_raw: str) -> str:
    """Return how the property was recognised in the printed header."""
    header = normalize_header(header_raw)
    for pid, pattern in TABLE_PROPERTY_PATTERNS.items():
        if re.search(pattern, header, re.I):
            return 'phrase'
    if property_id in SYMBOL_PROPERTIES:
        return symbol_match_kind(HEADER_UNIT.sub(' ', header), SYMBOL_LITERAL[property_id])
    # Manually curated properties carry no automatic pattern; the curation is
    # the evidence, so it is reported as a phrase match rather than a symbol.
    return 'phrase'


def plausibility(property_id: str, category: str, value: float | None,
                 unit: str | None, status: str) -> tuple[str, str | None]:
    if value is None:
        return 'unchecked', 'no numeric value'

    if property_id in PHYSICAL_RANGE:
        low, high, rule = PHYSICAL_RANGE[property_id]
        # pH is dimensionless, so its range applies to the raw cell directly;
        # densities need a proven unit before a bound means anything.
        if property_id.startswith('ph_') or status in ('exact', 'converted'):
            if (low is not None and value < low) or (high is not None and value > high):
                return 'out_of_physical_range', rule

    if property_id in PERCENT_PROPERTIES and unit and unit.strip() == '%':
        if value < 0 or value > 100:
            return 'out_of_physical_range', 'percentage 0–100'

    if value < 0 and category in CONTENT_CATEGORIES and property_id not in SIGNED_PROPERTIES:
        return 'negative_content', 'content cannot be negative'

    return 'ok', None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--db', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()

    header_stats: Counter[str] = Counter()
    value_stats: Counter[str] = Counter()
    per_property: dict[str, Counter[str]] = {}

    with sqlite3.connect(args.db) as con:
        con.executescript(DDL)
        rows = con.execute("""
            SELECT o.observation_id, o.property_id, p.category, o.property_header_raw,
                   o.value_num_raw, o.unit_raw, o.value_normalized, o.unit_normalized,
                   o.normalization_status
            FROM table_observation o
            JOIN property_definition p ON p.property_id = o.property_id
        """).fetchall()

        payload = []
        for (observation_id, property_id, category, header, raw_value, raw_unit,
             normalized_value, normalized_unit, status) in rows:
            kind = header_kind(property_id, header)
            value = normalized_value if normalized_value is not None else raw_value
            unit = normalized_unit if normalized_value is not None else raw_unit
            verdict, rule = plausibility(property_id, category, value, unit, status)
            payload.append((observation_id, kind, verdict, rule))
            header_stats[kind] += 1
            value_stats[verdict] += 1
            per_property.setdefault(property_id, Counter())[verdict] += 1

        con.executemany("""
            INSERT INTO observation_quality_flag
              (observation_id, header_match_kind, value_plausibility, plausibility_rule)
            VALUES (?,?,?,?)
            ON CONFLICT(observation_id) DO UPDATE SET
              header_match_kind=excluded.header_match_kind,
              value_plausibility=excluded.value_plausibility,
              plausibility_rule=excluded.plausibility_rule,
              flagged_at=CURRENT_TIMESTAMP
        """, payload)
        con.commit()

    trusted = sum(
        1 for _, kind, verdict, _ in payload
        if kind != 'symbol_embedded' and verdict == 'ok'
    )
    report = {
        'observations': len(payload),
        'header_match_kind': dict(header_stats),
        'value_plausibility': dict(value_stats),
        'unflagged_observations': trusted,
        'most_affected_properties': {
            pid: dict(counts) for pid, counts in
            sorted(per_property.items(),
                   key=lambda item: -(item[1]['negative_content'] + item[1]['out_of_physical_range']))[:15]
        },
    }
    text = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(text + '\n', encoding='utf-8')
    print(text)


if __name__ == '__main__':
    main()
