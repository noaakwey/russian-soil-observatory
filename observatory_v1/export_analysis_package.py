#!/usr/bin/env python3
"""Export a transparent analysis package from the provenance SQLite database."""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import shutil
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def export_query(con: sqlite3.Connection, output: Path, query: str) -> int:
    cursor = con.execute(query)
    columns = [item[0] for item in cursor.description]
    count = 0
    with output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in cursor:
            writer.writerow(dict(row))
            count += 1
    return count


QUERIES = {
    "full_table_observations.csv": """
        SELECT observation_id,candidate_id,corpus,document_id,property,category,
               value_num_raw,value_text_raw,unit_raw,value_normalized,unit_normalized,
               normalization_status,qa_status,spatial_linkage,context_site_id,
               row_label_raw,horizon_label_raw,depth_top_cm,depth_bottom_cm,
               operational_measurement_id,evidence_locator,evidence_path,
               page_start,page_end,table_label
        FROM v_full_table_observations
        ORDER BY document_id,candidate_id
    """,
    "verified_measurements.csv": """
        SELECT *, 'verified_row_coordinate_link' AS analysis_tier
        FROM v_ready_measurements ORDER BY document_id, measurement_id
    """,
    "supported_table_measurements.csv": """
        SELECT m.measurement_id, 'supported_document_single_reported_coordinate' AS analysis_tier,
               d.corpus, d.document_id, d.title, d.doi, s.site_id, s.name AS site_name,
               s.region, s.latitude, s.longitude, s.spatial_precision_m, s.spatial_confidence,
               p.profile_label, h.horizon_label, h.depth_top_cm, h.depth_bottom_cm,
               pd.property_id, pd.canonical_name AS property, pd.category,
               m.value_num, m.value_text, m.unit_normalized, m.unit_raw,
               m.method_raw, m.qa_status, a.artifact_type, a.source_path AS evidence_path,
               m.evidence_locator
        FROM measurement m
        JOIN site s ON s.site_id=m.site_id
        LEFT JOIN profile p ON p.profile_id=m.profile_id
        LEFT JOIN horizon h ON h.horizon_id=m.horizon_id
        JOIN property_definition pd ON pd.property_id=m.property_id
        JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id
        JOIN document d ON d.document_id=a.document_id
        WHERE m.qa_status='flagged'
          AND m.evidence_locator LIKE '%document_single_reported_coordinate%'
        ORDER BY d.document_id, m.measurement_id
    """,
    "regional_context_table_measurements.csv": """
        SELECT m.measurement_id, 'regional_context_single_geocoded_district' AS analysis_tier,
               d.corpus, d.document_id, d.title, d.doi, s.site_id, s.name AS site_name,
               s.region, s.latitude, s.longitude, s.spatial_precision_m, s.spatial_confidence,
               p.profile_label, h.horizon_label, h.depth_top_cm, h.depth_bottom_cm,
               pd.property_id, pd.canonical_name AS property, pd.category,
               m.value_num, m.value_text, m.unit_normalized, m.unit_raw,
               m.method_raw, m.qa_status, a.artifact_type, a.source_path AS evidence_path,
               m.evidence_locator
        FROM measurement m
        JOIN site s ON s.site_id=m.site_id
        LEFT JOIN profile p ON p.profile_id=m.profile_id
        LEFT JOIN horizon h ON h.horizon_id=m.horizon_id
        JOIN property_definition pd ON pd.property_id=m.property_id
        JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id
        JOIN document d ON d.document_id=a.document_id
        WHERE m.qa_status='flagged'
          AND m.evidence_locator LIKE '%document_single_geocoded_district%'
        ORDER BY d.document_id, m.measurement_id
    """,
    "sites.csv": """
        SELECT s.*, COUNT(DISTINCT m.measurement_id) AS staged_measurement_count
        FROM site s LEFT JOIN measurement m ON m.site_id=s.site_id
        GROUP BY s.site_id ORDER BY s.spatial_confidence, s.site_id
    """,
    "site_coordinate_candidates.csv": """
        SELECT scc.site_id, scc.candidate_id, scc.link_reason,
               lc.latitude, lc.longitude, lc.precision_hint, lc.status AS candidate_status,
               lc.context_text, d.corpus, d.document_id, d.doi, d.title,
               a.source_path AS evidence_path
        FROM site_coordinate_candidate scc
        JOIN location_candidate lc ON lc.candidate_id=scc.candidate_id
        JOIN extraction e ON e.extraction_id=lc.extraction_id
        JOIN source_artifact a ON a.artifact_id=e.artifact_id
        JOIN document d ON d.document_id=a.document_id
        ORDER BY d.corpus, d.document_id, scc.site_id, scc.candidate_id
    """,
    "reported_sites.csv": """
        SELECT s.site_id, s.country_code, s.name AS site_name, s.region, s.latitude, s.longitude,
               s.spatial_precision_m, s.spatial_confidence, s.geometry_source,
               GROUP_CONCAT(DISTINCT se.evidence_text) AS coordinate_evidence,
               GROUP_CONCAT(DISTINCT a.artifact_type) AS coordinate_artifact_types,
               GROUP_CONCAT(DISTINCT d.document_id) AS document_ids,
               GROUP_CONCAT(DISTINCT d.doi) AS dois,
               GROUP_CONCAT(DISTINCT d.title) AS titles,
               GROUP_CONCAT(DISTINCT d.publication_year) AS publication_years,
               GROUP_CONCAT(DISTINCT d.corpus) AS corpora,
               COUNT(DISTINCT m.measurement_id) AS staged_measurement_count
        FROM site s
        JOIN site_evidence se ON se.site_id=s.site_id
        JOIN source_artifact a ON a.artifact_id=se.artifact_id
        JOIN document d ON d.document_id=a.document_id
        LEFT JOIN measurement m ON m.site_id=s.site_id
        WHERE s.spatial_confidence IN ('exact','reported')
        GROUP BY s.site_id
        ORDER BY d.corpus, d.publication_year, s.site_id
    """,
    "geocoded_context_sites.csv": """
        SELECT s.site_id, s.country_code, s.name AS place_name, s.region AS geocoder_display_name,
               s.latitude, s.longitude, s.spatial_precision_m, s.spatial_confidence, s.geometry_source,
               se.evidence_text AS location_evidence,
               d.document_id, d.corpus, d.doi, d.title, d.publication_year
        FROM site s
        JOIN site_evidence se ON se.site_id=s.site_id AND se.evidence_kind='location_text'
        JOIN source_artifact a ON a.artifact_id=se.artifact_id
        JOIN document d ON d.document_id=a.document_id
        WHERE s.spatial_confidence='geocoded'
        ORDER BY d.corpus, d.publication_year, s.site_id
    """,
    "profile_descriptions.csv": """
        SELECT p.profile_id, p.site_id, s.latitude, s.longitude, s.spatial_confidence,
               d.corpus, d.document_id, d.title, d.doi, d.publication_year,
               p.profile_label, p.author_soil_type_raw, p.author_profile_formula_raw,
               p.soil_classification, p.classification_system,
               p.land_use, p.notes, pe.evidence_text, a.source_path AS evidence_path
        FROM profile p
        JOIN site s ON s.site_id=p.site_id
        JOIN profile_evidence pe ON pe.profile_id=p.profile_id
        JOIN source_artifact a ON a.artifact_id=pe.artifact_id
        JOIN document d ON d.document_id=a.document_id
        WHERE pe.evidence_kind='profile_description'
          AND s.spatial_confidence IN ('exact','reported')
        ORDER BY d.corpus, d.publication_year, p.profile_id
    """,
    "profile_author_statements.csv": """
        SELECT pas.statement_id, pas.profile_id, p.profile_label, pas.field_name,
               pas.raw_value, pas.review_status, d.corpus, d.document_id, d.title, d.doi,
               a.source_path AS evidence_path, pas.evidence_text, pas.extractor
        FROM profile_author_statement pas
        JOIN profile p ON p.profile_id=pas.profile_id
        JOIN source_artifact a ON a.artifact_id=pas.artifact_id
        JOIN document d ON d.document_id=a.document_id
        ORDER BY d.corpus, d.publication_year, pas.profile_id, pas.field_name
    """,
    "documents.csv": """
        WITH artifact_counts AS (
                 SELECT document_id, COUNT(*) AS artifact_count
                 FROM source_artifact GROUP BY document_id
             ),
             table_counts AS (
                 SELECT a.document_id, COUNT(*) AS table_candidate_count
                 FROM table_measurement_candidate tm
                 JOIN source_artifact a ON a.artifact_id=tm.artifact_id
                 GROUP BY a.document_id
             ),
             prose_counts AS (
                 SELECT a.document_id, COUNT(*) AS prose_candidate_count
                 FROM measurement_candidate mc
                 JOIN extraction e ON e.extraction_id=mc.extraction_id
                 JOIN source_artifact a ON a.artifact_id=e.artifact_id
                 GROUP BY a.document_id
             )
        SELECT d.*, COALESCE(ac.artifact_count, 0) AS artifact_count,
               COALESCE(tc.table_candidate_count, 0) AS table_candidate_count,
               COALESCE(pc.prose_candidate_count, 0) AS prose_candidate_count
        FROM document d
        LEFT JOIN artifact_counts ac ON ac.document_id=d.document_id
        LEFT JOIN table_counts tc ON tc.document_id=d.document_id
        LEFT JOIN prose_counts pc ON pc.document_id=d.document_id
        ORDER BY d.corpus, d.document_id
    """,
    "corpus_coverage.csv": """
        SELECT d.corpus,
               COUNT(*) AS documents_total,
               SUM(CASE WHEN EXISTS (
                   SELECT 1 FROM source_artifact a WHERE a.document_id=d.document_id AND a.artifact_type='text'
               ) THEN 1 ELSE 0 END) AS documents_with_fulltext,
               SUM(CASE WHEN EXISTS (
                   SELECT 1 FROM source_artifact a WHERE a.document_id=d.document_id AND a.artifact_type='ocr_markdown'
               ) THEN 1 ELSE 0 END) AS documents_with_ocr_tables,
               SUM(CASE WHEN EXISTS (
                   SELECT 1 FROM source_artifact a WHERE a.document_id=d.document_id AND a.artifact_type='pdf'
               ) THEN 1 ELSE 0 END) AS documents_with_registered_pdf
        FROM document d GROUP BY d.corpus ORDER BY d.corpus
    """,
    "properties.csv": "SELECT * FROM property_definition ORDER BY category, property_id",
    "prose_candidates_for_review.csv": """
        SELECT v.*, n.value_normalized, n.unit_normalized, n.normalization_status, n.warning
        FROM v_measurement_candidate_provenance v
        LEFT JOIN measurement_candidate_normalization n ON n.candidate_id=v.candidate_id
        WHERE v.status='unreviewed'
        ORDER BY v.corpus, v.document_id, v.candidate_id
    """,
    "ocr_table_candidates_for_review.csv": """
        SELECT t.candidate_id, d.corpus, d.document_id, d.title, d.doi,
               a.source_path AS evidence_path, ha.source_path AS header_evidence_path,
               hl.linkage_rule AS header_value_linkage_rule, a.page_start, a.page_end, a.table_label,
               t.row_index, t.column_index, pd.canonical_name AS property, pd.category,
               t.property_header_raw, t.value_num, t.value_text, t.unit_raw,
               t.row_label_raw, t.horizon_label, t.depth_top_cm, t.depth_bottom_cm, t.status
        FROM table_measurement_candidate t
        JOIN source_artifact a ON a.artifact_id=t.artifact_id
        LEFT JOIN table_candidate_header_link hl ON hl.candidate_id=t.candidate_id
        LEFT JOIN source_artifact ha ON ha.artifact_id=hl.header_artifact_id
        JOIN document d ON d.document_id=a.document_id
        LEFT JOIN property_definition pd ON pd.property_id=t.property_id
        WHERE t.status='unreviewed'
        ORDER BY d.document_id, t.artifact_id, t.row_index, t.column_index
    """,
    "normalized_table_measurement_candidates.csv": """
        SELECT t.candidate_id, d.corpus, d.document_id, d.doi, d.publication_year,
               a.source_path AS evidence_path, ha.source_path AS header_evidence_path,
               hl.linkage_rule AS header_value_linkage_rule, a.page_start, a.page_end, a.table_label,
               t.row_index, t.column_index, pd.property_id, pd.canonical_name AS property,
               pd.category, pd.canonical_unit, t.property_header_raw, t.value_num,
               t.value_text, t.unit_raw, n.value_normalized, n.unit_normalized,
               n.normalization_status, n.warning, t.row_label_raw, t.horizon_label,
               t.depth_top_cm, t.depth_bottom_cm, t.status AS candidate_status
        FROM table_measurement_candidate t
        JOIN table_measurement_candidate_normalization n ON n.candidate_id=t.candidate_id
        JOIN property_definition pd ON pd.property_id=t.property_id
        JOIN source_artifact a ON a.artifact_id=t.artifact_id
        LEFT JOIN table_candidate_header_link hl ON hl.candidate_id=t.candidate_id
        LEFT JOIN source_artifact ha ON ha.artifact_id=hl.header_artifact_id
        JOIN document d ON d.document_id=a.document_id
        ORDER BY d.corpus, d.document_id, a.artifact_id, t.row_index, t.column_index
    """,
    "explicit_coordinate_table_review.csv": """
        WITH reported_sites AS (
          SELECT d.document_id, COUNT(DISTINCT se.site_id) AS reported_site_count,
                 GROUP_CONCAT(DISTINCT printf('%.6f,%.6f', s.latitude, s.longitude)) AS reported_coordinates
          FROM document d
          JOIN source_artifact evidence ON evidence.document_id=d.document_id
          JOIN site_evidence se ON se.artifact_id=evidence.artifact_id
          JOIN site s ON s.site_id=se.site_id
          WHERE s.spatial_confidence IN ('exact','reported')
          GROUP BY d.document_id
        )
        SELECT t.candidate_id, d.document_id, d.title, d.doi,
               reported_sites.reported_site_count, reported_sites.reported_coordinates,
               CASE WHEN reported_sites.reported_site_count=1 THEN 'check_unit_or_plausibility'
                    ELSE 'multi_site_requires_row_to_coordinate_link' END AS review_reason,
               a.source_path AS evidence_path, t.row_index, t.column_index,
               pd.canonical_name AS property, t.property_header_raw, t.value_num, t.unit_raw,
               t.row_label_raw, t.horizon_label, t.depth_top_cm, t.depth_bottom_cm
        FROM table_measurement_candidate t
        JOIN source_artifact a ON a.artifact_id=t.artifact_id
        JOIN document d ON d.document_id=a.document_id
        JOIN reported_sites ON reported_sites.document_id=d.document_id
        LEFT JOIN property_definition pd ON pd.property_id=t.property_id
        WHERE t.status='unreviewed'
        ORDER BY reported_sites.reported_site_count DESC, d.document_id, t.artifact_id, t.row_index, t.column_index
    """,
}

