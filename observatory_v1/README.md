# Russian Soil Observatory v1

This is a provenance-first operational database for confirmed soil observation
points in Russia, built from Springer and `Почвоведение` separately.

Rules:

- A translation and its original are separate `document` rows; use
  `document_link` only after a relationship is checked.
- OCR/table output is evidence, not an observation. It enters `extraction`
  before it can create a site, profile, horizon, or measurement.
- Operational `site` rows must be Russian (`country_code = 'RU'`) and carry a
  spatial-confidence class.
- `profile`, `horizon`, `sample` and `laboratory_analysis` are separate: a
  sample label or a method is never discarded when a result is normalized.
- Every accepted measurement must lead back to an artifact and, where used, an
  extraction record.

`bootstrap.py` creates `russian_soil_observatory.sqlite`. Source profiling and
ingestion will be added as reproducible stages; no legacy "final" JSON is
treated as ground truth.

## Staged workflow

1. `ingest_*_text.py` and the Springer OCR index create candidates only.
2. `country_triage.py` checks every explicit coordinate against a pinned
   country-boundary GeoJSON and writes `location_validation`. It never creates
   an operational point; border and unmatched cases remain unresolved.
3. A promotion step may create a Russian `site`, `profile`, `horizon`, and
   `measurement` only when their document evidence can be linked without
   guessing. `v_ready_measurements` is the only ready-to-use data view.

The boundary file is an external reference input. Store its dataset name,
version, URL and SHA-256 next to the database before triage, so that a country
decision can be repeated later.
