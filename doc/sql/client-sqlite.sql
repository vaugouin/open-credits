-- =============================================================================
-- open-credits, the client's local SQLite file (one per contributor)
-- Logical model: doc/data-model.md. Master side: doc/sql/OC-tables.sql.
--
-- Layers 0 to 3 of the contributor's own runs, plus a copy of the role vocabulary.
-- Table and column names are the logical names of the data model and of
-- submission.json, so exporting a bundle is a straight read.
--
-- What differs from the master:
--   - no edition, consolidated credit, history, report or contributor: the master's business;
--   - work, copy and part have local UUIDs only: the bundle identifies them by external ids,
--     fingerprint and opensubtitles_hash, and the master keeps its own ids for them;
--   - a few columns stay on this machine and are never exported: part.local_path,
--     frame.evidence_path, submission.status and exported_at, work.plex_rating_key;
--   - the vocabulary is keyed by code, as the bundle uses it (credit.role_code);
--     it is replaced as a whole when a new version is downloaded (meta.vocabulary_version).
--
-- STRICT tables (SQLite >= 3.37), foreign keys enforced: run PRAGMA foreign_keys = ON
-- on every connection. Booleans are 0/1, lists are JSON arrays, UUIDs are version 7 text.
-- =============================================================================

PRAGMA user_version = 1;  -- schema version of this file
PRAGMA foreign_keys = ON;

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,   -- vocabulary_version, client_version...
  value TEXT NOT NULL
) STRICT;


-- Layer 0 ---------------------------------------------------------------------

CREATE TABLE work (
  id              TEXT PRIMARY KEY CHECK (length(id) = 36),
  kind            TEXT NOT NULL CHECK (kind IN ('movie', 'episode')),
  tmdb_movie_id   INTEGER,
  tmdb_serie_id   INTEGER,
  season_number   INTEGER,
  episode_number  INTEGER,
  imdb_id         TEXT CHECK (imdb_id GLOB 'tt[0-9]*'),
  wikidata_id     TEXT CHECK (wikidata_id GLOB 'Q[1-9]*'),
  title_hint      TEXT NOT NULL,   -- as Plex shows it, in the library's language
  title_language  TEXT,            -- BCP 47, the Plex library language
  year            INTEGER,
  plex_rating_key INTEGER,         -- local only
  CHECK (kind = 'movie'   AND tmdb_serie_id IS NULL AND season_number IS NULL AND episode_number IS NULL
      OR kind = 'episode' AND tmdb_movie_id IS NULL),
  CHECK (tmdb_movie_id IS NOT NULL OR tmdb_serie_id IS NOT NULL OR imdb_id IS NOT NULL OR wikidata_id IS NOT NULL)
) STRICT;
CREATE UNIQUE INDEX work_movie   ON work (tmdb_movie_id) WHERE tmdb_movie_id IS NOT NULL;
CREATE UNIQUE INDEX work_episode ON work (tmdb_serie_id, season_number, episode_number) WHERE tmdb_serie_id IS NOT NULL;

CREATE TABLE copy (
  id               TEXT PRIMARY KEY CHECK (length(id) = 36),
  work_id          TEXT NOT NULL REFERENCES work (id),
  fingerprint      TEXT NOT NULL UNIQUE CHECK (length(fingerprint) = 64),
  part_count       INTEGER NOT NULL CHECK (part_count >= 1),
  duration_ms      INTEGER NOT NULL CHECK (duration_ms >= 0),
  width            INTEGER,
  height           INTEGER,
  fps              REAL,
  edition_hint     TEXT CHECK (length(edition_hint) <= 200),
  version_language TEXT,
  source           TEXT CHECK (source IN ('bluray', 'remux', 'dvd', 'web', 'tv', 'vhs', 'other'))
) STRICT;
CREATE INDEX copy_work ON copy (work_id);

CREATE TABLE part (
  id                 TEXT PRIMARY KEY CHECK (length(id) = 36),
  copy_id            TEXT NOT NULL REFERENCES copy (id),
  part_index         INTEGER NOT NULL CHECK (part_index >= 1),
  opensubtitles_hash TEXT NOT NULL CHECK (length(opensubtitles_hash) = 16),
  file_size          INTEGER NOT NULL CHECK (file_size >= 1),
  duration_ms        INTEGER NOT NULL CHECK (duration_ms >= 0),
  offset_ms          INTEGER NOT NULL CHECK (offset_ms >= 0),
  local_path         TEXT,   -- local only, never exported
  UNIQUE (copy_id, part_index)
) STRICT;
CREATE INDEX part_hash ON part (opensubtitles_hash, file_size);

