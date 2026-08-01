PRAGMA foreign_keys = ON;

-- A document is never merged with its translation.  Relationships are explicit.
CREATE TABLE IF NOT EXISTS document (
  document_id TEXT PRIMARY KEY,
  corpus TEXT NOT NULL CHECK (corpus IN ('springer','pochvovedenie')),
  language TEXT,
  title TEXT,
  authors TEXT,
  publication_year INTEGER,
  doi TEXT,
  source_path TEXT NOT NULL,
  sha256 TEXT,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE (corpus, source_path)
);

CREATE TABLE IF NOT EXISTS document_link (
  document_id_a TEXT NOT NULL REFERENCES document(document_id),
  document_id_b TEXT NOT NULL REFERENCES document(document_id),
  relation TEXT NOT NULL CHECK (relation IN ('translation_of','same_study','cites','possible_overlap')),
  confidence TEXT NOT NULL CHECK (confidence IN ('confirmed','candidate','rejected')),
  evidence_note TEXT,
  PRIMARY KEY (document_id_a, document_id_b, relation)
);

CREATE TABLE IF NOT EXISTS source_artifact (
  artifact_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES document(document_id),
  artifact_type TEXT NOT NULL CHECK (artifact_type IN ('pdf','page','table','crop','ocr_markdown','table_json','text')),
  source_path TEXT NOT NULL,
  page_start INTEGER,
  page_end INTEGER,
  table_label TEXT,
  sha256 TEXT,
  parent_artifact_id TEXT REFERENCES source_artifact(artifact_id),
  metadata_json TEXT,
  UNIQUE (document_id, artifact_type, source_path)
);

-- Parsed rows remain staging evidence until a Russian point and its values are verified.
CREATE TABLE IF NOT EXISTS extraction (
  extraction_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  extractor TEXT NOT NULL,
  extractor_version TEXT,
  raw_text TEXT,
  parsed_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('raw','parsed','needs_review','rejected','accepted')),
  quality_score REAL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- OCR tables are preserved as a matrix before semantic parsing.  This is the
-- reproducible bridge from a crop to row/header/value interpretations.
CREATE TABLE IF NOT EXISTS table_cell (
  cell_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  row_index INTEGER NOT NULL CHECK (row_index >= 0),
  column_index INTEGER NOT NULL CHECK (column_index >= 0),
  text_raw TEXT NOT NULL,
  rowspan INTEGER NOT NULL DEFAULT 1 CHECK (rowspan >= 1),
  colspan INTEGER NOT NULL DEFAULT 1 CHECK (colspan >= 1),
  UNIQUE (artifact_id, row_index, column_index)
);

CREATE TABLE IF NOT EXISTS site (
  site_id TEXT PRIMARY KEY,
  country_code TEXT NOT NULL,
  name TEXT,
  region TEXT,
  latitude REAL,
  longitude REAL,
  spatial_precision_m REAL,
  spatial_confidence TEXT NOT NULL CHECK (spatial_confidence IN ('exact','reported','geocoded','regional_only','unverified')),
  geometry_source TEXT,
  CHECK (country_code = 'RU'),
  CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),
  CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE TABLE IF NOT EXISTS site_evidence (
  site_id TEXT NOT NULL REFERENCES site(site_id),
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  evidence_text TEXT NOT NULL,
  evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('coordinates','location_text','map','table','geocoding')),
  PRIMARY KEY (site_id, artifact_id, evidence_kind)
);

-- Several strict parsers may recognize the same printed coordinate using
-- different typography rules.  Keep every candidate's provenance linked to
-- one canonical site instead of creating duplicate map points or overwriting
-- the original coordinate evidence.
CREATE TABLE IF NOT EXISTS site_coordinate_candidate (
  site_id TEXT NOT NULL REFERENCES site(site_id),
  candidate_id TEXT NOT NULL REFERENCES location_candidate(candidate_id),
  link_reason TEXT NOT NULL,
  PRIMARY KEY (site_id, candidate_id)
);

