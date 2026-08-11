#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build the conservative, reproducible report and GitHub Pages data layer.

Only the strict operational layer is analysed: an explicitly written coordinate
inside Russia, one reported coordinate in the document, a soil-context table,
and a numeric value re-checked against the source OCR cell.  A table cell is
not treated as an independent field replicate.
"""
from __future__ import annotations

import json
import math
import html
import re
import hashlib
import sys
from datetime import date
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# The report is also invoked from the repository root.  Pin this sibling
# module explicitly so an unrelated module on PYTHONPATH cannot supply an
# older property vocabulary.
sys.path.insert(0, str(Path(__file__).resolve().parent))
from property_dictionary_ru import CATEGORY_RU, RU

# Keep the release build compatible with delivery snapshots that introduced
# these canonical identifiers after the first publication dictionary.
RU.update({
    "ph_unspecified": "pH (экстрагент не указан автором)",
    "phosphorus_pentoxide": "пентаоксид фосфора (P₂O₅)",
    "potassium_oxide": "оксид калия (K₂O)",
    "exchangeable_calcium": "обменный кальций",
    "exchangeable_magnesium": "обменный магний",
    "calcium_ion_activity_paste": "активность ионов кальция в почвенной пасте",
})

DOCS = Path(__file__).resolve().parents[1]
DATA, TABLES, ASSETS = DOCS / "data", DOCS / "tables", DOCS / "assets"
plt.rcParams.update({"figure.dpi": 150, "savefig.dpi": 180, "font.size": 10,
                     "axes.spines.top": False, "axes.spines.right": False})


def russian_build_date() -> str:
    months = ("января", "февраля", "марта", "апреля", "мая", "июня",
              "июля", "августа", "сентября", "октября", "ноября", "декабря")
    today = date.today()
    return f"{today.day} {months[today.month - 1]} {today.year} г."


def safe(x):
    if isinstance(x, dict): return {str(k): safe(v) for k, v in x.items()}
    if isinstance(x, list): return [safe(v) for v in x]
    if isinstance(x, (np.integer,)): return int(x)
    if isinstance(x, (np.floating, float)): return None if not math.isfinite(x) else float(x)
    return None if pd.isna(x) else x


def csv_out(frame, filename):
    TABLES.mkdir(exist_ok=True)
    frame.to_csv(TABLES / filename, index=False, encoding="utf-8")


def property_dictionary_and_normalized_measurements(x):
    """Publish one canonical unit per property, with Russian annotations."""
    props = pd.read_csv(DATA / "properties.csv")
    # The operational exporter ships a complete release-specific Russian
    # vocabulary.  Prefer the maintained publication dictionary, then fall
    # back to it for identifiers added in later database snapshots.
    release_labels = pd.read_csv(DATA / "property_dictionary_ru.csv")
    release_label_map = release_labels.set_index("property_id")["property_ru"].to_dict()
    props["property_russian"] = props.property_id.map(RU).fillna(props.property_id.map(release_label_map))
    props["category_russian"] = props.category.map(CATEGORY_RU)
    missing = props[props.property_russian.isna() | props.category_russian.isna()]
    if not missing.empty:
        detail = missing[["property_id", "category"]].to_dict("records")
        raise ValueError(f"Russian property dictionary incomplete: {detail}")
    props["unit_rule"] = props.canonical_unit.map(
        lambda u: "Значения приводятся к этой единице только обратимыми размерностно корректными преобразованиями; исходная единица сохраняется."
        if pd.notna(u) else "Единица зависит от методики; автоматическое приведение не выполняется."
    )
    props = props[["property_id", "property_russian", "canonical_name", "category_russian", "category", "canonical_unit", "unit_rule", "description"]]
    # Preserve the provenance-exported dictionary (covered by manifest.json)
    # and publish the portal-specific presentation table separately.
    props.to_csv(DATA / "property_dictionary_ru_public.csv", index=False, encoding="utf-8")
    lines = ["# Словарь свойств и канонических единиц", "", "Этот словарь задаёт единственную публикуемую единицу для каждого свойства. Исходное значение и исходная единица всегда сохраняются в `normalized_measurements.csv`; автоматическая конверсия допустима только для размерностно совместимых единиц.", "", "| Код | Свойство (рус.) | Каноническая единица | Категория |", "|---|---|---|---|"]
    for r in props.itertuples(index=False):
        lines.append(f"| `{r.property_id}` | {r.property_russian} | {r.canonical_unit if pd.notna(r.canonical_unit) else 'зависит от методики'} | {r.category_russian} |")
    (DOCS / "property_units.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rows_html = "".join(
        f"<tr><td><code>{html.escape(str(r.property_id))}</code></td><td>{html.escape(str(r.property_russian))}</td><td>{html.escape(str(r.canonical_unit if pd.notna(r.canonical_unit) else 'зависит от методики'))}</td><td>{html.escape(str(r.category_russian))}</td></tr>"
        for r in props.itertuples(index=False)
    )
    note_html = """<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Словарь свойств и единиц</title><style>body{max-width:1100px;margin:2rem auto;padding:0 1rem;font:16px/1.5 system-ui,sans-serif;color:#172033}table{border-collapse:collapse;width:100%}th,td{border:1px solid #d8e0e8;padding:.45rem;text-align:left;vertical-align:top}th{background:#f1f5f9}code{font-size:.85em}a{color:#075985}</style></head><body><p><a href=\"index.html\">← Геопортал</a> · <a href=\"property_units.md\">Markdown</a></p><h1>Словарь свойств и канонических единиц</h1><p>Исходная единица и значение сохраняются в нормализованной таблице. Преобразование допускается только для размерностно совместимых единиц; если это невозможно, ячейка остаётся в очереди ручного разбора.</p><table><thead><tr><th>Код</th><th>Свойство</th><th>Каноническая единица</th><th>Категория</th></tr></thead><tbody>""" + rows_html + "</tbody></table></body></html>"
    (DOCS / "property_units.html").write_text(note_html, encoding="utf-8")

    by_name = props.set_index("canonical_name")
    out = x.copy()
    out["property_russian"] = out.property.map(by_name.property_russian)
    out["canonical_unit"] = out.property.map(by_name.canonical_unit)
    out["category_russian"] = out.property.map(by_name.category_russian)
    out["normalization_status"] = np.where(
        out.unit_raw.fillna("").str.replace(" ", "", regex=False).eq(out.unit_normalized.fillna("").str.replace(" ", "", regex=False)),
        "source_unit_already_canonical", "converted_or_canonicalized"
    )
    keep = ["measurement_id", "analysis_tier", "corpus", "document_id", "doi", "site_id", "latitude", "longitude",
            "property_id", "property_russian", "property", "category_russian", "category", "value_num", "value_text",
            "unit_raw", "unit_normalized", "canonical_unit", "normalization_status", "qa_status", "profile_label",
            "horizon_label", "depth_top_cm", "depth_bottom_cm", "method_raw", "evidence_path", "evidence_locator"]
    out = out.reindex(columns=keep)
    out.to_csv(DATA / "normalized_measurements.csv", index=False, encoding="utf-8")
    return props, out


def load():
    flagged = pd.read_csv(DATA / "supported_table_measurements.csv")
    accepted = pd.read_csv(DATA / "verified_measurements.csv")
    if not accepted.empty:
        documents = pd.read_csv(DATA / "documents.csv")[["document_id", "doi", "title", "publication_year"]]
        accepted = accepted.merge(documents, on="document_id", how="left", suffixes=("", "_catalog"))
        accepted["title"] = accepted.get("title_catalog", accepted.get("title"))
        accepted["qa_status"] = "accepted"
        accepted["artifact_type"] = "text"
        property_ids = pd.read_csv(DATA / "properties.csv").set_index("canonical_name")["property_id"]
        accepted["property_id"] = accepted["property"].map(property_ids)
        accepted["unit_raw"] = accepted.get("unit_raw")
        accepted["method_raw"] = accepted.get("method_raw")
        accepted["value_text"] = accepted.get("value_text")
        accepted["spatial_precision_m"] = pd.NA
        accepted["region"] = pd.NA
        accepted["profile_label"] = accepted.get("profile_label")
        accepted["horizon_label"] = accepted.get("horizon_label")
        accepted["evidence_path"] = accepted.get("evidence_path")
    x = pd.concat([flagged, accepted], ignore_index=True, sort=False)
    def evidence(value):
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {"raw": value}
        except (TypeError, json.JSONDecodeError):
            return {"raw": value, "direct_prose_evidence": True}
    x["evidence"] = x.evidence_locator.map(evidence)
    x["row_label"] = x.evidence.map(lambda d: d.get("row_label"))
    # The export has an empty placeholder title; Crossref is the bibliographic
    # source of truth, so avoid pandas' title_x/title_y ambiguity.
    x = x.drop(columns=[c for c in ["title", "publication_year"] if c in x.columns])
    meta = pd.read_csv(DATA / "doi_metadata.csv")
    measurements = x.merge(meta[["doi", "publication_year", "title", "journal", "authors"]], on="doi", how="left")
    coordinates = pd.read_csv(DATA / "reported_sites.csv")
    contexts = pd.read_csv(DATA / "geocoded_context_sites.csv")
    profiles = pd.read_csv(DATA / "profile_descriptions.csv")
    audit_path = DATA / "direct_profile_source_coordinate_audit.csv"
    quarantined_profiles = 0
    direct_profile_audit_rows = 0
    direct_profile_audit_verified = 0
    if audit_path.exists():
        coordinate_audit = pd.read_csv(audit_path)
        direct_profile_audit_rows = len(coordinate_audit)
        direct_profile_audit_verified = int(coordinate_audit.status.eq("verified_source_coordinate").sum())
        unsafe = set(coordinate_audit.loc[
            coordinate_audit.status.ne("verified_source_coordinate"), "profile_id"
        ])
        quarantined_profiles = int(profiles.profile_id.isin(unsafe).sum())
        # A direct link must survive an independent check of the *raw* article
        # block.  Keep the original export and the audit CSV, but do not show a
        # failed link in a public map as if it were a verified field location.
        profiles = profiles.loc[~profiles.profile_id.isin(unsafe)].copy()
    profiles.attrs["quarantined_source_coordinate_links"] = quarantined_profiles
    profiles.attrs["direct_profile_audit_rows"] = direct_profile_audit_rows
    profiles.attrs["direct_profile_audit_verified"] = direct_profile_audit_verified
    full_inventory = pd.read_csv(DATA / "full_table_property_inventory.csv")
    full_inventory_meta = json.loads((DATA / "full_table_property_inventory_meta.json").read_text(encoding="utf-8"))
    full_inventory_spatial = pd.read_csv(DATA / "full_table_property_spatial_linkage.csv")
    return measurements, coordinates, meta, contexts, profiles, full_inventory, full_inventory_meta, full_inventory_spatial


def temporal_register(frame):
    # Curated after reading temporal_evidence.csv: all source dates are retained
    # there; this compact register carries only dates that describe the study data.
    rows = [
        ["10.1134/S1064229322060096", 2022, "not reported", None, None,
         "The article reports an experiment, but the extracted text does not state a field sampling/monitoring interval tied to the staged pH table."],
        ["10.1134/S1064229323601130", 2023, "monitoring interval", 1998, 2022,
         "Text explicitly states field observations and meteorological analysis for 1998–2022 (n=25); 1997–2015 is also discussed as an earlier 18-year segment."],
        ["10.1134/S106422932460074X", 2024, "discrete sampling campaigns", 2021, 2022,
         "Text names a winter 2021 sample, a summer 2022 sample and a winter 2022 sample; it also gives older site-construction years, which are not sampling dates."],
        ["10.1134/S1064229324604529", 2025, "paleochronological context", None, None,
         "The source discusses radiocarbon dating and Late Glacial interpretation. Its numerical chronology is not assigned to the staged pH cells, so it is not combined with monitoring time."],
        ["10.1134/S106422932560304X", 2026, "not reported", None, None,
         "The text describes samples and depths; no sampling/monitoring year tied to the staged clay values was found."],
    ]
    curated = pd.DataFrame(rows, columns=["doi", "publication_year", "temporal_semantics", "observation_start_year", "observation_end_year", "source_evidence"])
    evidence = pd.read_csv(DATA / "temporal_evidence.csv")
    evidence_counts = evidence.groupby("document_id").agg(
        extracted_date_snippets=("date_text", "size"),
        field_or_monitoring_candidates=("date_type", lambda s: int((s == "field_or_monitoring").sum())),
        paleochronology_candidates=("date_type", lambda s: int((s == "paleochronology").sum())),
    ).reset_index()
    out = frame[["doi", "document_id", "site_id"]].drop_duplicates().merge(curated, on="doi", how="left").merge(evidence_counts, on="document_id", how="left")
    out["temporal_review_status"] = np.where(out.temporal_semantics.notna(), "contextually curated", "dates extracted; interpretation pending contextual review")
    out["temporal_semantics"] = out.temporal_semantics.fillna("not curated")
    out["extracted_date_snippets"] = out.extracted_date_snippets.fillna(0).astype(int)
    out["field_or_monitoring_candidates"] = out.field_or_monitoring_candidates.fillna(0).astype(int)
    out["paleochronology_candidates"] = out.paleochronology_candidates.fillna(0).astype(int)
    csv_out(out, "temporal_register.csv")
    return out


def summaries(x, coordinates):
    summary = x.groupby(["property", "unit_normalized"], dropna=False).agg(
        table_cells=("value_num", "size"), sites=("site_id", "nunique"), documents=("document_id", "nunique"),
        minimum=("value_num", "min"), q25=("value_num", lambda v: v.quantile(.25)),
        median=("value_num", "median"), mean=("value_num", "mean"), q75=("value_num", lambda v: v.quantile(.75)), maximum=("value_num", "max"),
    ).reset_index().sort_values("property")
    csv_out(summary, "point_property_summary.csv")
    sites = x.groupby(["site_id", "site_name", "latitude", "longitude", "doi", "title", "publication_year"], dropna=False).agg(
        observations=("measurement_id", "size"), properties=("property", lambda s: "; ".join(sorted(set(s))))
    ).reset_index().sort_values(["latitude", "longitude"])
    csv_out(sites, "site_summary.csv")
    publication = sites.groupby("publication_year").size().reset_index(name="documents").sort_values("publication_year")
    csv_out(publication, "publication_timeline.csv")
    spatial = pd.DataFrame([{
        "analysis_tier": "all_reported_coordinate_records",
        "coordinate_records": len(coordinates), "unique_coordinate_locations": coordinates[["latitude", "longitude"]].drop_duplicates().shape[0],
        "documents": coordinates.document_ids.str.split(";").explode().nunique(),
        "lat_min": coordinates.latitude.min(), "lat_max": coordinates.latitude.max(),
        "lon_min": coordinates.longitude.min(), "lon_max": coordinates.longitude.max(),
        "detailed_measurement_sites": x.site_id.nunique(), "detailed_measurements": len(x),
        "note": "All records are explicit reported points; only the detailed subset has table-cell values.",
    }])
    csv_out(spatial, "spatial_coverage_summary.csv")
    return summary, sites


def spatial_statistics(coordinates):
    """Descriptive spacing only; source points are not an area sample."""
    coord = coordinates.copy()
    coord["corpus"] = coord.corpora.str.split(";").str[0]
    by_corpus = coord.groupby("corpus").agg(
        coordinate_records=("site_id", "size"),
        unique_coordinate_locations=("site_id", "size"),
        source_documents=("document_ids", lambda s: s.str.split(";").explode().nunique()),
        min_latitude=("latitude", "min"), max_latitude=("latitude", "max"),
        min_longitude=("longitude", "min"), max_longitude=("longitude", "max"),
        with_staged_values=("staged_measurement_count", lambda s: int((s > 0).sum())),
    ).reset_index()
    # Recalculate unique locations inside each corpus rather than calling a
    # coordinate record a unique sample.
    by_corpus["unique_coordinate_locations"] = [
        coord.loc[coord.corpus.eq(c), ["latitude", "longitude"]].drop_duplicates().shape[0]
        for c in by_corpus.corpus
    ]
    csv_out(by_corpus, "spatial_source_coverage.csv")

    unique = coord[["latitude", "longitude"]].drop_duplicates().to_numpy(dtype=float)
    lat, lon = np.radians(unique[:, 0]), np.radians(unique[:, 1])
    dlat, dlon = lat[:, None] - lat, lon[:, None] - lon
    distance = 2 * 6371.0088 * np.arcsin(np.sqrt(np.sin(dlat / 2) ** 2 + np.cos(lat[:, None]) * np.cos(lat) * np.sin(dlon / 2) ** 2))
    np.fill_diagonal(distance, np.inf)
    nearest = distance.min(axis=1)
    spacing = pd.DataFrame([{
        "statistic": "nearest-neighbour distance among unique reported coordinate locations",
        "unit": "km", "n_unique_locations": len(unique),
        "minimum": nearest.min(), "q25": np.quantile(nearest, .25), "median": np.median(nearest),
        "q75": np.quantile(nearest, .75), "q90": np.quantile(nearest, .9), "maximum": nearest.max(),
        "locations_under_1_km": int((nearest < 1).sum()), "locations_under_10_km": int((nearest < 10).sum()),
        "locations_over_100_km": int((nearest > 100).sum()),
        "interpretation": "descriptive only; clustering can reflect multi-point study design, not soil-process autocorrelation",
    }])
    csv_out(spacing, "nearest_neighbour_summary.csv")
    return by_corpus, spacing, nearest


def potential_reuse(x):
    """Flag exact table vectors at the same coordinate, never silently dedupe."""
    records = []
    for (document_id, latitude, longitude, prop), group in x.groupby(["document_id", "latitude", "longitude", "property"], dropna=False):
        vector = "|".join(
            f"{r.row_label or ''}:{float(r.value_num):.10g}" for r in group.sort_values(["row_label", "value_num"], na_position="last").itertuples()
        )
        key = f"{float(latitude):.8f}|{float(longitude):.8f}|{prop}|{vector}"
        records.append({"fingerprint": hashlib.sha1(key.encode()).hexdigest(), "document_id": document_id,
                        "doi": group.doi.iloc[0], "title": group.title.iloc[0], "latitude": latitude, "longitude": longitude,
                        "property": prop, "n_values": len(group), "value_vector": vector})
    all_vectors = pd.DataFrame(records)
    repeated = all_vectors[all_vectors.fingerprint.duplicated(keep=False)].sort_values(["fingerprint", "document_id"])
    csv_out(repeated, "potential_reused_observation_vectors.csv")
    return repeated


def within_profile_depth_statistics(x):
    """Describe depth sequences inside a source, never pool them nationally."""
    depth = x[(x.property.eq("pH in water")) & x.depth_top_cm.notna()].copy()
    depth["mid_depth_cm"] = (depth.depth_top_cm + depth.depth_bottom_cm) / 2
    rows = []
    for (doi, site_id), g in depth.groupby(["doi", "site_id"], dropna=False):
        if len(g) < 4:
            continue
        g = g.sort_values("mid_depth_cm")
        # Rank correlation is deliberately descriptive: it quantifies the
        # monotonic within-source pattern but has no cross-study p-value.
        rho = g.mid_depth_cm.rank().corr(g.value_num.rank(), method="pearson")
        rows.append({"doi": doi, "site_id": site_id, "n_horizons": len(g),
                     "depth_min_cm": g.depth_top_cm.min(), "depth_max_cm": g.depth_bottom_cm.max(),
                     "shallowest_ph": g.value_num.iloc[0], "deepest_ph": g.value_num.iloc[-1],
                     "change_deep_minus_shallow": g.value_num.iloc[-1] - g.value_num.iloc[0],
                     "spearman_rho_depth_ph": rho,
                     "interpretation": "Within-source descriptive sequence; not pooled or inferential."})
    out = pd.DataFrame(rows)
    csv_out(out, "within_profile_depth_summary.csv")
    return depth, out


def regional_context_statistics(contexts):
    grouped = contexts.groupby("corpus").agg(
        geocoded_context_records=("site_id", "size"),
        unique_centroids=("site_id", lambda s: 0),
        source_documents=("document_id", "nunique"),
        median_precision_m=("spatial_precision_m", "median"),
        q25_precision_m=("spatial_precision_m", lambda s: s.quantile(.25)),
        q75_precision_m=("spatial_precision_m", lambda s: s.quantile(.75)),
    ).reset_index()
    grouped["unique_centroids"] = [
        contexts.loc[contexts.corpus.eq(c), ["latitude", "longitude"]].drop_duplicates().shape[0]
        for c in grouped.corpus
    ]
    csv_out(grouped, "regional_context_coverage.csv")
    return grouped


def profile_descriptor_statistics(profiles):
    """Count source wording only; never silently classify soil taxonomy."""
    def counts(column, label):
        values = profiles[column].dropna().astype(str).str.strip()
        values = values[values.ne("")]
        return values.str.casefold().value_counts().rename_axis(label).reset_index(name="descriptions")
    soil = counts("soil_classification", "soil_classification_raw")
    land = counts("land_use", "land_use_raw")
    combined = pd.concat([
        soil.assign(descriptor_kind="soil_classification_raw").rename(columns={"soil_classification_raw": "descriptor"}),
        land.assign(descriptor_kind="land_use_raw").rename(columns={"land_use_raw": "descriptor"}),
    ], ignore_index=True)[["descriptor_kind", "descriptor", "descriptions"]]
    csv_out(combined.sort_values(["descriptor_kind", "descriptions", "descriptor"], ascending=[True, False, True]),
            "profile_descriptor_summary.csv")
    return soil, land


def readiness_summary(coordinates, contexts, profiles, measurements):
    """A release inventory: evidence-backed layers are never conflated with queues."""
    audit = json.loads((DATA / "audit_final.json").read_text(encoding="utf-8"))
    counts = audit.get("counts", {})
    manifest = json.loads((DATA / "manifest.json").read_text(encoding="utf-8"))
    exported = manifest.get("row_counts", {})
    table_observation_audit = {}
    full_audit_path = DATA / "full_table_observation_audit.json"
    if full_audit_path.exists():
        table_observation_audit = json.loads(full_audit_path.read_text(encoding="utf-8"))
    rows = [
        ("documents", counts.get("document"), "Source documents registered in provenance database"),
        ("reported_coordinate_records", len(coordinates), "Explicit coordinates in sources, country-validated as Russia"),
        ("unique_reported_coordinate_locations", coordinates[["latitude", "longitude"]].drop_duplicates().shape[0], "Map markers after identical-coordinate grouping"),
        ("descriptive_profiles", len(profiles), "Explicit profile/pit/section/horizon prose linked at document level"),
        ("operational_measurements", len(measurements), "Numeric rows in the strict analysis layer"),
        ("prose_measurement_candidates_pending", exported.get("prose_candidates_for_review.csv", counts.get("measurement_candidate")), "Evidence queue; no coordinate link asserted"),
        ("complete_table_observations", table_observation_audit.get("table_observation", exported.get("full_table_observations.csv", counts.get("table_measurement_candidate"))), "All header-grounded OCR table values, each with source-cell provenance and QA/spatial-linkage status"),
        ("table_observations_unit_missing", table_observation_audit.get("qa_status", {}).get("unit_missing", 0), "Values retained; the published table/header did not supply a defensible unit"),
        ("table_observations_unit_incompatible", table_observation_audit.get("qa_status", {}).get("unit_incompatible", 0), "Values retained; source and canonical units are not automatically convertible"),
        ("coordinate_table_candidates_pending", exported.get("explicit_coordinate_table_review.csv"), "High-priority OCR queue from articles that report coordinates"),
        ("geocoded_regional_context_records", len(contexts), "Administrative centroids; not sampling points"),
    ]
    out = pd.DataFrame(rows, columns=["layer", "records", "meaning"])
    csv_out(out, "data_readiness_summary.csv")
    return out


def full_table_inventory_statistics(inventory):
    """Summarise all header-grounded table cells, separate from mapped values."""
    category = inventory.groupby("category", dropna=False).agg(
        recognized_properties=("property", "size"), numeric_cells=("numeric_cells", "sum"),
        ocr_tables=("ocr_tables", "sum"), documents=("documents", "sum"),
        cells_with_source_unit=("cells_with_source_unit", "sum"),
    ).reset_index().sort_values("numeric_cells", ascending=False)
    # Category table counts overlap because a table may contain several kinds
    # of properties; the note makes this non-additivity explicit.
    category["note"] = "Table/document counts overlap across categories; numeric cells are additive."
    csv_out(category, "full_table_category_inventory.csv")
    return category


def full_table_spatial_linkage_statistics(linkage, total_cells):
    out = linkage.groupby("spatial_linkage_tier", dropna=False).agg(
        numeric_cells=("numeric_cells", "sum"), recognized_properties=("property", "nunique")
    ).reset_index()
    out["share_of_all_numeric_cells_percent"] = out.numeric_cells / total_cells * 100
    labels = {
        "document_single_reported_coordinate": "One reported coordinate in document; candidate still needs unit/row review.",
        "document_multiple_reported_coordinates": "Several reported coordinates; table row cannot be automatically assigned to a site.",
        "no_reported_coordinate": "No explicit reported coordinate in source document.",
    }
    out["meaning"] = out.spatial_linkage_tier.map(labels)
    csv_out(out.sort_values("numeric_cells", ascending=False), "full_table_spatial_linkage_summary.csv")
    return out.set_index("spatial_linkage_tier")


def coordinate_source_timeline(coordinates, metadata):
    """Bibliographic dates for the complete coordinate layer, never sampling dates."""
    meta = metadata.set_index("doi").to_dict("index")
    records = []
    for _, row in coordinates.iterrows():
        for doi in str(row.dois or "").split(";"):
            doi = doi.strip()
            if not doi or doi.lower() == "nan":
                # Pochvovedenie records retain their source-side year.
                records.append({"document_id": row.document_ids, "corpus": row.corpora, "doi": None,
                                "publication_year": row.publication_years, "title": row.titles,
                                "date_source": "document catalog"})
            else:
                m = meta.get(doi, {})
                records.append({"document_id": row.document_ids, "corpus": row.corpora, "doi": doi,
                                "publication_year": m.get("publication_year") or row.publication_years,
                                "title": m.get("title") or row.titles, "date_source": m.get("metadata_source", "document catalog")})
    docs = pd.DataFrame(records).drop_duplicates("document_id")
    docs["publication_year"] = pd.to_numeric(docs.publication_year, errors="coerce")
    docs = docs.sort_values(["publication_year", "document_id"], na_position="last")
    csv_out(docs, "coordinate_source_documents.csv")
    timeline = docs.groupby("publication_year", dropna=False).size().reset_index(name="documents")
    csv_out(timeline, "coordinate_source_publication_timeline.csv")
    return docs, timeline


def figures(x, summary, sites, coordinates, coordinate_timeline, contexts, profile_soil, depth_ph, full_inventory):
    ASSETS.mkdir(exist_ok=True)
    # Map-like coordinate scatter. It deliberately has no area interpolation.
    fig, ax = plt.subplots(figsize=(7.4, 5.2))
    ax.scatter(coordinates.longitude, coordinates.latitude, s=18, color="#94a3b8", alpha=.75,
               label="Сообщённая координата без строгого табличного значения")
    context_points = contexts[["latitude", "longitude"]].drop_duplicates()
    ax.scatter(context_points.longitude, context_points.latitude, s=10, marker="+", color="#d97706", alpha=.65,
               label="Геокодированный административный контекст")
    sc = ax.scatter(sites.longitude, sites.latitude, s=sites.observations * 14 + 45,
                    c=sites.publication_year, cmap="viridis", edgecolor="#172554", linewidth=.7)
    ax.set(xlabel="Долгота, °E", ylabel="Широта, °N", title="Подтверждённые координаты исследований (размер = число ячеек)")
    ax.grid(alpha=.2); fig.colorbar(sc, ax=ax, label="Год публикации")
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout(); fig.savefig(ASSETS / "spatial_coverage.png"); plt.close(fig)

    d = summary.sort_values("table_cells")
    fig, ax = plt.subplots(figsize=(8.2, max(3.8, .42 * len(d))))
    ax.barh(d.property, d.table_cells, color="#0f766e")
    ax.set(xlabel="Число верифицированных ячеек", title="Состав операционного слоя по свойствам")
    for y, n in enumerate(d.table_cells): ax.text(n + .2, y, str(int(n)), va="center")
    fig.tight_layout(); fig.savefig(ASSETS / "property_coverage.png"); plt.close(fig)

    pub = sites.groupby("publication_year").size().reset_index(name="documents")
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(pub.publication_year.astype(str), pub.documents, color="#334155")
    ax.set(xlabel="Год публикации (Crossref)", ylabel="Статьи", title="Библиографическое покрытие, не время отбора проб")
    fig.tight_layout(); fig.savefig(ASSETS / "publication_years.png"); plt.close(fig)

    years = coordinate_timeline.dropna(subset=["publication_year"]).copy()
    years["publication_year"] = years.publication_year.astype(int)
    fig, ax = plt.subplots(figsize=(7, 3.5))
    ax.bar(years.publication_year.astype(str), years.documents, color="#475569")
    ax.set(xlabel="Год публикации", ylabel="Число геопривязанных источников", title="Полный координатный слой: библиографическая шкала")
    fig.tight_layout(); fig.savefig(ASSETS / "coordinate_source_publication_years.png"); plt.close(fig)

    # Different physical units must never share one numerical axis.
    property_groups = list(x.groupby(["property", "unit_normalized"], dropna=False))
    fig, axes = plt.subplots(len(property_groups), 1, figsize=(8.4, max(3.2, 2.1 * len(property_groups))), squeeze=False)
    for ax, ((prop, unit), g) in zip(axes[:, 0], property_groups):
        jitter = np.linspace(-.16, .16, len(g)) if len(g) > 1 else [0]
        ax.scatter(g.value_num, jitter, s=36, alpha=.8, color="#0f766e")
        ax.axvline(g.value_num.median(), color="#b45309", lw=1, ls="--")
        ax.set(yticks=[], ylabel="", title=f"{prop} ({unit}) — n={len(g)}")
        ax.grid(axis="x", alpha=.22)
    axes[-1, 0].set_xlabel("Значение в канонической единице свойства")
    fig.suptitle("Верифицированные значения: отдельный масштаб для каждого свойства", y=1.01)
    fig.tight_layout(); fig.savefig(ASSETS / "value_distribution.png"); plt.close(fig)

    # Study-wise pH preserves clustering instead of pooling table cells.
    ph = x[x.property.eq("pH in water")].copy()
    if not ph.empty:
        labels = []
        fig, ax = plt.subplots(figsize=(8.2, max(4, .45 * ph.document_id.nunique() + 1.2)))
        for i, (doc, g) in enumerate(sorted(ph.groupby("document_id"), key=lambda t: t[1].value_num.median())):
            jitter = np.linspace(-.16, .16, len(g)) if len(g) > 1 else [0]
            ax.scatter(g.value_num, np.full(len(g), i) + jitter, color="#0f766e", alpha=.8, s=36)
            ax.plot([g.value_num.min(), g.value_num.max()], [i, i], color="#94a3b8", lw=1)
            doi = g.doi.iloc[0]
            labels.append(str(doi).split("/")[-1][-8:] if pd.notna(doi) else str(doc).split(":")[-1][-12:])
        ax.set(yticks=range(len(labels)), yticklabels=labels, xlabel="pH in water", ylabel="Статья (DOI или ID источника)", title="pH по исследованиям: кластеры не объединены в общую выборку")
        ax.grid(axis="x", alpha=.2); fig.tight_layout(); fig.savefig(ASSETS / "study_ph_distribution.png"); plt.close(fig)

    # A spacing diagnostic that makes spatial clustering visible without
    # pretending the convenience corpus is a random spatial sample.
    _, _, nearest = spatial_statistics(coordinates)
    fig, ax = plt.subplots(figsize=(7, 3.7))
    ax.hist(nearest, bins=np.geomspace(max(nearest.min(), .01), nearest.max(), 18), color="#475569", edgecolor="white")
    ax.axvline(np.median(nearest), color="#0f766e", lw=2, label=f"Медиана: {np.median(nearest):.1f} км")
    ax.set_xscale("log"); ax.set(xlabel="Ближайшая соседняя координата, км (логарифмическая шкала)", ylabel="Число положений", title="Пространственная неоднородность исходных точек")
    ax.legend(frameon=False); fig.tight_layout(); fig.savefig(ASSETS / "nearest_neighbour_distribution.png"); plt.close(fig)

    if not profile_soil.empty:
        top = profile_soil.head(12).sort_values("descriptions")
        fig, ax = plt.subplots(figsize=(7, 4.4))
        ax.barh(top.soil_classification_raw, top.descriptions, color="#7c3aed")
        ax.set(xlabel="Число текстовых описаний", title="Наиболее частые исходные почвенные термины")
        for y, n in enumerate(top.descriptions): ax.text(n + .2, y, str(int(n)), va="center")
        ax.grid(axis="x", alpha=.2); fig.tight_layout(); fig.savefig(ASSETS / "profile_descriptor_coverage.png"); plt.close(fig)

    if not depth_ph.empty:
        fig, ax = plt.subplots(figsize=(7.2, 4.2))
        for doi, g in depth_ph.groupby("doi"):
            g = g.sort_values("mid_depth_cm")
            ax.plot(g.value_num, g.mid_depth_cm, marker="o", lw=1.5, alpha=.85,
                    label=str(doi).split("/")[-1][-8:])
        ax.invert_yaxis()
        ax.set(xlabel="pH in water", ylabel="Глубина середины горизонта, см",
               title="Последовательности pH по глубине внутри источников")
        ax.grid(alpha=.2); ax.legend(title="Суффикс DOI", frameon=False, fontsize=8)
        fig.tight_layout(); fig.savefig(ASSETS / "within_profile_ph_depth.png"); plt.close(fig)

    top = full_inventory.head(20).sort_values("numeric_cells")
    fig, ax = plt.subplots(figsize=(8, 6.2))
    ax.barh(top.property, top.numeric_cells, color="#2563eb")
    ax.set(xlabel="Число числовых OCR-ячеек с распознанным заголовком",
           title="Полный корпус таблиц: 20 наиболее представленных свойств")
    ax.grid(axis="x", alpha=.2)
    fig.tight_layout(); fig.savefig(ASSETS / "full_table_property_coverage.png"); plt.close(fig)


def portal(x, coordinates, metadata, contexts, profiles):
    payload = {"generated_from": "strict operational layer; build_analysis.py",
               "precision_note": "Все точки — координаты, приведённые авторами. Значения есть только в строгом подслое: таблица привязана к единственной сообщённой координате документа, а не к каждой её строке.",
               "sites": []}
    measurements = {sid: group for sid, group in x.groupby("site_id", sort=False)}
    profile_descriptions = {sid: group for sid, group in profiles.groupby("site_id", sort=False)}
    metadata_by_doi = metadata.set_index("doi").to_dict("index")
    # Several sources can cite an identical coordinate.  Group only the map
    # marker, retaining every source record in the popup.
    for (lat, lon), cg in coordinates.groupby(["latitude", "longitude"], sort=True):
        source_records, ms, ps = [], [], []
        for _, sr in cg.iterrows():
            first_doi = next((d.strip() for d in str(sr.dois or "").split(";") if d.strip()), None)
            meta = metadata_by_doi.get(first_doi, {})
            source_records.append(safe({"site_id": sr.site_id, "corpus": sr.corpora,
                                        "document_ids": sr.document_ids, "dois": sr.dois,
                                        "titles": meta.get("title") or sr.titles, "publication_years": meta.get("publication_year") or sr.publication_years,
                                        "coordinate_evidence": sr.coordinate_evidence,
                                        "coordinate_artifact_types": sr.coordinate_artifact_types,
                                        "has_staged_measurements": int(sr.staged_measurement_count)}))
            g = measurements.get(sr.site_id)
            if g is not None:
                for _, r in g.sort_values(["property", "value_num"]).iterrows():
                    ms.append(safe({"property": r.property, "value": r.value_num, "unit": r.unit_normalized,
                                    "row_label": r.row_label, "header": r.evidence.get("header"),
                                    "doi": r.doi, "title": r.title, "publication_year": r.publication_year,
                                    "evidence_path": r.evidence_path, "evidence_locator": r.evidence_locator}))
            pg = profile_descriptions.get(sr.site_id)
            if pg is not None:
                for _, p in pg.iterrows():
                    ps.append(safe({"profile_label": p.profile_label, "soil_classification": p.soil_classification,
                                    "classification_system": p.classification_system, "land_use": p.land_use,
                                    "doi": p.doi, "title": p.title, "evidence": p.evidence_text,
                                    "notes": p.notes}))
        payload["sites"].append(safe({"latitude": lat, "longitude": lon, "coordinate_records": len(cg),
                                       "source_records": source_records, "measurements": ms, "profile_descriptions": ps,
                                       "has_detailed_values": bool(ms)}))
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    (DATA / "portal_data.json").write_text(serialized, encoding="utf-8")

    regional = []
    metadata_by_doi = metadata.set_index("doi").to_dict("index")
    for (lat, lon), group in contexts.groupby(["latitude", "longitude"], sort=True):
        records = []
        for _, r in group.iterrows():
            m = metadata_by_doi.get(r.doi, {}) if isinstance(r.doi, str) else {}
            records.append(safe({"site_id": r.site_id, "place_name": r.place_name, "display_name": r.geocoder_display_name,
                                 "document_id": r.document_id, "corpus": r.corpus, "doi": r.doi,
                                 "title": m.get("title") or r.title, "publication_year": m.get("publication_year") or r.publication_year,
                                 "precision_m": r.spatial_precision_m, "location_evidence": r.location_evidence}))
        regional.append(safe({"latitude": lat, "longitude": lon, "context_records": len(group), "source_records": records}))
    payload["regional_context"] = regional
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)
    (DATA / "portal_data.json").write_text(serialized, encoding="utf-8")
    # `fetch()` from a file:// page is blocked by most browsers.  Publish the
    # identical immutable payload as a JavaScript assignment as well, so a
    # downloaded portal works without a local web server or GitHub Pages.
    (DATA / "portal_data.js").write_text("window.PORTAL_DATA = " + serialized + ";\n", encoding="utf-8")


