#!/usr/bin/env python3
"""Build a conservative review queue for source-text soil observation coordinates.

The first coordinate audit intentionally recognised only literal words such as
``soil`` and ``profile``.  In real articles a table row often contains a WRB
or Russian soil name, a sample/pit label and coordinates, but never the word
"soil" itself.  This script recovers that evidence *without* promoting it:

* only coordinates extracted from a primary text artifact are considered;
* the coordinate must have passed the Russia boundary validation;
* a nearby fragment must contain either a soil-taxonomic term plus a table or
  sample/profile marker, or an explicit Russian/English field-observation
  marker;
* duplicate extractions of one document-coordinate are collapsed to one
  candidate, retaining the complete source fragment for audit.

The CSV is deliberately an intermediate, human-readable evidence record.
Promotion remains a separate explicit stage.
"""
from __future__ import annotations

import argparse
import csv
import re
import sqlite3
from collections import Counter
from pathlib import Path


SOIL_TAXON = re.compile(
    r"\b(?:Chernozem|Cryosol|Solonchak|Solonetz|Kastanozem|Luvisol|Podzol|"
    r"Phaeozem|Calcisol|Vertisol|Leptosol|Fluvisol|Gleysol|Histosol|"
    r"Stagnosol|Technosol|Cambisol|Arenosol|Regosol|Umbrisol|Anthrosol|"
    r"peat|bog)\b|(?:почв|черноз[её]м|солонц|солончак|криозем|подзол|"
    r"торф|разрез|горизонт)",
    re.I,
)
FIELD_MARKER = re.compile(
    r"\b(?:soil\s+(?:pit|profile)|profile|pit|plot|sample|sampling|"
    r"mound|fen|borehole|well|experimental\s+(?:field|plot))\b|"
    r"(?:разрез|профил|образец|отбор|точк[аи]|скв\w*|участ\w*|"
    r"площадк|пп\b|поле\s+[А-ЯA-Z]|опытн\w*\s+пол)",
    re.I,
)
TABLE_MARKER = re.compile(r"(?:\btable\s*\d*\b|таблиц\w*|<table|</tr>|<td>)", re.I)
SAMPLE_LABEL = re.compile(r"\b(?:[A-ZА-Я]{1,4}[-–]?\d{1,3}|\d{1,3}[A-ZА-Я][-–]?\d{1,3})\b")
DIRECT_STUDY = re.compile(
    r"\b(?:stud(?:y|ies|ied)|investigat(?:e|ed|ion)|examined|sampled)\b|"
    r"(?:исследован\w*|изучен\w*|отбор\w*|объект\w*\s+исследован)",
    re.I,
)


def evidence_class(context: str) -> str | None:
    """Return a strict reason that makes a coordinate an observation context."""
    taxon = bool(SOIL_TAXON.search(context))
    field = bool(FIELD_MARKER.search(context))
    table = bool(TABLE_MARKER.search(context))
    label = bool(SAMPLE_LABEL.search(context))
    study = bool(DIRECT_STUDY.search(context))
    if taxon and (field or label) and (table or study or field):
        return "taxonomy_plus_field_marker"
    if taxon and table and label:
        return "taxonomy_table_sample_label"
    if taxon and field and study:
        return "taxonomy_explicit_study"
    return None


SQL = """
SELECT lc.candidate_id, lc.latitude, lc.longitude, lc.precision_hint,
       lc.context_text, d.document_id, d.corpus, a.artifact_id
  FROM location_candidate lc
  JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
  JOIN extraction e ON e.extraction_id=lc.extraction_id
  JOIN source_artifact a ON a.artifact_id=e.artifact_id
  JOIN document d ON d.document_id=a.document_id
 WHERE lc.status='unreviewed'
   AND lv.country_code='RU' AND lv.result='inside'
   AND a.artifact_type='text'
 ORDER BY d.document_id, lc.candidate_id
"""


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    # Grouping avoids treating parallel DMS/decimal extractors as separate
    # observations.  Rounded values are only a grouping key; raw doubles stay
    # in the output and database.
    unique: dict[tuple[str, float, float], dict[str, object]] = {}
    reasons: Counter[str] = Counter()
    with sqlite3.connect(a.db) as con:
        con.row_factory = sqlite3.Row
        for rec in con.execute(SQL):
            row = dict(rec)
            reason = evidence_class(str(row["context_text"] or ""))
            if not reason:
                continue
            key = (str(row["document_id"]), round(float(row["latitude"]), 7), round(float(row["longitude"]), 7))
            if key in unique:
                continue
            row["evidence_class"] = reason
            # Keep the generic promotion interface: its category is a
            # decision label, while evidence_class says why it was selected.
            row["category"] = "direct_source_soil_observation"
            unique[key] = row
            reasons[reason] += 1
    fields = ["candidate_id", "document_id", "corpus", "artifact_id", "precision_hint",
              "latitude", "longitude", "category", "evidence_class", "context_text"]
    with a.output.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        for row in unique.values():
            w.writerow({k: row.get(k) for k in fields})
    print({"unique_candidates": len(unique), "evidence_classes": dict(reasons)})


if __name__ == "__main__":
    main()