-- Canonicalisation is recorded, never silently discarded.  Parser variants
-- can emit the same printed coordinate more than once in one document; this
-- table preserves the former site identifier and the reason for its merge.
CREATE TABLE IF NOT EXISTS site_merge (
  retired_site_id TEXT PRIMARY KEY,
  canonical_site_id TEXT NOT NULL,
  document_id TEXT NOT NULL REFERENCES document(document_id),
  merge_reason TEXT NOT NULL,
  merged_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS profile (
  profile_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES site(site_id),
  profile_label TEXT,
  -- Literal statements from the publication.  These are deliberately not
  -- normalized taxonomic assignments and must never be inferred from a map
  -- unit, a regional description, or a translation.
  author_soil_type_raw TEXT,
  author_profile_formula_raw TEXT,
  soil_classification TEXT,
  classification_system TEXT,
  land_use TEXT,
  notes TEXT
);

-- A textual soil/profile description is not interchangeable with a measured
-- horizon.  Retain its source separately so that a profile-level statement
-- can be displayed and audited without manufacturing an analytical result.
CREATE TABLE IF NOT EXISTS profile_evidence (
  profile_id TEXT NOT NULL REFERENCES profile(profile_id),
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  extraction_id TEXT REFERENCES extraction(extraction_id),
  evidence_text TEXT NOT NULL,
  evidence_kind TEXT NOT NULL CHECK (evidence_kind IN ('profile_description','table_header','table_row')),
  PRIMARY KEY (profile_id, artifact_id, evidence_kind)
);

-- One profile can have more than one author statement (for example a Russian
-- name and a WRB rendering, or a repeated description in the manuscript).
-- Keep every literal candidate with the exact textual evidence; the two
-- convenience columns on profile contain the closest/first strict statement.
CREATE TABLE IF NOT EXISTS profile_author_statement (
  statement_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profile(profile_id),
  field_name TEXT NOT NULL CHECK (field_name IN ('author_soil_type_raw','author_profile_formula_raw')),
  raw_value TEXT NOT NULL,
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  extraction_id TEXT REFERENCES extraction(extraction_id),
  evidence_text TEXT NOT NULL,
  extractor TEXT NOT NULL,
  review_status TEXT NOT NULL DEFAULT 'unreviewed'
    CHECK (review_status IN ('unreviewed','accepted','flagged')),
  UNIQUE (profile_id, field_name, raw_value, artifact_id)
);

-- Literal author statements found in a primary text before a unique link to a
-- coordinate-linked profile is proven.  These candidates preserve discovery
-- coverage without allowing a document-level statement to contaminate a site.
CREATE TABLE IF NOT EXISTS document_author_statement_candidate (
  candidate_id TEXT PRIMARY KEY,
  document_id TEXT NOT NULL REFERENCES document(document_id),
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  field_name TEXT NOT NULL CHECK (field_name IN ('author_soil_type_raw','author_profile_formula_raw')),
  profile_label_raw TEXT,
  raw_value TEXT NOT NULL,
  evidence_text TEXT NOT NULL,
  link_status TEXT NOT NULL DEFAULT 'unlinked'
    CHECK (link_status IN ('unlinked','linked','rejected')),
  extractor TEXT NOT NULL,
  UNIQUE (document_id, artifact_id, field_name, raw_value, profile_label_raw)
);

CREATE TABLE IF NOT EXISTS horizon (
  horizon_id TEXT PRIMARY KEY,
  profile_id TEXT NOT NULL REFERENCES profile(profile_id),
  horizon_label TEXT,
  depth_top_cm REAL,
  depth_bottom_cm REAL,
  CHECK (depth_top_cm IS NULL OR depth_top_cm >= 0),
  CHECK (depth_bottom_cm IS NULL OR depth_bottom_cm >= depth_top_cm)
);

-- A profile/horizon may yield several physical samples (bulk, composite,
-- replicate, seasonal sampling).  It must not be reduced to a text label on a
-- measurement candidate.
CREATE TABLE IF NOT EXISTS sample (
  sample_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES site(site_id),
  profile_id TEXT REFERENCES profile(profile_id),
  horizon_id TEXT REFERENCES horizon(horizon_id),
  sample_label TEXT,
  material TEXT,
  collection_date TEXT,
  depth_top_cm REAL,
  depth_bottom_cm REAL,
  collection_method TEXT,
  notes TEXT,
  CHECK (depth_top_cm IS NULL OR depth_top_cm >= 0),
  CHECK (depth_bottom_cm IS NULL OR depth_bottom_cm >= depth_top_cm)
);

CREATE TABLE IF NOT EXISTS sample_evidence (
  sample_id TEXT NOT NULL REFERENCES sample(sample_id),
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  extraction_id TEXT REFERENCES extraction(extraction_id),
  evidence_text TEXT NOT NULL,
  PRIMARY KEY (sample_id, artifact_id)
);

-- A laboratory analysis records the analytical event independently of its
-- resulting properties.  One event can yield several elements/properties.
CREATE TABLE IF NOT EXISTS laboratory_analysis (
  analysis_id TEXT PRIMARY KEY,
  sample_id TEXT NOT NULL REFERENCES sample(sample_id),
  analysis_label TEXT,
  laboratory_name TEXT,
  method_raw TEXT,
  method_normalized TEXT,
  instrument TEXT,
  extraction_reagent TEXT,
  notes TEXT,
  evidence_artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  evidence_extraction_id TEXT REFERENCES extraction(extraction_id)
);

CREATE TABLE IF NOT EXISTS property_definition (
  property_id TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL UNIQUE,
  category TEXT NOT NULL,
  canonical_unit TEXT,
  description TEXT
);

CREATE TABLE IF NOT EXISTS method_definition (
  method_id TEXT PRIMARY KEY,
  canonical_name TEXT NOT NULL UNIQUE,
  domain TEXT NOT NULL,
  description TEXT
);

CREATE TABLE IF NOT EXISTS method_candidate (
  candidate_id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES extraction(extraction_id),
  method_id TEXT REFERENCES method_definition(method_id),
  method_raw TEXT NOT NULL,
  context_text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unreviewed','accepted','rejected')) DEFAULT 'unreviewed'
);

CREATE TABLE IF NOT EXISTS measurement (
  measurement_id TEXT PRIMARY KEY,
  site_id TEXT NOT NULL REFERENCES site(site_id),
  profile_id TEXT REFERENCES profile(profile_id),
  horizon_id TEXT REFERENCES horizon(horizon_id),
  property_id TEXT NOT NULL REFERENCES property_definition(property_id),
  value_num REAL,
  value_text TEXT,
  unit_raw TEXT,
  unit_normalized TEXT,
  method_raw TEXT,
  method_normalized TEXT,
  qa_status TEXT NOT NULL CHECK (qa_status IN ('unreviewed','accepted','flagged','rejected')),
  evidence_artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  evidence_extraction_id TEXT REFERENCES extraction(extraction_id),
  evidence_locator TEXT,
  CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);

CREATE TABLE IF NOT EXISTS laboratory_analysis_measurement (
  analysis_id TEXT NOT NULL REFERENCES laboratory_analysis(analysis_id),
  measurement_id TEXT NOT NULL REFERENCES measurement(measurement_id),
  PRIMARY KEY (analysis_id, measurement_id)
);

-- Machine-extracted candidates are intentionally separate from operational rows.
CREATE TABLE IF NOT EXISTS location_candidate (
  candidate_id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES extraction(extraction_id),
  latitude REAL,
  longitude REAL,
  place_text TEXT,
  country_candidate TEXT,
  precision_hint TEXT,
  context_text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unreviewed','accepted','rejected')) DEFAULT 'unreviewed'
);

-- A country decision is separate from the OCR/text candidate itself.  This
-- makes the spatial filter auditable and prevents a journal/corpus label from
-- becoming an unsupported geographic assertion.
CREATE TABLE IF NOT EXISTS location_validation (
  candidate_id TEXT PRIMARY KEY REFERENCES location_candidate(candidate_id),
  validator TEXT NOT NULL,
  boundary_dataset TEXT NOT NULL,
  boundary_version TEXT,
  country_code TEXT,
  result TEXT NOT NULL CHECK (result IN ('inside','outside','border_ambiguous','unresolved')),
  details_json TEXT,
  validated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Articles often name an administrative district but report no sampling
-- coordinate.  Keep that observation: a later geocode is explicitly a
-- district-level location, never a fabricated point of collection.
CREATE TABLE IF NOT EXISTS place_candidate (
  candidate_id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES extraction(extraction_id),
  place_text TEXT NOT NULL,
  administrative_level TEXT NOT NULL CHECK (administrative_level IN ('district','region','settlement','other')),
  context_text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unreviewed','accepted','rejected')) DEFAULT 'unreviewed'
);

CREATE TABLE IF NOT EXISTS place_geocode (
  candidate_id TEXT PRIMARY KEY REFERENCES place_candidate(candidate_id),
  provider TEXT NOT NULL,
  query_text TEXT NOT NULL,
  display_name TEXT,
  country_code TEXT,
  latitude REAL,
  longitude REAL,
  geometry_kind TEXT NOT NULL CHECK (geometry_kind IN ('centroid','boundary_centroid','point','unresolved')),
  spatial_precision_m REAL,
  source_url TEXT,
  raw_json TEXT,
  status TEXT NOT NULL CHECK (status IN ('accepted','ambiguous','rejected','unresolved')),
  geocoded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS measurement_candidate (
  candidate_id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES extraction(extraction_id),
  property_id TEXT REFERENCES property_definition(property_id),
  property_raw TEXT NOT NULL,
  value_num REAL,
  value_text TEXT,
  unit_raw TEXT,
  method_raw TEXT,
  horizon_label TEXT,
  depth_top_cm REAL,
  depth_bottom_cm REAL,
  sample_label TEXT,
  context_text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unreviewed','accepted','rejected')) DEFAULT 'unreviewed',
  CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);

-- Soil names and land use are commonly reported in prose rather than a
-- laboratory table.  Retain the exact wording and context before linking it
-- to a profile.
CREATE TABLE IF NOT EXISTS profile_candidate (
  candidate_id TEXT PRIMARY KEY,
  extraction_id TEXT NOT NULL REFERENCES extraction(extraction_id),
  profile_label TEXT,
  soil_classification_raw TEXT,
  classification_system_candidate TEXT,
  land_use_raw TEXT,
  context_text TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('unreviewed','accepted','rejected')) DEFAULT 'unreviewed'
);

-- Normalization is a reversible interpretation of an extracted candidate;
-- raw values/units stay untouched for audit and later correction.
CREATE TABLE IF NOT EXISTS measurement_candidate_normalization (
  candidate_id TEXT PRIMARY KEY REFERENCES measurement_candidate(candidate_id),
  value_normalized REAL,
  unit_normalized TEXT,
  normalization_status TEXT NOT NULL CHECK (normalization_status IN ('exact','converted','incompatible','missing_unit','missing_value')),
  warning TEXT,
  normalizer_version TEXT NOT NULL,
  normalized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Candidate values from an OCR table retain the exact header and matrix
-- coordinates; they are never conflated with prose candidates.
CREATE TABLE IF NOT EXISTS table_measurement_candidate (
  candidate_id TEXT PRIMARY KEY,
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  row_index INTEGER NOT NULL,
  column_index INTEGER NOT NULL,
  property_id TEXT REFERENCES property_definition(property_id),
  property_header_raw TEXT NOT NULL,
  value_num REAL,
  value_text TEXT,
  unit_raw TEXT,
  row_label_raw TEXT,
  horizon_label TEXT,
  depth_top_cm REAL,
  depth_bottom_cm REAL,
  status TEXT NOT NULL CHECK (status IN ('unreviewed','accepted','rejected')) DEFAULT 'unreviewed',
  CHECK (value_num IS NOT NULL OR value_text IS NOT NULL)
);

-- Some PDF table crops split the header and the numeric body.  A candidate
-- created from such a pair keeps both artifacts instead of pretending that
-- the header occurred in the value crop.
CREATE TABLE IF NOT EXISTS table_candidate_header_link (
  candidate_id TEXT PRIMARY KEY REFERENCES table_measurement_candidate(candidate_id),
  header_artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  value_artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  linkage_rule TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS table_measurement_candidate_normalization (
  candidate_id TEXT PRIMARY KEY REFERENCES table_measurement_candidate(candidate_id),
  value_normalized REAL,
  unit_normalized TEXT,
  normalization_status TEXT NOT NULL CHECK (normalization_status IN ('exact','converted','incompatible','missing_unit','missing_value')),
  warning TEXT,
  normalizer_version TEXT NOT NULL,
  normalized_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Complete, provenance-preserving analytical layer for every header-grounded
-- value recovered from a table.  Unlike ``measurement``, this table does not
-- require a sampling point: absence of a defensible row-to-site link is data
-- quality information, not a reason to discard the printed value.
CREATE TABLE IF NOT EXISTS table_observation (
  observation_id TEXT PRIMARY KEY,
  candidate_id TEXT NOT NULL UNIQUE REFERENCES table_measurement_candidate(candidate_id),
  document_id TEXT NOT NULL REFERENCES document(document_id),
  artifact_id TEXT NOT NULL REFERENCES source_artifact(artifact_id),
  row_index INTEGER NOT NULL,
  column_index INTEGER NOT NULL,
  property_id TEXT NOT NULL REFERENCES property_definition(property_id),
  property_header_raw TEXT NOT NULL,
  value_num_raw REAL,
  value_text_raw TEXT,
  unit_raw TEXT,
  value_normalized REAL,
  unit_normalized TEXT,
  normalization_status TEXT NOT NULL CHECK (normalization_status IN ('exact','converted','incompatible','missing_unit','missing_value')),
  normalization_warning TEXT,
  row_label_raw TEXT,
  horizon_label_raw TEXT,
  depth_top_cm REAL,
  depth_bottom_cm REAL,
  context_site_id TEXT REFERENCES site(site_id),
  spatial_linkage TEXT NOT NULL CHECK (spatial_linkage IN ('no_reported_coordinate','document_single_reported_coordinate','document_multiple_reported_coordinates','row_profile_verified')),
  operational_measurement_id TEXT REFERENCES measurement(measurement_id),
  qa_status TEXT NOT NULL CHECK (qa_status IN ('normalized','unit_missing','unit_incompatible','missing_value','flagged')),
  evidence_locator TEXT NOT NULL,
  created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
  CHECK (value_num_raw IS NOT NULL OR value_text_raw IS NOT NULL)
);

CREATE INDEX IF NOT EXISTS idx_document_doi ON document(doi);
CREATE INDEX IF NOT EXISTS idx_artifact_document ON source_artifact(document_id);
CREATE INDEX IF NOT EXISTS idx_extraction_artifact ON extraction(artifact_id);
CREATE INDEX IF NOT EXISTS idx_table_cell_artifact ON table_cell(artifact_id, row_index, column_index);
CREATE INDEX IF NOT EXISTS idx_site_coordinates ON site(latitude, longitude);
CREATE INDEX IF NOT EXISTS idx_site_coordinate_candidate_candidate ON site_coordinate_candidate(candidate_id);
CREATE INDEX IF NOT EXISTS idx_measurement_property ON measurement(property_id);
CREATE INDEX IF NOT EXISTS idx_measurement_site ON measurement(site_id);
CREATE INDEX IF NOT EXISTS idx_sample_site ON sample(site_id);
CREATE INDEX IF NOT EXISTS idx_sample_profile ON sample(profile_id);
CREATE INDEX IF NOT EXISTS idx_laboratory_analysis_sample ON laboratory_analysis(sample_id);
CREATE INDEX IF NOT EXISTS idx_location_candidate_extraction ON location_candidate(extraction_id);
CREATE INDEX IF NOT EXISTS idx_location_validation_country ON location_validation(country_code, result);
CREATE INDEX IF NOT EXISTS idx_place_candidate_extraction ON place_candidate(extraction_id);
CREATE INDEX IF NOT EXISTS idx_place_geocode_country ON place_geocode(country_code, status);
CREATE INDEX IF NOT EXISTS idx_measurement_candidate_property ON measurement_candidate(property_id);
CREATE INDEX IF NOT EXISTS idx_profile_candidate_extraction ON profile_candidate(extraction_id);
CREATE INDEX IF NOT EXISTS idx_method_candidate_extraction ON method_candidate(extraction_id);
CREATE INDEX IF NOT EXISTS idx_candidate_normalization_status ON measurement_candidate_normalization(normalization_status);
CREATE INDEX IF NOT EXISTS idx_table_measurement_property ON table_measurement_candidate(property_id);
CREATE INDEX IF NOT EXISTS idx_table_observation_property ON table_observation(property_id);
CREATE INDEX IF NOT EXISTS idx_table_observation_document ON table_observation(document_id);
CREATE INDEX IF NOT EXISTS idx_table_observation_spatial ON table_observation(spatial_linkage);

CREATE VIEW IF NOT EXISTS v_measurement_candidate_provenance AS
SELECT
  mc.candidate_id, d.corpus, d.document_id, d.title, d.publication_year,
  pd.canonical_name AS property, pd.category, mc.property_raw,
  mc.value_num, mc.value_text, mc.unit_raw, mc.method_raw,
  mc.sample_label, mc.horizon_label, mc.depth_top_cm, mc.depth_bottom_cm,
  mc.status, mc.context_text, a.source_path AS evidence_path,
  a.page_start, a.page_end, a.table_label
FROM measurement_candidate mc
JOIN extraction e ON e.extraction_id = mc.extraction_id
JOIN source_artifact a ON a.artifact_id = e.artifact_id
JOIN document d ON d.document_id = a.document_id
LEFT JOIN property_definition pd ON pd.property_id = mc.property_id;

CREATE VIEW IF NOT EXISTS v_ready_measurements AS
SELECT
  m.measurement_id, d.corpus, d.document_id, s.site_id, s.name AS site_name,
  s.latitude, s.longitude, s.spatial_confidence, p.profile_label,
  h.horizon_label, h.depth_top_cm, h.depth_bottom_cm,
  pd.canonical_name AS property, pd.category, m.value_num, m.value_text,
  m.unit_normalized, m.unit_raw, m.method_normalized, m.method_raw,
  a.source_path AS evidence_path, m.evidence_locator
FROM measurement m
JOIN site s ON s.site_id=m.site_id
LEFT JOIN profile p ON p.profile_id=m.profile_id
LEFT JOIN horizon h ON h.horizon_id=m.horizon_id
JOIN property_definition pd ON pd.property_id=m.property_id
JOIN source_artifact a ON a.artifact_id=m.evidence_artifact_id
JOIN document d ON d.document_id=a.document_id
-- A ready measurement is point-scale only when the coordinate was explicitly
-- reported or otherwise exact.  Administrative centroids and quarantined
-- geocoding candidates remain discoverable in their own layers, never here.
WHERE m.qa_status='accepted'
  AND s.country_code='RU'
  AND s.spatial_confidence IN ('exact','reported');

CREATE VIEW IF NOT EXISTS v_full_table_observations AS
SELECT o.observation_id, o.candidate_id, d.corpus, o.document_id,
       pd.canonical_name AS property, pd.category,
       o.value_num_raw, o.value_text_raw, o.unit_raw,
       o.value_normalized, o.unit_normalized, o.normalization_status,
       o.qa_status, o.spatial_linkage, o.context_site_id,
       o.row_label_raw, o.horizon_label_raw, o.depth_top_cm, o.depth_bottom_cm,
       o.operational_measurement_id, o.evidence_locator,
       a.source_path AS evidence_path, a.page_start, a.page_end, a.table_label
FROM table_observation o
JOIN document d ON d.document_id=o.document_id
JOIN property_definition pd ON pd.property_id=o.property_id
JOIN source_artifact a ON a.artifact_id=o.artifact_id;