CREATE TABLE submission (
  id                  TEXT PRIMARY KEY CHECK (length(id) = 36),
  copy_id             TEXT NOT NULL REFERENCES copy (id),
  created_at          TEXT NOT NULL,   -- ISO 8601 UTC, end of the run
  client_name         TEXT NOT NULL,
  client_version      TEXT NOT NULL,
  ocr_engine          TEXT NOT NULL,
  ocr_engine_version  TEXT NOT NULL,
  ocr_models          TEXT,
  parameters          TEXT CHECK (parameters IS NULL OR json_valid(parameters)),
  vocabulary_version  TEXT,
  licence             TEXT NOT NULL DEFAULT 'CC0-1.0' CHECK (licence = 'CC0-1.0'),
  has_evidence_frames INTEGER NOT NULL DEFAULT 0 CHECK (has_evidence_frames IN (0, 1)),
  status              TEXT NOT NULL DEFAULT 'running'
                      CHECK (status IN ('running', 'review', 'exported', 'discarded')),   -- local only
  exported_at         TEXT   -- local only
) STRICT;
CREATE INDEX submission_copy ON submission (copy_id);


-- Layers 1 and 2 --------------------------------------------------------------

CREATE TABLE segment (
  id              TEXT PRIMARY KEY CHECK (length(id) = 36),
  submission_id   TEXT NOT NULL REFERENCES submission (id) ON DELETE CASCADE,
  part_id         TEXT NOT NULL REFERENCES part (id),
  kind            TEXT NOT NULL CHECK (kind IN ('opening_titles', 'opening_credits_over_action', 'closing_credits',
                                                'post_credits_scene', 'recap', 'card')),
  start_ms        INTEGER NOT NULL CHECK (start_ms >= 0),
  end_ms          INTEGER NOT NULL CHECK (end_ms > start_ms),
  detected_by     TEXT NOT NULL CHECK (detected_by IN ('plex_marker', 'blackdetect', 'scene_change', 'text_detection', 'manual')),
  layout          TEXT NOT NULL CHECK (layout IN ('rolling', 'cards', 'graphic', 'crawl', 'mixed')),
  scroll_px_per_s REAL,
  CHECK (layout <> 'rolling' OR scroll_px_per_s IS NOT NULL)
) STRICT;
CREATE INDEX segment_submission ON segment (submission_id);

CREATE TABLE frame (
  id             TEXT PRIMARY KEY CHECK (length(id) = 36),
  segment_id     TEXT NOT NULL REFERENCES segment (id) ON DELETE CASCADE,
  timecode_ms    INTEGER NOT NULL CHECK (timecode_ms >= 0),
  phash          TEXT NOT NULL CHECK (length(phash) = 16),
  page_offset_px INTEGER,
  has_text       INTEGER NOT NULL DEFAULT 1 CHECK (has_text IN (0, 1)),
  evidence_path  TEXT,   -- local WebP; exported as frames/<id>.webp
  crop_x         INTEGER,
  crop_y         INTEGER,
  crop_w         INTEGER,
  crop_h         INTEGER
) STRICT;
CREATE INDEX frame_segment ON frame (segment_id, timecode_ms);

CREATE TABLE text_box (
  id             TEXT PRIMARY KEY CHECK (length(id) = 36),   -- local only: boxes carry no id in the bundle
  frame_id       TEXT NOT NULL REFERENCES frame (id) ON DELETE CASCADE,
  x              INTEGER NOT NULL CHECK (x >= 0),
  y              INTEGER NOT NULL CHECK (y >= 0),
  w              INTEGER NOT NULL CHECK (w >= 1),
  h              INTEGER NOT NULL CHECK (h >= 1),
  text           TEXT NOT NULL,
  confidence     REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  font_height_px INTEGER,
  is_upper_case  INTEGER CHECK (is_upper_case IN (0, 1)),
  is_bold        INTEGER CHECK (is_bold IN (0, 1))
) STRICT;
CREATE INDEX text_box_frame ON text_box (frame_id);

CREATE TABLE text_line (
  id         TEXT PRIMARY KEY CHECK (length(id) = 36),
  segment_id TEXT NOT NULL REFERENCES segment (id) ON DELETE CASCADE,
  y_page     INTEGER NOT NULL,
  x          INTEGER NOT NULL CHECK (x >= 0),
  w          INTEGER NOT NULL CHECK (w >= 1),
  h          INTEGER NOT NULL CHECK (h >= 1),
  text       TEXT NOT NULL CHECK (text <> ''),
  readings   INTEGER NOT NULL CHECK (readings >= 1),
  agreeing   INTEGER NOT NULL CHECK (agreeing BETWEEN 1 AND readings),
  confidence REAL NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  frame_ids  TEXT NOT NULL CHECK (json_valid(frame_ids) AND json_array_length(frame_ids) >= 1),
  first_ms   INTEGER NOT NULL CHECK (first_ms >= 0),
  last_ms    INTEGER NOT NULL CHECK (last_ms >= first_ms)
) STRICT;
CREATE INDEX text_line_segment ON text_line (segment_id, y_page);


-- Layer 3 ---------------------------------------------------------------------
-- Entities first: blocks and credits point to them.

CREATE TABLE person (
  id                    TEXT PRIMARY KEY CHECK (length(id) = 36),
  display_name          TEXT NOT NULL,
  is_private_individual INTEGER NOT NULL DEFAULT 0 CHECK (is_private_individual IN (0, 1)),
  tmdb_person_id        INTEGER,
  imdb_id               TEXT CHECK (imdb_id GLOB 'nm[0-9]*'),
  wikidata_id           TEXT CHECK (wikidata_id GLOB 'Q[1-9]*')
) STRICT;
CREATE INDEX person_tmdb ON person (tmdb_person_id);

