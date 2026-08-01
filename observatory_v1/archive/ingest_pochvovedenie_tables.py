#!/usr/bin/env python3
"""Ingest every raw ``Почвоведение`` OCR table without hiding uncertainty.

The 2,022 JSON files are the source-of-truth table matrices.  They are loaded
verbatim into ``source_artifact`` + ``table_cell`` first.  A previous parser
also produced a small, useful set of semantic suggestions (pH, SOC, humus,
etc.).  Those suggestions are added only as *unreviewed* candidates and are
attached to the original matrix whenever a matching source table exists.

Nothing here creates an operational measurement, a site, or a profile.  Thus a
bad header recovery cannot silently become an observation at a coordinate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sqlite3
from collections import Counter, defaultdict
from pathlib import Path


PROPERTY_MAP = {
    "pH": "ph_unspecified",
    "pH_H2O": "ph_h2o",
    "pH_KCl": "ph_kcl",
    "SOC": "soil_organic_carbon",
    "Humus": "organic_matter",
    "Ntot": "total_nitrogen",
    "BulkDensity": "bulk_density",
}
FILENAME = re.compile(
    r"^(?P<article>Pochved\d+[^_]*)_p(?P<page>\d+(?:-\d+)?)_t(?P<table>\d+)\.json$"
)
CORE = re.compile(r"^(Pochved\d+)")


def artifact_id(document_id: str, name: str) -> str:
    return f"{document_id}:table_json:{name[:-5]}"


def source_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric_equal(raw: str | None, value: object) -> bool:
    if raw is None:
        return False
    try:
        left = float(str(raw).replace("−", "-").replace(",", ".").strip())
        right = float(str(value).replace("−", "-").replace(",", ".").strip())
    except ValueError:
        return str(raw).strip() == str(value).strip()
    return abs(left - right) < 1e-9


def find_value_cells(matrix: list[list[object]], raw: str | None) -> list[tuple[int, int]]:
    return [(r, col) for r, row in enumerate(matrix) for col, value in enumerate(row)
            if numeric_equal(raw, value)]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tables-dir", type=Path, required=True)
    ap.add_argument("--semantic-json", type=Path,
                    help="Existing header-recovery output; kept strictly unreviewed.")
    ap.add_argument("--db", type=Path, required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    files = sorted(args.tables_dir.glob("*.json"))
    stats: Counter[str] = Counter(files=len(files))
    by_article_table: dict[tuple[str, int], list[tuple[Path, dict, str]]] = defaultdict(list)
    parsed: list[tuple[Path, dict, str, str, int]] = []

    for path in files:
        match = FILENAME.match(path.name)
        if not match:
            stats["unrecognised_filename"] += 1
            continue
        record = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        article = match.group("article")
        document_id = f"pochvovedenie:{article}"
        table_no = int(record.get("table_number") or match.group("table"))
        aid = artifact_id(document_id, path.name)
        parsed.append((path, record, document_id, aid, table_no))
        by_article_table[(article, table_no)].append((path, record, aid))

    semantic: list[dict] = []
    if args.semantic_json:
        semantic = json.loads(args.semantic_json.read_text(encoding="utf-8"))
        stats["semantic_input"] = len(semantic)

    with sqlite3.connect(args.db) as con:
        con.execute("PRAGMA foreign_keys=ON")
        con.execute("""INSERT INTO property_definition
            (property_id,canonical_name,category,canonical_unit,description)
            VALUES ('ph_unspecified','pH (method unspecified)','acid_base','pH',
                    'Source reports pH but does not identify the extractant; raw header is retained.')
            ON CONFLICT(property_id) DO NOTHING""")

        known_documents = {row[0] for row in con.execute(
            "SELECT document_id FROM document WHERE corpus='pochvovedenie'"
        )}
        by_core: dict[str, list[str]] = defaultdict(list)
        for document_id in known_documents:
            match = CORE.match(document_id.split(":", 1)[1])
            if match:
                by_core[match.group(1)].append(document_id)

        def resolve_document(article: str | None) -> str | None:
            if not article:
                return None
            exact = f"pochvovedenie:{article}"
            if exact in known_documents:
                return exact
            match = CORE.match(article)
            options = by_core.get(match.group(1), []) if match else []
            return options[0] if len(options) == 1 else None

        for path, record, document_id, aid, table_no in parsed:
            resolved_document = resolve_document(document_id.split(":", 1)[1])
            if not resolved_document:
                stats["table_document_missing"] += 1
                continue
            if resolved_document != document_id:
                # Catalogue suffixes occasionally differ in transliteration or
                # capitalisation; the stable PochvedNNNNNNN identifier is the
                # only reconciliation key used here.
                document_id = resolved_document
                aid = artifact_id(document_id, path.name)
            matrix = record.get("data") or []
            metadata = {k: v for k, v in record.items() if k != "data"}
            metadata["ingest_note"] = "Raw OCR matrix retained verbatim; semantic interpretation is separate."
            if not args.dry_run:
                con.execute("""INSERT INTO source_artifact
                    (artifact_id,document_id,artifact_type,source_path,page_start,page_end,table_label,sha256,metadata_json)
                    VALUES(?,?, 'table_json', ?,?,?,?,?,?)
                    ON CONFLICT(artifact_id) DO UPDATE SET
                      source_path=excluded.source_path,page_start=excluded.page_start,page_end=excluded.page_end,
                      table_label=excluded.table_label,sha256=excluded.sha256,metadata_json=excluded.metadata_json""",
                    (aid, document_id, str(path), record.get("start_page"), record.get("end_page"),
                     str(table_no), source_hash(path), json.dumps(metadata, ensure_ascii=False)))
                for row_index, row in enumerate(matrix):
                    for column_index, value in enumerate(row):
                        if value is None or str(value).strip() == "":
                            continue
                        con.execute("""INSERT INTO table_cell
                            (cell_id,artifact_id,row_index,column_index,text_raw,rowspan,colspan)
                            VALUES(?,?,?,?,?,1,1)
                            ON CONFLICT(artifact_id,row_index,column_index) DO UPDATE SET text_raw=excluded.text_raw""",
                            (f"{aid}:r{row_index}:c{column_index}", aid, row_index, column_index, str(value)))
                        stats["raw_cells"] += 1
            stats["raw_tables"] += 1

        # Recovering a header is valuable, but it is not a fact until a review
        # ties the table row to a sampling unit.  Store it in the candidate
        # layer and keep unresolved cell locations explicit as (-1,-1).
        # It is deliberately attached to the legacy parser output rather than
        # falsely claiming an exact raw OCR cell when a number repeats in a
        # matrix or when the crop changed between parser versions.
        for index, item in enumerate(semantic):
            article = item.get("article_id")
            table_no = item.get("table_number")
            property_id = PROPERTY_MAP.get(item.get("property"))
            document_id = resolve_document(article)
            if not property_id or not document_id:
                stats["semantic_not_linked"] += 1
                continue
            legacy_path = f"{args.semantic_json}#article={article}"
            aid = f"{document_id}:table_json:legacy-v2fixed"
            raw_tables = by_article_table.get((article, table_no), [])
            resolution = "legacy_parser_output"
            if not args.dry_run:
                con.execute("""INSERT INTO source_artifact
                    (artifact_id,document_id,artifact_type,source_path,table_label,metadata_json)
                    VALUES(?,?, 'table_json', ?,?,?)
                    ON CONFLICT(artifact_id) DO UPDATE SET
                      source_path=excluded.source_path,table_label=excluded.table_label,
                      metadata_json=excluded.metadata_json""",
                    (aid, document_id, legacy_path, str(table_no), json.dumps({
                        "ingest_note": "Legacy semantic header recovery; raw OCR matrices are separate artifacts.",
                        "raw_table_artifacts_available": [str(path) for path, _record, _aid in raw_tables],
                    }, ensure_ascii=False)))
            raw_value = item.get("raw")
            try:
                value_num = float(str(raw_value).replace(",", "."))
            except (TypeError, ValueError):
                value_num = item.get("value")
            evidence = {
                "legacy_extractor": "v2_extraction_fixed",
                "recovery": item.get("recovery"),
                "aligned": item.get("aligned"),
                "horizon_resolved": item.get("horizon_resolved"),
                "value_flag": item.get("value_flag"),
                "source_cell_resolution": resolution,
                "raw_table_json_available": [str(path) for path, _record, _aid in raw_tables],
            }
            candidate_id = f"tablecand:pochv-v2fixed:{article}:t{int(table_no):03d}:{index:05d}"
            if not args.dry_run:
                con.execute("""INSERT INTO table_measurement_candidate
                    (candidate_id,artifact_id,row_index,column_index,property_id,property_header_raw,
                     value_num,value_text,unit_raw,row_label_raw,horizon_label,depth_top_cm,depth_bottom_cm,status)
                    VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,'unreviewed')
                    ON CONFLICT(candidate_id) DO UPDATE SET
                      artifact_id=excluded.artifact_id,row_index=excluded.row_index,column_index=excluded.column_index,
                      property_id=excluded.property_id,property_header_raw=excluded.property_header_raw,
                      value_num=excluded.value_num,value_text=excluded.value_text,unit_raw=excluded.unit_raw,
                      row_label_raw=excluded.row_label_raw,horizon_label=excluded.horizon_label,
                      depth_top_cm=excluded.depth_top_cm,depth_bottom_cm=excluded.depth_bottom_cm""",
                    (candidate_id, aid, -1, -1, property_id, item.get("col") or item.get("property"),
                     value_num, None if value_num is not None else str(raw_value), item.get("unit"),
                     json.dumps(evidence, ensure_ascii=False), item.get("horizon"),
                     item.get("depth_top"), item.get("depth_bottom")))
            stats["semantic_candidates"] += 1
        if not args.dry_run:
            con.commit()
    print(json.dumps(dict(stats), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
