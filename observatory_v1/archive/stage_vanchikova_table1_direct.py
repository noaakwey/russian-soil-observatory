#!/usr/bin/env python3
"""Stage fully parsed direct-profile values from Vanchikova et al., Table 1.

This is intentionally a narrow, evidence-preserving template stage.  It uses
the read-only parser audit and writes only a row whose profile label,
coordinate, horizon/depth and all 12 table cells are present in the original
line-oriented source text.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
from pathlib import Path

from audit_vanchikova_table1 import (
    DOCUMENT, DEPTH, SCALAR, SIGNATURE, first_coordinate_end, lines,
    parse_depth, profile_block, source_text,
)


PROPERTIES = (
    ("ph_h2o", "pH in water", "acid_base", "pH", "pH", 1.0),
    ("ph_kcl", "pH in KCl", "acid_base", "pH", "pH", 1.0),
    ("water_soluble_organic_carbon", "water soluble organic carbon", "organic", "mg/kg", "mg/kg", 1.0),
    ("soil_organic_carbon", "soil organic carbon", "organic", "g/kg", "%", 10.0),
    ("silicon_dioxide", "silicon dioxide", "geochemical", "%", "%", 1.0),
    ("iron_oxide_fe2o3", "iron oxide Fe2O3", "geochemical", "%", "%", 1.0),
    ("aluminum_oxide_al2o3", "aluminum oxide Al2O3", "geochemical", "%", "%", 1.0),
    ("calcium_oxide_cao", "calcium oxide CaO", "geochemical", "%", "%", 1.0),
    ("magnesium_oxide_mgo", "magnesium oxide MgO", "geochemical", "%", "%", 1.0),
    ("potassium_oxide_k2o", "potassium oxide K2O", "geochemical", "%", "%", 1.0),
    ("sodium_oxide_na2o", "sodium oxide Na2O", "geochemical", "%", "%", 1.0),
    ("fine_fraction_lt_0_001mm", "fine fraction <0.001 mm", "particle_size", "%", "%", 1.0),
)


def token(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:20]


def values_for_profile(text: str, label: str, latitude: float, longitude: float) -> tuple[str, float, float, list[str], str] | None:
    found = profile_block(text, label, latitude, longitude)
    if not found or not all(item.casefold() in text.casefold() for item in SIGNATURE):
        return None
    _header, block = found
    coordinate_end = first_coordinate_end(block)
    if coordinate_end is None:
        return None
    tail = lines(block[coordinate_end:])
    while tail and tail[0].startswith("[") and tail[0].endswith("]"):
        tail.pop(0)
    if len(tail) < 14 or not DEPTH.fullmatch(tail[1]):
        return None
    raw = tail[2:14]
    if len(raw) != len(PROPERTIES) or not all(SCALAR.fullmatch(value) for value in raw):
        return None
    if any(value in {"-", "−"} for value in raw):
        return None
    top, bottom = parse_depth(tail[1])
    return tail[0], top, bottom, raw, " | ".join(lines(block)[:40])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    stats = {"direct_profiles": 0, "complete_rows": 0, "staged_measurements": 0}
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        profiles = con.execute(
            """SELECT p.profile_id,p.profile_label,p.site_id,s.latitude,s.longitude,a.artifact_id,a.source_path
               FROM profile p JOIN site s ON s.site_id=p.site_id
               JOIN profile_evidence pe ON pe.profile_id=p.profile_id AND pe.evidence_kind='profile_description'
               JOIN source_artifact a ON a.artifact_id=pe.artifact_id
               WHERE p.notes='Direct profile-label-to-coordinate link in one source fragment.'
                 AND a.document_id=?""", (DOCUMENT,)
        ).fetchall()
        for row in profiles:
            stats["direct_profiles"] += 1
            text = source_text(con, row["artifact_id"], row["source_path"])
            if not text:
                continue
            parsed = values_for_profile(text, row["profile_label"], row["latitude"], row["longitude"])
            if not parsed:
                continue
            horizon_label, depth_top, depth_bottom, raw_values, source_block = parsed
            stats["complete_rows"] += 1
            horizon_id = f"horizon:direct-table1:{token(row['profile_id'] + ':' + horizon_label)}"
            sample_id = f"sample:direct-table1:{token(row['profile_id'] + ':' + horizon_label)}"
            analysis_id = f"analysis:direct-table1:{token(row['profile_id'] + ':' + horizon_label)}"
            if not args.dry_run:
                for pid, name, category, canonical_unit, _raw_unit, _factor in PROPERTIES:
                    con.execute("""INSERT INTO property_definition(property_id,canonical_name,category,canonical_unit,description)
                                   VALUES(?,?,?,?,?) ON CONFLICT(property_id) DO NOTHING""",
                                (pid, name, category, canonical_unit, "Direct-profile Table 1 template; source value and unit retained."))
                con.execute("""INSERT INTO horizon(horizon_id,profile_id,horizon_label,depth_top_cm,depth_bottom_cm)
                               VALUES(?,?,?,?,?) ON CONFLICT(horizon_id) DO UPDATE SET
                               horizon_label=excluded.horizon_label,depth_top_cm=excluded.depth_top_cm,depth_bottom_cm=excluded.depth_bottom_cm""",
                            (horizon_id, row["profile_id"], horizon_label, depth_top, depth_bottom))
                con.execute("""INSERT INTO sample(sample_id,site_id,profile_id,horizon_id,sample_label,depth_top_cm,depth_bottom_cm,notes)
                               VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(sample_id) DO UPDATE SET horizon_id=excluded.horizon_id""",
                            (sample_id, row["site_id"], row["profile_id"], horizon_id, row["profile_label"], depth_top, depth_bottom,
                             "Direct coordinate/profile/table-row linkage."))
                con.execute("""INSERT INTO sample_evidence(sample_id,artifact_id,extraction_id,evidence_text)
                               VALUES(?,?,NULL,?) ON CONFLICT(sample_id,artifact_id) DO UPDATE SET evidence_text=excluded.evidence_text""",
                            (sample_id, row["artifact_id"], source_block))
                con.execute("""INSERT INTO laboratory_analysis(analysis_id,sample_id,analysis_label,method_raw,evidence_artifact_id,evidence_extraction_id)
                               VALUES(?,?,?,NULL,?,NULL) ON CONFLICT(analysis_id) DO NOTHING""",
                            (analysis_id, sample_id, "Direct-profile Table 1 row", row["artifact_id"]))
            for index, ((pid, _name, _category, canonical_unit, raw_unit, factor), raw_value) in enumerate(zip(PROPERTIES, raw_values)):
                value = float(raw_value.replace(",", "."))
                normalized = value * factor
                measurement_id = f"measurement:direct-table1:{token(row['profile_id'] + ':' + pid)}"
                locator = json.dumps({
                    "parser": "stage_vanchikova_table1_direct.py", "document": DOCUMENT,
                    "table": "Table 1. Характеристика образцов почв", "profile_label": row["profile_label"],
                    "horizon_label": horizon_label, "depth_cm": [depth_top, depth_bottom],
                    "property_position": index, "raw_value": raw_value, "raw_unit": raw_unit,
                    "source_block": source_block,
                }, ensure_ascii=False)
                if not args.dry_run:
                    con.execute("""INSERT INTO measurement(measurement_id,site_id,profile_id,horizon_id,property_id,value_num,value_text,
                                   unit_raw,unit_normalized,method_raw,qa_status,evidence_artifact_id,evidence_extraction_id,evidence_locator)
                                   VALUES(?,?,?,?,?,?,?, ?,?,NULL,'accepted',?,NULL,?)
                                   ON CONFLICT(measurement_id) DO UPDATE SET value_num=excluded.value_num,value_text=excluded.value_text,
                                   unit_raw=excluded.unit_raw,unit_normalized=excluded.unit_normalized,qa_status='accepted',evidence_locator=excluded.evidence_locator""",
                                (measurement_id, row["site_id"], row["profile_id"], horizon_id, pid, normalized, raw_value,
                                 raw_unit, canonical_unit, row["artifact_id"], locator))
                    con.execute("""INSERT INTO laboratory_analysis_measurement(analysis_id,measurement_id) VALUES(?,?)
                                   ON CONFLICT(analysis_id,measurement_id) DO NOTHING""", (analysis_id, measurement_id))
                stats["staged_measurements"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(stats, ensure_ascii=False))


if __name__ == "__main__":
    main()
