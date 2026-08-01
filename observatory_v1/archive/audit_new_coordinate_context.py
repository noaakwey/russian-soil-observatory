#!/usr/bin/env python3
"""Classify newly extracted explicit coordinate contexts without mutating data.

This is a provenance audit, not a geocoder.  It distinguishes a source
fragment that explicitly describes sampling/profile/field work from a merely
geographical mention, so degree-minute coordinates can be expanded without
turning cities and literature examples into soil pits.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path


SAMPLING = re.compile(
    r"\b(?:sample(?:s|d|ing)?|soil\s+(?:profile|pit)|pit\s*[A-Za-z0-9-]+|"
    r"field\s+(?:study|survey|plot|site)|study\s+(?:was|were)\s+(?:carried|conducted)|"
    r"experimental\s+(?:site|plot)|key\s+(?:site|plot)|transect|"
    r"sampling\s+(?:plot|site|point)|profile\s*\d+)\b|"
    r"(?:отбор\w*|образц\w*|разрез\w*|профил\w*|пробн\w*\s+(?:площад|участ)|"
    r"ключев\w*\s+(?:участ|площад)|полев\w*\s+(?:исслед|работ)|"
    r"экспериментальн\w*\s+(?:участ|площад))",
    re.I,
)
# Papers often name a taxon rather than using the literal word "soil".  This
# is an audit signal only: a candidate still needs a local field/study marker
# before it can be considered for manual promotion.  Keeping these stems here
# prevents profile tables from being misclassified as neutral prose merely
# because their Russian or WRB taxon is printed without "почва"/"soil".
SOIL = re.compile(
    r"\b(?:soil|Chernozem|Cryosol|Solonchak|Solonetz|Kastanozem|Luvisol|Podzol|"
    r"Phaeozem|Calcisol|Vertisol|Leptosol|Fluvisol|Gleysol|Histosol|Stagnosol|"
    r"Technosol|Cambisol|Arenosol|Regosol|Umbrisol|Anthrosol)\b|"
    r"(?:почв\w*|черноз[её]м\w*|солонц\w*|солончак\w*|криозем\w*|подзол\w*|"
    r"подбур\w*|литозем\w*|пелозем\w*|петрозем\w*|агрозем\w*|торф\w*|"
    r"гле\w*|аллювиальн\w*|дернов\w*|техноген\w*|каштанов\w*|сероз[её]м\w*)",
    re.I,
)
LABELED_FIELD_OBJECT = re.compile(
    r"(?:\b(?:point|site|plot|pit|profile)\s*(?:no\.?\s*)?[A-Za-z0-9IVX-]+\b|"
    r"(?:точк|участ|площадк|разрез|профил)\w*\s*(?:№\s*)?[0-9IVXА-Яа-я-]+)",
    re.I,
)
STUDY_ACTION = re.compile(
    r"(?:\b(?:study|research|investigation)s?\s+(?:was|were)\s+(?:conducted|carried)|"
    r"\b(?:we\s+)?(?:studied|sampled|investigated|examined)\b|"
    r"(?:исследован|изучен|наблюден|отбор)\w*\s+(?:проводил|проведен|осуществля|выполня|находил)|"
    r"(?:проводил|выполнял|осуществлял)\w*\s+(?:исследован|изучен|отбор)\w*)",
    re.I,
)
BACKGROUND = re.compile(
    r"\b(?:city|capital|population|district\s+center|located\s+in|is\s+found|"
    r"area\s+of|administrative)\b|(?:город\w*|столиц\w*|населени\w*|районн\w*\s+центр|"
    r"расположен\w*|административн\w*)",
    re.I,
)

# A coordinate pair in a figure's graticule is not an observation.  OCR often
# places map ticks, legend text and the caption in one context window, which
# can otherwise inherit an unrelated mention of plots/samples.  Keep these in
# the candidate layer for map review but never classify them as a field point.
MAP_GRID = re.compile(
    r"(?:\bfig\.?\s*\d|\bmap\b|\blegend\b|рис\.\s*\d|картосхем|"
    r"условн\w*\s+обозначен|границ\w*\s+(?:заповедник|район|территор))",
    re.I,
)


def classify(text: str) -> str:
    if MAP_GRID.search(text) and text.count("°") >= 4:
        return "coordinate_range_or_extent"
    if SAMPLING.search(text):
        return "explicit_sampling_or_profile_context"
    # A numbered point/plot is a sampling object only when the same source
    # fragment also names soil.  This admits common Russian article wording
    # (``Точка 2 ... почва ... координаты``) without turning labelled map
    # elements or arbitrary numbered places into soil observations.
    if SOIL.search(text) and (LABELED_FIELD_OBJECT.search(text) or STUDY_ACTION.search(text)):
        return "explicit_sampling_or_profile_context"
    if BACKGROUND.search(text):
        return "geographical_background_context"
    if SOIL.search(text):
        return "soil_context_without_sampling_action"
    return "other_context"


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--db", type=Path, required=True)
    p.add_argument("--precision-prefix", default="russian_abbreviated_")
    p.add_argument("--output", type=Path)
    args = p.parse_args()
    rows: list[dict[str, object]] = []
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        for row in con.execute(
            """SELECT lc.candidate_id, lc.precision_hint, lc.latitude, lc.longitude,
                      lc.context_text, d.document_id, d.corpus
                 FROM location_candidate lc
                 JOIN location_validation lv ON lv.candidate_id=lc.candidate_id
                 JOIN extraction e ON e.extraction_id=lc.extraction_id
                 JOIN source_artifact a ON a.artifact_id=e.artifact_id
                 JOIN document d ON d.document_id=a.document_id
                WHERE lc.precision_hint LIKE ? AND lc.status='unreviewed'
                  AND lv.country_code='RU' AND lv.result='inside'
                ORDER BY d.document_id, lc.candidate_id""",
            (args.precision_prefix + "%",),
        ):
            rec = dict(row)
            rec["context_class"] = classify(str(rec["context_text"] or ""))
            rows.append(rec)
    counts = Counter(str(r["context_class"]) for r in rows)
    if args.output:
        fields = ["candidate_id", "document_id", "corpus", "precision_hint", "latitude", "longitude", "context_class", "context_text"]
        with args.output.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader(); writer.writerows([{key: row.get(key) for key in fields} for row in rows])
    print(json.dumps({"candidates": len(rows), "context_classes": counts}, ensure_ascii=False))


if __name__ == "__main__":
    main()
