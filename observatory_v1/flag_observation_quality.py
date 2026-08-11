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
    # Content-type properties normalized to g/kg had no upper bound at all,
    # so a header correctly matched to the right property could still carry
    # a value that cannot physically exist at that concentration (soil is
    # not 68% total nitrogen). Found via descriptive statistics: several
    # "Corg, %" / "Total N, %" cells report a value than makes sense as a
    # percentage only in a different context (a ratio, a share of a pool, a
    # normalization to a baseline) and %-to-g/kg conversion (x10) turns that
    # into an impossible three- or four-digit g/kg figure. Bounds are set
    # above the most organic-rich real soils (Histosols) to avoid flagging
    # genuine extreme samples.
    'soil_organic_carbon': (0.0, 600.0, 'organic carbon content 0–600 g/kg (Histosol ceiling)'),
    'total_nitrogen': (0.0, 50.0, 'total nitrogen content 0–50 g/kg'),
    'total_potassium': (0.0, 60.0, 'total potassium content 0–60 g/kg'),
    'soil_depth': (0.0, 2000.0, 'soil depth 0–2 000 cm'),
    'flow_depth': (0.0, 2000.0, 'flow depth 0–2 000 cm'),
    'layer_depth': (0.0, 2000.0, 'layer depth 0–2 000 cm'),
    'soil_moistening_depth': (0.0, 2000.0, 'soil moistening depth 0–2 000 cm'),
    'leaf_length': (0.0, 2000.0, 'leaf length 0–2 000 mm'),
    'root_length': (0.0, 2000.0, 'root length 0–2 000 mm'),

    # Found the same way, once observation_unit_inference (2026-08-04) started
    # assigning a unit to essentially every observation instead of leaving most
    # of them 'missing_unit': several properties had no upper bound at all, so
    # a value evidently pulled from the wrong table column (a neighbouring
    # index, a magnetic-susceptibility reading, a mis-aligned OCR cell) sailed
    # through as physically "ok" once it was mapped to mg/kg or meq/100g.
    # Trace/contaminant elements (microelement, contaminant categories,
    # mg/kg): even heavily polluted soils rarely exceed a few percent by mass.
    'iron': (0.0, 300000.0, 'iron content 0–300 000 mg/kg (30% mass ceiling)'),
    'zinc': (0.0, 50000.0, 'zinc content 0–50 000 mg/kg'),
    'copper': (0.0, 50000.0, 'copper content 0–50 000 mg/kg'),
    'nickel': (0.0, 50000.0, 'nickel content 0–50 000 mg/kg'),
    'manganese': (0.0, 50000.0, 'manganese content 0–50 000 mg/kg'),
    'mercury': (0.0, 1000.0, 'mercury content 0–1 000 mg/kg'),
    'nitrate_n': (0.0, 5000.0, 'nitrate nitrogen 0–5 000 mg/kg'),
    'mineral_nitrogen': (0.0, 5000.0, 'mineral nitrogen 0–5 000 mg/kg'),
    'available_phosphorus': (0.0, 20000.0, 'available phosphorus 0–20 000 mg/kg'),
    'total_dissolved_solids': (0.0, 500.0, 'total dissolved solids 0–500 g/L (saturated brine ceiling)'),
    # Exchangeable cations reported in cmolc/kg: real soils rarely exceed a
    # few tens; 100 is a generous ceiling that still excludes clear column
    # mis-alignment (values in the hundreds of thousands were found).
    'calcium': (0.0, 100.0, 'exchangeable calcium 0–100 cmolc/kg'),
    'magnesium': (0.0, 100.0, 'exchangeable magnesium 0–100 cmolc/kg'),
    # Soil-solution ions (meq/100g): saline soils can genuinely reach tens of
    # meq/100g; 200 is a generous ceiling for real extremes.
    'calcium_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'magnesium_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'sodium_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'potassium_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'chloride_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'sulfate_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'bicarbonate_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'hydrogen_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
    'ammonium_ion': (0.0, 200.0, 'soil-solution ion 0–200 meq/100g'),
}