def report(x, summary, sites, temporal, coordinates, spacing, coordinate_timeline, contexts, reused, profiles, depth_summary, full_inventory, full_categories, full_inventory_meta, full_spatial):
    counts = summary.set_index("property").table_cells.to_dict()
    lat0, lat1, lon0, lon1 = coordinates.latitude.min(), coordinates.latitude.max(), coordinates.longitude.min(), coordinates.longitude.max()
    n_docs = coordinates.document_ids.str.split(";").explode().nunique()
    unique_locations = coordinates[["latitude", "longitude"]].drop_duplicates().shape[0]
    nn = spacing.iloc[0]
    timeline_years = coordinate_timeline.dropna(subset=["publication_year"])
    pub_range = f"{int(timeline_years.publication_year.min())}–{int(timeline_years.publication_year.max())}" if not timeline_years.empty else "не указано"
    verification = json.loads((DATA / "measurement_verification.json").read_text(encoding="utf-8"))
    coverage = pd.read_csv(DATA / "corpus_coverage.csv")
    springer = coverage.loc[coverage.corpus.eq("springer")].iloc[0]
    direct_accepted = int((x.qa_status == "accepted").sum())
    curated_temporal = int((temporal.temporal_review_status == "contextually curated").sum())
    text_coordinate_records = int(coordinates.coordinate_artifact_types.fillna("").str.contains(r"\btext\b").sum())
    ocr_coordinate_records = int(coordinates.coordinate_artifact_types.fillna("").str.contains("ocr_markdown").sum())
    direct_profile_count = int(profiles.notes.fillna("").str.contains(
        "Direct profile-label-to-coordinate|Explicit pit label and author-reported coordinate",
        regex=True,
    ).sum())
    document_profile_count = len(profiles) - direct_profile_count
    quarantined_profile_count = int(profiles.attrs.get("quarantined_source_coordinate_links", 0))
    direct_profile_audit_rows = int(profiles.attrs.get("direct_profile_audit_rows", 0))
    direct_profile_audit_verified = int(profiles.attrs.get("direct_profile_audit_verified", 0))
    direct_profile_audit_clause = (
        f" Все {direct_profile_audit_verified} из {direct_profile_audit_rows} прямых связок прошли повторный аудит по сырому тексту; результаты доступны в [direct_profile_source_coordinate_audit.csv](data/direct_profile_source_coordinate_audit.csv)."
        if direct_profile_audit_rows and direct_profile_audit_verified == direct_profile_audit_rows else ""
    )
    property_sentence = "; ".join(
        f"{prop} — {int(n)}" for prop, n in x.property.value_counts().items()
    )
    report = f"""# Пространственно-временной анализ подтверждённых почвенных наблюдений РФ

**Дата сборки:** {russian_build_date()}  
**Версия слоя:** пространственная витрина и строгий числовой подслой Springer / *Eurasian Soil Science* + «Почвоведение».

## Аннотация

Полная пространственная витрина содержит **{len(coordinates)}** записей явно сообщённых координат из **{n_docs}** документов двух корпусов (*Springer* и «Почвоведение»), что соответствует **{unique_locations}** уникальным положениям. Отдельно доступны **{len(contexts)}** геокодированных административных контекстов (не точки отбора) из {contexts.document_id.nunique()} документов. Для **{len(profiles)}** текстовых описаний разрезов/профилей сохранены классификация, землепользование и фрагмент исходного текста: **{direct_profile_count}** имеют прямую связку «метка разреза ↔ координата» в одном фрагменте, ещё **{document_profile_count}** привязаны к единственной координате статьи только на уровне документа.{direct_profile_audit_clause} {f'Ещё {quarantined_profile_count} прямой линк исключён из отображения до исправления в исходной БД: независимый аудит сырого текста выявил несовпадение координаты; запись и доказательство сохранены в [direct_profile_source_coordinate_audit.csv](data/direct_profile_source_coordinate_audit.csv).' if quarantined_profile_count else ''} Во всём OCR-корпусе заголовочно распознано **{full_inventory_meta['numeric_cells']:,}** числовых ячеек по **{full_inventory_meta['properties']}** свойствам в **{full_inventory_meta['ocr_tables']:,}** таблицах из **{full_inventory_meta['documents']:,}** документов; это инвентарный слой, ещё не пространственная выборка. В строгий пространственный подслой вошли **{len(x)}** числовых наблюдений из **{len(sites)}** статей и **{sites.site_id.nunique()}** координат: {len(x) - direct_accepted} табличных строк с документно-однозначной связью и {direct_accepted} строк с прямой связью метки профиля, горизонта и координаты. Для OCR-ветви сверены **{verification['ok']}/{verification['checked']}** ячеек — без пропусков локатора или расхождений; прямые текстовые строки содержат полный исходный блок таблицы в собственном локаторе доказательств.

Происхождение точных координат разделено явно: **{text_coordinate_records}** записей извлечены из полнотекстовой статьи, **{ocr_coordinate_records}** — из отдельного OCR-артефакта таблицы/подписи. Последний путь является дополнительным и не заменяет текстовый разбор.

В описательном слое у {int(profiles.soil_classification.notna().sum())} профилей есть исходный почвенный термин, у {int(profiles.land_use.notna().sum())} — указание землепользования. Это частота лексических описаний в публикациях, не оценка распространённости типов почв: русские и англоязычные варианты пока не объединяются автоматическим нормализатором.

## Полный спектр табличных свойств

Главная закономерность полного корпуса — не «превосходство pH», а публикационная специализация. pH in water даёт {int(full_inventory.loc[full_inventory.property.eq('pH in water'), 'numeric_cells'].iloc[0]):,} ячеек, тогда как микроэлементная категория суммарно даёт **{int(full_categories.loc[full_categories.category.eq('microelement'), 'numeric_cells'].iloc[0]):,}**, обменная — **{int(full_categories.loc[full_categories.category.eq('exchange'), 'numeric_cells'].iloc[0]):,}**, органическая — **{int(full_categories.loc[full_categories.category.eq('organic'), 'numeric_cells'].iloc[0]):,}**. Следовательно, pH-подслой — удобный контроль качества, но не репрезентативный срез всей базы. Полная сводка — [full_table_property_inventory.csv](data/full_table_property_inventory.csv) и [full_table_category_inventory.csv](tables/full_table_category_inventory.csv).

Этот инвентарь не используется для картирования значений: у части ячеек нет единицы в OCR, у большинства нет надёжной связи «строка таблицы → конкретная координата». Он показывает объём и тематическую структуру доступных данных, а не численное распределение почвенных свойств в РФ.

Пространственная готовность полного корпуса крайне неравномерна: **{int(full_spatial.loc['document_single_reported_coordinate', 'numeric_cells']):,}** ячеек ({full_spatial.loc['document_single_reported_coordinate', 'share_of_all_numeric_cells_percent']:.2f}%) происходят из статей с одной сообщённой точкой, **{int(full_spatial.loc['document_multiple_reported_coordinates', 'numeric_cells']):,}** — из многоточечных статей и требуют привязки строки, а **{int(full_spatial.loc['no_reported_coordinate', 'numeric_cells']):,}** ({full_spatial.loc['no_reported_coordinate', 'share_of_all_numeric_cells_percent']:.2f}%) вообще не имеют явной координаты в тексте. Поэтому ограниченный пространственный слой — не следствие отбора «удобных» свойств, а следствие отсутствующей географической связи у большей части полной таблицы. Детали — [full_table_spatial_linkage_summary.csv](tables/full_table_spatial_linkage_summary.csv).

## Материалы и контроль качества

Покрытие источников неравномерно: для «Почвоведения» доступны тексты всех {int(coverage.loc[coverage.corpus.eq('pochvovedenie'), 'documents_total'].iloc[0])} документов, а для Springer — тексты {int(springer.documents_with_fulltext)} из {int(springer.documents_total)}. У остальных Springer сохранены OCR-таблицы, но нет полнотекстовой статьи или зарегистрированного PDF, поэтому их численные ячейки остаются в доказательной очереди и не получают выдуманную географическую привязку. Полная сводка — [corpus_coverage.csv](data/corpus_coverage.csv).

Координаты извлекались в десятичной и DMS-записи только при явных обозначениях широты/долготы (`N`, `E` и аналоги); также поддерживается UTM только при явном указании системы и зоны. Необозначенные пары чисел не считались координатами. Такой фильтр устранил ложные совпадения OCR (например, значения таблиц, похожие на географические пары). Одна явно записанная UTM-пара прошла проверку зоны, полушария, контекста отбора и границы РФ; её исходный фрагмент сохранён в доказательном слое.

Пространственный охват всех подтверждённых координат: **{lat0:.3f}–{lat1:.3f}° N** и **{lon0:.3f}–{lon1:.3f}° E**. Геопортал показывает все {len(coordinates)} записей; точки без числовых значений сохраняются как доказательная пространственная витрина, а не искусственно заполненный слой свойств. Табличная связь имеет уровень `document_single_reported_coordinate`: координата относится к исследованию в целом, а не к каждой строке таблицы. Поэтому значения внутри статьи нельзя считать независимыми пространственными репликациями.

Для {int(nn.n_unique_locations)} уникальных положений медианное расстояние до ближайшей соседней точки равно **{nn['median']:.2f} км** (IQR {nn.q25:.2f}–{nn.q75:.2f} км); {int(nn.locations_under_1_km)} положений имеют соседа ближе 1 км, а {int(nn.locations_over_100_km)} — дальше 100 км. Это описание геометрии массива, а не тест пространственной автокорреляции: близкие точки могут быть серией одного исследования, а не независимыми разрезами. Детали приведены в [nearest_neighbour_summary.csv](tables/nearest_neighbour_summary.csv) и [spatial_source_coverage.csv](tables/spatial_source_coverage.csv).

## Результаты

Строгий слой содержит **{len(x)}** значений по {x.property.nunique()} свойствам: {property_sentence}. Для каждого свойства опубликована отдельная сводка минимумов, квартилей и медианы в [point_property_summary.csv](tables/point_property_summary.csv), а полный русскоязычный словарь с единицами — в [property_units.html](property_units.html). Эти характеристики описывают неоднородные экспериментальные и профильные таблицы, а не распределение свойств в РФ. Значения разных свойств не объединяются на одной шкале, а на рисунке каждому свойству дан собственный масштаб.

Главный содержательный результат пока методический: наблюдения неоднородны по цели статей — от экспериментального изменения pH при воздействии продуктов горения до физической деградации порового пространства. Поэтому межсайтовые средние и корреляции были бы псевдорепликацией. Допустимы только описательные характеристики отдельных свойств и анализ внутри исходных исследований после ручной интерпретации дизайна.

Для {len(depth_summary)} последовательностей pH с четырьмя и более горизонтами сохранён внутристатейный анализ глубины: [within_profile_depth_summary.csv](tables/within_profile_depth_summary.csv). Его коэффициенты ранговой связи описывают порядок горизонтов только внутри источника и не объединяются в общий эффект. Два идентичных профиля pH отмечены отдельно как потенциально не-независимые.

## Временная ось

Для полного координатного слоя доступна библиографическая шкала **{pub_range}**: [coordinate_source_documents.csv](tables/coordinate_source_documents.csv) и [coordinate_source_publication_timeline.csv](tables/coordinate_source_publication_timeline.csv). Она **не интерпретируется как время отбора**. Из {len(temporal)} источников строгого числового слоя {curated_temporal} прошли контекстную классификацию дат; все извлечённые даты сохранены в [temporal_evidence.csv](data/temporal_evidence.csv), а статус их интерпретации — в [temporal_register.csv](tables/temporal_register.csv). Среди вручную классифицированных источников есть мониторинг дыхания почв за **1998–2022** (25 лет), дискретные отборы 2021–2022 гг. и палеохронологический контекст. Их нельзя статистически склеивать в общую временную траекторию.

## Неочевидные закономерности и ограничения

1. **Контроль формы записи важнее числа координат.** Строгая проверка отбросила правдоподобные, но ложные «координаты», возникавшие из пар табличных чисел. Это резко уменьшило покрытие, но повысило научную ценность слоя.
2. **Временная неоднородность семантическая, а не просто неполнота.** В одном наборе соседствуют эксперимент, многолетний мониторинг, разовые городские отборы и палеореконструкция. Общий тренд «во времени» был бы категорической ошибкой.
3. **Структура свойств предопределена публикационным дизайном.** Наиболее частое свойство в строгом подслое — pH в воде ({counts.get('pH in water', 0)}/{len(x)}), но это не означает его доминирования в почвенном покрове; это следствие того, какие таблицы встретились в верифицированных статьях.
4. **Кластеризация источников не равна кластерам почвенных свойств.** Близкие координаты отражают многоточечные дизайны статей; без общего протокола отбора и сопоставимых показателей вычислять Moran’s I, вариограмму или «горячие точки» было бы методологически неверно.
5. **Есть потенциальная не-независимость публикаций.** В {reused.document_id.nunique()} статьях обнаружен один идентичный вектор pH по тем же координатам и горизонтам. Это не автоматически перевод или дубликат, но достаточная причина не считать эти 14 ячеек независимыми до проверки связи исследований. Доказательный список — [potential_reused_observation_vectors.csv](tables/potential_reused_observation_vectors.csv).

## Фигуры и результирующие таблицы

![Пространственное покрытие](assets/spatial_coverage.png)

![Ближайшие соседи](assets/nearest_neighbour_distribution.png)

![Состав свойств](assets/property_coverage.png)

![Распределение значений](assets/value_distribution.png)

![pH по исследованиям](assets/study_ph_distribution.png)

![Исходные почвенные термины профилей](assets/profile_descriptor_coverage.png)

![pH по глубине внутри источников](assets/within_profile_ph_depth.png)

![Полный спектр свойств в OCR-таблицах](assets/full_table_property_coverage.png)

![Библиографическая шкала координатных источников](assets/coordinate_source_publication_years.png)

- [Все сообщённые координаты и источники](data/reported_sites.csv)
- [Нормализованные измерения: одна единица на свойство](data/normalized_measurements.csv)
- [Русский словарь свойств и канонических единиц](property_units.html)
- [Геокодированные региональные контексты](data/geocoded_context_sites.csv)
- [Текстовые описания разрезов и профилей](data/profile_descriptions.csv)
- [Сводка исходных описательных терминов профилей](tables/profile_descriptor_summary.csv)
- [Инвентаризация готовности слоёв и очередей](tables/data_readiness_summary.csv)
- [Сводка пространственного покрытия](tables/spatial_coverage_summary.csv)
- [Покрытие по корпусам](tables/spatial_source_coverage.csv)
- [Охват регионального контекста](tables/regional_context_coverage.csv)
- [Сводка ближайшего соседа](tables/nearest_neighbour_summary.csv)
- [Свойства строгого числового слоя](tables/point_property_summary.csv)
- [Перечень точек с числовыми значениями](tables/site_summary.csv)
- [Внутристатейные последовательности pH по глубине](tables/within_profile_depth_summary.csv)
- [Полный инвентарь табличных свойств](data/full_table_property_inventory.csv)
- [Инвентарь по категориям свойств](tables/full_table_category_inventory.csv)
- [Связь полного табличного корпуса с координатами](tables/full_table_spatial_linkage_summary.csv)
- [Реестр временной семантики](tables/temporal_register.csv)
- [Потенциально повторно использованные векторы наблюдений](tables/potential_reused_observation_vectors.csv)
- [Все координатные документы и даты публикации](tables/coordinate_source_documents.csv)

## Воспроизводимость

Сборка: `MPLCONFIGDIR=/tmp/mpl python3 docs/scripts/build_analysis.py`. Исходные проверяемые значения — [supported_table_measurements.csv](data/supported_table_measurements.csv); результат сверки — [measurement_verification.json](data/measurement_verification.json). Геопортал — [index.html](index.html). При расширении базы новые координаты должны проходить тот же строгий парсер, проверку страны, привязку контекста и повторную сверку значений.
"""
    (DOCS / "analysis.md").write_text(report, encoding="utf-8")
    render_report_html(report)