DOCUMENT_AUTHOR_CANDIDATES_QUERY = """
    SELECT c.candidate_id, c.field_name, c.profile_label_raw, c.raw_value,
           c.linkable, c.link_status, d.corpus, d.document_id, d.title, d.doi,
           a.source_path AS evidence_path, c.evidence_text, c.extractor
    FROM document_author_statement_candidate c
    JOIN document d ON d.document_id=c.document_id
    JOIN source_artifact a ON a.artifact_id=c.artifact_id
    ORDER BY c.linkable DESC, d.corpus, d.publication_year, c.candidate_id
"""


README = """# Russian Soil Observatory — analysis package

Generated from the provenance database at `{database}` on `{generated_at}`.

## Which table to analyse

`supported_table_measurements.csv` is the usable starting layer.  Each row
has a numeric value, recognized/normalized unit, explicit Russian coordinate,
and a source table cell.  Its `analysis_tier` is
`supported_document_single_reported_coordinate`: the document has exactly one
explicitly reported Russian coordinate, but the coordinate is not printed in
the same table row.  Treat it as a distinct quality tier; do not mix it with
row-level verified data without a sensitivity check.

`verified_measurements.csv` contains only values with a direct row/sample to
coordinate proof.  It may legitimately be empty in this release.

`reported_sites.csv` is the operational point inventory: every row has an
exact or author-reported Russian coordinate.  `sites.csv` is deliberately
broader provenance inventory and also retains `geocoded` regional contexts
and `unverified` quarantined candidates.  Never use those latter rows as
sampling points.  The `v_ready_measurements` view excludes both classes by
contract.

`profile_descriptions.csv` is a separate descriptive layer.  Each row has an
explicit profile/pit/section/horizon statement in article prose and a unique
reported coordinate in the same document.  It is not itself a measured horizon
or proof that the coordinate belongs to every profile mentioned by the paper.

`profile_author_statements.csv` contains only literal author statements for a
coordinate-linked profile: the reported soil type and/or the complete
morphological-profile formula.  It is not a normalized classification; its
evidence excerpt and source path are retained for review.

`document_author_statement_candidates.csv` is the broader discovery layer:
literal types and profile-formulae found in primary text before a profile link
is proven.  `linkable=1` means that the article prints a nearby preceding pit
label; it is still not an operational profile claim until the link has been
reviewed.  Never treat these rows as a taxonomic assignment to a point.

`regional_context_table_measurements.csv` has a single geocoded district or
settlement for the document and no reported point.  It is valuable for regional
coverage and discovery, but its latitude/longitude is *not* a sampling point;
do not use it in point-scale spatial statistics.

`explicit_coordinate_table_review.csv` is the short, high-value remainder
from papers that do report coordinates.  It is separate from the 44k general
OCR candidates: entries either lack a trustworthy unit/plausibility result or
come from a multi-site paper and need a row-to-coordinate proof.

`ocr_table_candidates_for_review.csv` and `prose_candidates_for_review.csv`
are evidence-backed staging layers, not point observations.  They are kept so
the database can grow without losing any extraction result.  Never infer a
coordinate for them from a paper title or journal.

`full_table_observations.csv` is the complete header-grounded table layer.
Every row preserves its OCR-cell locator and source artifact.  Its
`spatial_linkage` is explicit: it may be no coordinate, document-only context,
or a verified row/profile link.  `unit_missing` and `unit_incompatible` are
retained QA states, not dropped values or guessed units.

## Provenance and spatial rules

- `evidence_path` and `evidence_locator` lead back to the exact OCR artifact,
  table row and column.
- Only Russian sites are present in `sites.csv`.
- `spatial_confidence=reported/exact` is distinct from `geocoded`; district
  centroids are never used by `supported_table_measurements.csv`.
- Original and translated papers remain separate `document_id` rows.

## Files

- `manifest.json` — row counts, audit result and SHA-256 checksums.
- `sites.csv`, `documents.csv`, `properties.csv` — reference dimensions.
- `parse_issues.jsonl` — texts deliberately held for separate parsing after a
  per-document deadline; they were not silently discarded.

The authoritative SQLite database remains at `{database}`; it retains the
full OCR-cell and source-artifact lineage that is intentionally not duplicated
into this compact package.
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--table-observation-audit", type=Path)
    parser.add_argument("--parse-issues", type=Path)
    args = parser.parse_args()

    audit = json.loads(args.audit.read_text(encoding="utf-8"))
    if not audit.get("ready"):
        raise SystemExit("Refusing export: database audit is not clean.")
    args.output.mkdir(parents=True, exist_ok=True)
    table_observation_audit = None
    if args.table_observation_audit:
        table_observation_audit = json.loads(args.table_observation_audit.read_text(encoding="utf-8"))
        if not table_observation_audit.get("ready"):
            raise SystemExit("Refusing export: complete table-observation audit is not clean.")
    with sqlite3.connect(args.db) as con:
        con.row_factory = sqlite3.Row
        # `site_coordinate_candidate` was an intermediate linkage table in
        # earlier snapshots.  The delivery schema now keeps only promoted
        # provenance links in `site_evidence`, so omit that optional review
        # export when opening a newer database.
        has_site_coordinate_candidates = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='site_coordinate_candidate'"
        ).fetchone()
        counts = {
            name: export_query(con, args.output / name, query)
            for name, query in QUERIES.items()
            if name != "site_coordinate_candidates.csv" or has_site_coordinate_candidates
        }
        has_discovery = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_author_statement_candidate'"
        ).fetchone()
        if has_discovery:
            counts["document_author_statement_candidates.csv"] = export_query(
                con, args.output / "document_author_statement_candidates.csv", DOCUMENT_AUTHOR_CANDIDATES_QUERY
            )
    if args.parse_issues and args.parse_issues.exists():
        shutil.copyfile(args.parse_issues, args.output / "parse_issues.jsonl")
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    (args.output / "README.md").write_text(
        README.format(database=args.db.resolve(), generated_at=generated_at), encoding="utf-8"
    )
    manifest = {
        "generated_at": generated_at,
        "database": str(args.db.resolve()),
        "audit": audit,
        "full_table_observation_audit": table_observation_audit,
        "row_counts": counts,
        # A manifest cannot checksum itself: writing its checksum changes its
        # own bytes.  Every payload file is covered; the archive checksum
        # covers the manifest as well.
        "files": {p.name: {"bytes": p.stat().st_size, "sha256": sha256(p)} for p in sorted(args.output.iterdir()) if p.is_file() and p.name != "manifest.json"},
    }
    (args.output / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "row_counts": counts, "audit_ready": audit["ready"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