# Fractions of a whole: meaningless outside 0–100 when the unit really is %.
PERCENT_PROPERTIES = {
    'sand', 'coarse_sand', 'fine_sand', 'silt', 'clay', 'physical_clay',
    'porosity', 'base_saturation', 'aggregate_stability', 'organic_matter',
    'carbonate_equivalent', 'exchangeable_sodium_percentage',
    'gravimetric_water_content', 'field_capacity', 'wilting_point',
    'water_holding_capacity',
    'vegetation_pole_density', 'soil_cover_percentage',
    'coarse_silt', 'medium_silt', 'fine_silt', 'very_coarse_sand',
    'fine_fraction_lt_0_001mm',
    # Elemental-oxide composition (geochemical/elemental_oxide categories):
    # every property below has canonical_unit '%' in property_definition and
    # is a mass fraction of whole-rock/soil composition, so it cannot exceed
    # 100 either. Missing here until observation_unit_inference exposed
    # values like "Fe2O3 = 32 978%" (a magnetic-susceptibility reading
    # mis-aligned to the oxide column) sailing through as physically "ok".
    'silicon_dioxide', 'iron_oxide_fe2o3', 'aluminum_oxide_al2o3',
    'calcium_oxide_cao', 'magnesium_oxide_mgo', 'potassium_oxide_k2o',
    'sodium_oxide_na2o', 'titanium_dioxide', 'manganese_oxide_mno',
    'phosphorus_pentoxide', 'potassium_oxide',
}

# Generic table metrics have no semantic property-specific range. Once the
# printed unit is proven, a few units still have useful physical ceilings.
UNCLASSIFIED_UNIT_RANGE: dict[str, tuple[float | None, float | None, str]] = {
    'cm': (0.0, 2000.0, 'generic length 0–2 000 cm'),
    'mm': (0.0, 2000.0, 'generic length 0–2 000 mm'),
    '%': (0.0, 100.0, 'percentage 0–100'),
    'mg/kg': (0.0, 300000.0, 'generic concentration 0–300 000 mg/kg'),
    '°c': (-100.0, 100.0, 'temperature −100–100 °C'),
    'в°c': (-100.0, 100.0, 'temperature −100–100 °C'),
}

# Categories whose values are amounts of a substance and cannot be negative.
CONTENT_CATEGORIES = {
    'organic', 'macronutrient', 'exchange', 'particle_size', 'microelement',
    'contaminant', 'salinity', 'biological', 'hydrophysical', 'elemental_oxide',
    'soil_solution', 'geochemical', 'vegetation', 'erosion', 'hydrological',
    'hydrometeorological',
}
# Redox potential is genuinely negative in reduced soils.
SIGNED_PROPERTIES = {'redox_potential', 'soil_temperature'}


def normalized_unit_key(unit: str | None) -> str:
    """Normalize common Unicode/OCR variants without guessing missing units."""
    value = (unit or '').strip().lower()
    value = value.replace('º', '°').replace('в°', '°')
    return re.sub(r'\s+', '', value)


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

    if property_id == 'unclassified_table_metric':
        bounds = UNCLASSIFIED_UNIT_RANGE.get(normalized_unit_key(unit))
        if bounds:
            low, high, rule = bounds
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
        unclassified_review_status = dict(con.execute("""
            SELECT COALESCE(q.status, 'no_review') AS review_status, COUNT(*)
            FROM table_observation o
            LEFT JOIN table_manual_review_queue q ON q.candidate_id=o.candidate_id
            WHERE o.property_id='unclassified_table_metric'
            GROUP BY COALESCE(q.status, 'no_review')
            ORDER BY review_status
        """).fetchall())
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
        'unclassified_review_status': unclassified_review_status,
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