def inline_markdown(value: str) -> str:
    escaped = html.escape(value)
    escaped = re.sub(r"!\[([^]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">', escaped)
    escaped = re.sub(r"\[([^]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', escaped)
    escaped = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`([^`]+)`", r"<code>\1</code>", escaped)
    return escaped


def render_report_html(markdown: str) -> None:
    """Small dependency-free renderer for the report's controlled Markdown."""
    lines, body, in_list = markdown.splitlines(), [], False
    for line in lines:
        if not line.strip():
            if in_list: body.append("</ol>"); in_list = False
            continue
        if line.startswith("# "):
            body.append(f"<h1>{inline_markdown(line[2:])}</h1>")
        elif line.startswith("## "):
            body.append(f"<h2>{inline_markdown(line[3:])}</h2>")
        elif re.match(r"^\d+\. ", line):
            if not in_list: body.append("<ol>"); in_list = True
            item = re.sub(r"^\d+\. ", "", line)
            body.append(f"<li>{inline_markdown(item)}</li>")
        elif line.startswith("- "):
            body.append(f"<p class=\"link\">{inline_markdown(line[2:])}</p>")
        elif line.startswith("!["):
            body.append(inline_markdown(line))
        else:
            body.append(f"<p>{inline_markdown(line)}</p>")
    if in_list: body.append("</ol>")
    page = """<!doctype html><html lang=\"ru\"><head><meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\"><title>Russian Soil Observatory — анализ</title><style>body{max-width:960px;margin:2rem auto;padding:0 1rem;font:16px/1.55 system-ui,sans-serif;color:#172033}h1,h2{line-height:1.2}h2{margin-top:2.2rem;border-bottom:1px solid #d8e0e8;padding-bottom:.35rem}img{display:block;max-width:100%;margin:1.1rem auto;border:1px solid #d8e0e8;border-radius:6px}code{background:#f1f5f9;padding:.1rem .3rem;border-radius:3px}.link{margin:.25rem 0}a{color:#075985}ol{padding-left:1.5rem}</style></head><body><p><a href=\"index.html\">← Геопортал</a> · <a href=\"analysis.md\">Markdown-версия</a></p>""" + "\n".join(body) + "</body></html>"
    (DOCS / "analysis.html").write_text(page, encoding="utf-8")


def main():
    x, coordinates, metadata, contexts, profiles, full_inventory, full_inventory_meta, full_inventory_spatial = load()
    property_dictionary_and_normalized_measurements(x)
    summary, sites = summaries(x, coordinates)
    coverage, spacing, _nearest = spatial_statistics(coordinates)
    regional_coverage = regional_context_statistics(contexts)
    profile_soil, _profile_land = profile_descriptor_statistics(profiles)
    readiness_summary(coordinates, contexts, profiles, x)
    depth_ph, depth_summary = within_profile_depth_statistics(x)
    full_categories = full_table_inventory_statistics(full_inventory)
    full_spatial = full_table_spatial_linkage_statistics(full_inventory_spatial, full_inventory_meta["numeric_cells"])
    coordinate_documents, coordinate_timeline = coordinate_source_timeline(coordinates, metadata)
    reused = potential_reuse(x)
    temporal = temporal_register(x)
    figures(x, summary, sites, coordinates, coordinate_timeline, contexts, profile_soil, depth_ph, full_inventory)
    portal(x, coordinates, metadata, contexts, profiles)
    result = {"observations": len(x), "direct_accepted_observations": int((x.qa_status == "accepted").sum()), "flagged_document_single_site_observations": int((x.qa_status == "flagged").sum()), "detailed_sites": int(x.site_id.nunique()), "detailed_documents": int(x.document_id.nunique()),
              "reported_coordinate_records": len(coordinates), "unique_reported_coordinate_locations": coordinates[["latitude", "longitude"]].drop_duplicates().shape[0],
              "coordinate_documents": int(coordinates.document_ids.str.split(";").explode().nunique()),
              "regional_context_records": len(contexts), "regional_context_documents": int(contexts.document_id.nunique()),
              "regional_context_unique_centroids": int(contexts[["latitude", "longitude"]].drop_duplicates().shape[0]),
              "descriptive_profiles": len(profiles), "descriptive_profile_documents": int(profiles.document_id.nunique()),
              "coordinate_documents_with_publication_year": int(coordinate_documents.publication_year.notna().sum()),
              "full_table_inventory": full_inventory_meta,
              "properties": {k: int(v) for k, v in x.property.value_counts().items()},
              "source_cell_verification": json.loads((DATA / "measurement_verification.json").read_text()),
              "temporal_register_rows": len(temporal), "interpretation": "descriptive only; no national spatial inference"}
    (DOCS / "analysis_results.json").write_text(json.dumps(safe(result), ensure_ascii=False, indent=2), encoding="utf-8")
    report(x, summary, sites, temporal, coordinates, spacing, coordinate_timeline, contexts, reused, profiles, depth_summary, full_inventory, full_categories, full_inventory_meta, full_spatial)
    print(json.dumps(safe(result), ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