CREATE TABLE company_class (
  code        TEXT PRIMARY KEY,
  label_en    TEXT NOT NULL,
  wikidata_id TEXT
) STRICT;

CREATE TABLE company (
  id              TEXT PRIMARY KEY CHECK (length(id) = 36),
  display_name    TEXT NOT NULL,
  company_class   TEXT,   -- company_class.code; no foreign key, the vocabulary is replaceable
  country         TEXT CHECK (country GLOB '[A-Z][A-Z]'),
  tmdb_company_id INTEGER,
  imdb_id         TEXT CHECK (imdb_id GLOB 'co[0-9]*'),
  wikidata_id     TEXT CHECK (wikidata_id GLOB 'Q[1-9]*')
) STRICT;
CREATE INDEX company_tmdb ON company (tmdb_company_id);

CREATE TABLE place (
  id           TEXT PRIMARY KEY CHECK (length(id) = 36),
  display_name TEXT NOT NULL,
  place_type   TEXT CHECK (place_type IN ('country', 'region', 'city', 'structure', 'studio_facility', 'nature')),
  wikidata_id  TEXT CHECK (wikidata_id GLOB 'Q[1-9]*')
) STRICT;

CREATE TABLE song (
  id          TEXT PRIMARY KEY CHECK (length(id) = 36),
  title_raw   TEXT NOT NULL,
  wikidata_id TEXT CHECK (wikidata_id GLOB 'Q[1-9]*')
) STRICT;

CREATE TABLE block (
  id               TEXT PRIMARY KEY CHECK (length(id) = 36),
  segment_id       TEXT NOT NULL REFERENCES segment (id) ON DELETE CASCADE,
  display_order    INTEGER NOT NULL CHECK (display_order >= 1),
  heading_raw      TEXT,
  block_type       TEXT NOT NULL CHECK (block_type IN ('cast', 'crew', 'unit', 'vendor_staff', 'songs', 'thanks', 'dedication',
                                                       'dubbing', 'locations', 'companies', 'legal', 'logos')),
  unit             TEXT,
  vendor_entity_id TEXT REFERENCES company (id),
  version_language TEXT,
  line_ids         TEXT NOT NULL CHECK (json_valid(line_ids) AND json_array_length(line_ids) >= 1)
) STRICT;
CREATE INDEX block_segment ON block (segment_id, display_order);

CREATE TABLE credit (
  id                    TEXT PRIMARY KEY CHECK (length(id) = 36),
  block_id              TEXT NOT NULL REFERENCES block (id) ON DELETE CASCADE,
  display_order         INTEGER NOT NULL CHECK (display_order >= 1),
  entity_kind           TEXT NOT NULL CHECK (entity_kind IN ('person', 'company', 'place', 'song', 'work', 'other')),
  name_raw              TEXT NOT NULL CHECK (name_raw <> ''),
  entity_id             TEXT,   -- person, company, place or song by entity_kind: checked by the exporter
  role_raw              TEXT,
  role_code             TEXT,   -- role.code
  role_modifiers        TEXT CHECK (role_modifiers IS NULL OR json_valid(role_modifiers)),
  role_target_entity_id TEXT REFERENCES person (id),
  song_id               TEXT REFERENCES song (id),
  character_raw         TEXT,
  language              TEXT,
  qualifier_raw         TEXT,
  line_ids              TEXT NOT NULL CHECK (json_valid(line_ids) AND json_array_length(line_ids) >= 1),
  parse_confidence      REAL CHECK (parse_confidence BETWEEN 0 AND 1),
  is_private_individual INTEGER NOT NULL DEFAULT 0 CHECK (is_private_individual IN (0, 1))
) STRICT;
CREATE INDEX credit_block  ON credit (block_id, display_order);
CREATE INDEX credit_entity ON credit (entity_id);


-- Layer 5: the vocabulary, downloaded from the master ---------------------------

CREATE TABLE role (
  code              TEXT PRIMARY KEY,   -- directing.first_assistant_director
  label_en          TEXT NOT NULL,
  applies_to        TEXT NOT NULL CHECK (applies_to IN ('person', 'company', 'place', 'song', 'work')),
  parent_code       TEXT,
  tmdb_department   TEXT,
  tmdb_job          TEXT,
  wikidata_property TEXT,
  wikidata_job_item TEXT,
  status            TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'proposed'))
) STRICT;

CREATE TABLE role_modifier (
  code     TEXT PRIMARY KEY,
  kind     TEXT NOT NULL CHECK (kind IN ('rank', 'unit', 'scope')),
  label_en TEXT NOT NULL
) STRICT;

CREATE TABLE role_alias (
  wording        TEXT NOT NULL,
  language       TEXT NOT NULL,
  role_code      TEXT NOT NULL REFERENCES role (code) ON DELETE CASCADE,
  role_modifiers TEXT CHECK (role_modifiers IS NULL OR json_valid(role_modifiers)),
  PRIMARY KEY (wording, language)
) STRICT;
