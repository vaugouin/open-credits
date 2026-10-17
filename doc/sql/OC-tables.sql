-- =============================================================================
-- open-credits, master tables T_WC_OC_* in the T2S MariaDB (vaugouindb)
-- Logical model: doc/data-model.md. Client side: doc/sql/client-sqlite.sql.
--
-- Naming, from the logical (lower-case) names to these physical ones:
--   id                          -> ID_OC_<TABLE>           (UUID v7, primary key)
--   <table>_id                  -> ID_OC_<TABLE>           (link to another OC table)
--   tmdb_movie_id, tmdb_serie_id, tmdb_person_id, tmdb_company_id
--                               -> ID_MOVIE, ID_SERIE, ID_PERSON, ID_COMPANY (as in T_WC_TMDB_*)
--   imdb_id, wikidata_id        -> ID_IMDB, ID_WIKIDATA    (as in T_WC_TMDB_*)
--   entity_id                   -> ID_OC_ENTITY            (PERSON, COMPANY, PLACE or SONG, by ENTITY_KIND)
--   vendor_entity_id            -> ID_OC_COMPANY_VENDOR
--   role_target_entity_id       -> ID_OC_PERSON_TARGET
--   parent_role_id              -> ID_OC_ROLE_PARENT
--   character_id                -> ID_OC_CHARACTER         (no table yet: submission-format open point 1)
--   anything else               -> upper case              (name_raw -> NAME_RAW)
-- so T_WC_OC_PERSON.ID_PERSON joins T_WC_TMDB_PERSON.ID_PERSON directly.
--
-- Rules (data-model decision 1, AGENTS.md):
--   - no foreign key to any other T_WC_* table: TMDb, IMDb and Wikidata ids are plain values;
--   - no foreign key constraints between OC tables either, as everywhere in the ecosystem:
--     the importer checks every reference (schema/check_submission.py) and loads one bundle
--     per transaction; each link column has its index;
--   - UUID primary keys use the native UUID type. MariaDB >= 10.11.5 / 11.0.3 stores version 7
--     UUIDs without byte swapping (MDEV-29959), so they stay time-ordered in the index.
--     MariaDB has no UUID_v7() before 11.7: the client and the importer generate them;
--   - lists (frame_ids, line_ids, role_modifiers, source_credit_ids) are JSON arrays, as in
--     the submission format; JSON_TABLE reads them when a query needs them as rows;
--   - enumerations are varchar, with their values in the column comment;
--   - standard columns follow doc-tech "Structure type d'une table simple". ID_CREATOR,
--     ID_OWNER and ID_USER_UPDATED stay NULL: open-credits accounts live in T_WC_OC_CONTRIBUTOR.
--
-- Run once with a CREATE-privileged user (not the agent account):
--   ~/docker/tools/runsqlvaugouindb.sh ~/docker/open-credits/doc/sql/OC-tables.sql
-- =============================================================================


-- -----------------------------------------------------------------------------
-- Layer 0: work, edition, copy, part, submission, contributor
-- -----------------------------------------------------------------------------

CREATE TABLE `T_WC_OC_WORK` (
  `ID_OC_WORK` uuid NOT NULL,
  `KIND` varchar(10) NOT NULL COMMENT 'movie, episode',
  `ID_MOVIE` int(11) DEFAULT NULL COMMENT 'TMDb movie id, movies only',
  `ID_SERIE` int(11) DEFAULT NULL COMMENT 'TMDb series id, episodes only',
  `SEASON_NUMBER` int(5) DEFAULT NULL,
  `EPISODE_NUMBER` int(5) DEFAULT NULL,
  `ID_IMDB` varchar(20) DEFAULT NULL COMMENT 'tt...',
  `ID_WIKIDATA` varchar(50) DEFAULT NULL COMMENT 'Q...',
  `ORIGINAL_TITLE` varchar(250) DEFAULT NULL COMMENT 'from TMDb, or Wikidata P1476; never from the submission. Episodes: the episode title when it has one',
  `ORIGINAL_LANGUAGE` varchar(20) DEFAULT NULL COMMENT 'BCP 47',
  `TITLE_EN` varchar(250) DEFAULT NULL COMMENT 'English title for display',
  `SERIE_ORIGINAL_NAME` varchar(250) DEFAULT NULL COMMENT 'episodes only',
  `YEAR` int(5) DEFAULT NULL COMMENT 'release year, or first air date of the episode',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_WORK`),
  UNIQUE KEY `UK_MOVIE` (`ID_MOVIE`),
  UNIQUE KEY `UK_EPISODE` (`ID_SERIE`,`SEASON_NUMBER`,`EPISODE_NUMBER`),
  KEY `KIND` (`KIND`),
  KEY `ID_IMDB` (`ID_IMDB`),
  KEY `ID_WIKIDATA` (`ID_WIKIDATA`),
  KEY `DELETED` (`DELETED`),
  KEY `DAT_CREAT` (`DAT_CREAT`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits: a movie or an episode, what the credits belong to';

CREATE TABLE `T_WC_OC_EDITION` (
  `ID_OC_EDITION` uuid NOT NULL,
  `ID_OC_WORK` uuid NOT NULL,
  `LABEL` varchar(20) NOT NULL COMMENT 'theatrical, directors_cut, extended, tv_cut, unrated, other',
  `LABEL_TEXT` varchar(200) DEFAULT NULL COMMENT 'free text, for other',
  `NOMINAL_RUNTIME_MS` int(11) DEFAULT NULL,
  `STATUS` varchar(10) NOT NULL DEFAULT 'proposed' COMMENT 'proposed, confirmed',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_EDITION`),
  KEY `ID_OC_WORK` (`ID_OC_WORK`),
  KEY `STATUS` (`STATUS`),
  KEY `DELETED` (`DELETED`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits: a cut of a work';

CREATE TABLE `T_WC_OC_COPY` (
  `ID_OC_COPY` uuid NOT NULL,
  `ID_OC_WORK` uuid NOT NULL,
  `ID_OC_EDITION` uuid DEFAULT NULL COMMENT 'empty until the copy is grouped',
  `FINGERPRINT` char(64) NOT NULL COMMENT 'SHA-256 of the lines <opensubtitles_hash>:<file_size> in part order',
  `PART_COUNT` int(5) NOT NULL,
  `DURATION_MS` int(11) NOT NULL COMMENT 'sum of the parts',
  `WIDTH` int(5) DEFAULT NULL,
  `HEIGHT` int(5) DEFAULT NULL,
  `FPS` double DEFAULT NULL,
  `EDITION_HINT` varchar(200) DEFAULT NULL COMMENT 'Plex {edition-...} tag, FILE_EDITION',
  `VERSION_LANGUAGE` varchar(20) DEFAULT NULL COMMENT 'BCP 47, language of the version the credits come from',
  `SOURCE` varchar(10) DEFAULT NULL COMMENT 'bluray, remux, dvd, web, tv, vhs, other',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_COPY`),
  UNIQUE KEY `UK_FINGERPRINT` (`FINGERPRINT`),
  KEY `ID_OC_WORK` (`ID_OC_WORK`),
  KEY `ID_OC_EDITION` (`ID_OC_EDITION`),
  KEY `DELETED` (`DELETED`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits: one encode of an edition, shared by everyone who holds the same files';

CREATE TABLE `T_WC_OC_PART` (
  `ID_OC_PART` uuid NOT NULL,
  `ID_OC_COPY` uuid NOT NULL,
  `PART_INDEX` int(5) NOT NULL COMMENT '1, 2, 3...',
  `OPENSUBTITLES_HASH` char(16) NOT NULL COMMENT 'joins T_WC_TMDB_PLEX_MEDIA_PART.OPENSUBTITLE_HASH',
  `FILE_SIZE` bigint(15) NOT NULL COMMENT 'joins T_WC_TMDB_PLEX_MEDIA_PART.PART_SIZE',
  `DURATION_MS` int(11) NOT NULL,
  `OFFSET_MS` int(11) NOT NULL COMMENT 'start in the copy',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_PART`),
  UNIQUE KEY `UK_COPY_PART` (`ID_OC_COPY`,`PART_INDEX`),
  KEY `OPENSUBTITLES_HASH` (`OPENSUBTITLES_HASH`,`FILE_SIZE`),
  KEY `DELETED` (`DELETED`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits: one file of a copy, identified by its content; the path is never stored';

CREATE TABLE `T_WC_OC_CONTRIBUTOR` (
  `ID_OC_CONTRIBUTOR` uuid NOT NULL,
  `USERNAME` varchar(100) NOT NULL,
  `REPUTATION` int(11) NOT NULL DEFAULT 0,
  `ROLE` varchar(20) NOT NULL DEFAULT 'contributor' COMMENT 'contributor, moderator',
  `TMDB_USERNAME` varchar(100) DEFAULT NULL,
  `WIKIDATA_USERNAME` varchar(100) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_CONTRIBUTOR`),
  UNIQUE KEY `UK_USERNAME` (`USERNAME`),
  KEY `ROLE` (`ROLE`),
  KEY `DELETED` (`DELETED`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits: an account, one per person (authentication not modelled yet)';

CREATE TABLE `T_WC_OC_SUBMISSION` (
  `ID_OC_SUBMISSION` uuid NOT NULL COMMENT 'the client UUID, kept',
  `ID_OC_CONTRIBUTOR` uuid NOT NULL COMMENT 'from the authenticated upload, never from the bundle',
  `ID_OC_COPY` uuid NOT NULL,
  `FORMAT_VERSION` varchar(20) NOT NULL COMMENT 'of submission.json',
  `CLIENT_NAME` varchar(100) NOT NULL,
  `CLIENT_VERSION` varchar(50) NOT NULL,
  `OCR_ENGINE` varchar(100) NOT NULL,
  `OCR_ENGINE_VERSION` varchar(50) NOT NULL,
  `OCR_MODELS` varchar(250) DEFAULT NULL,
  `PARAMETERS` json DEFAULT NULL,
  `VOCABULARY_VERSION` varchar(50) DEFAULT NULL,
  `TITLE_HINT` varchar(250) DEFAULT NULL COMMENT 'as the client found it, kept for the sanity check only',
  `TITLE_LANGUAGE` varchar(20) DEFAULT NULL,
  `HAS_EVIDENCE_FRAMES` tinyint(1) NOT NULL DEFAULT 0,
  `CREATED_AT` datetime NOT NULL COMMENT 'end of the run on the client, UTC',
  `SUBMITTED_AT` datetime NOT NULL COMMENT 'arrival on the master, UTC',
  `STATUS` varchar(20) NOT NULL DEFAULT 'received' COMMENT 'received, parsed, published, rolled_back',
  `LICENCE` varchar(20) NOT NULL DEFAULT 'CC0-1.0',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_SUBMISSION`),
  KEY `ID_OC_CONTRIBUTOR` (`ID_OC_CONTRIBUTOR`),
  KEY `ID_OC_COPY` (`ID_OC_COPY`),
  KEY `STATUS` (`STATUS`),
  KEY `SUBMITTED_AT` (`SUBMITTED_AT`),
  KEY `DELETED` (`DELETED`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits: one run of the client on one copy';


-- -----------------------------------------------------------------------------
-- Layers 1 and 2: segments, frames, OCR
-- -----------------------------------------------------------------------------

CREATE TABLE `T_WC_OC_SEGMENT` (
  `ID_OC_SEGMENT` uuid NOT NULL,
  `ID_OC_SUBMISSION` uuid NOT NULL,
  `ID_OC_PART` uuid NOT NULL,
  `KIND` varchar(30) NOT NULL COMMENT 'opening_titles, opening_credits_over_action, closing_credits, post_credits_scene, recap, card',
  `START_MS` int(11) NOT NULL COMMENT 'within the part',
  `END_MS` int(11) NOT NULL,
  `DETECTED_BY` varchar(20) NOT NULL COMMENT 'plex_marker, blackdetect, scene_change, text_detection, manual',
  `LAYOUT` varchar(10) NOT NULL COMMENT 'rolling, cards, graphic, crawl, mixed',
  `SCROLL_PX_PER_S` double DEFAULT NULL COMMENT 'rolling credits only',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_SEGMENT`),
  KEY `ID_OC_SUBMISSION` (`ID_OC_SUBMISSION`),
  KEY `ID_OC_PART` (`ID_OC_PART`),
  KEY `KIND` (`KIND`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 1: a stretch of a part that carries credits';

CREATE TABLE `T_WC_OC_FRAME` (
  `ID_OC_FRAME` uuid NOT NULL,
  `ID_OC_SEGMENT` uuid NOT NULL,
  `TIMECODE_MS` int(11) NOT NULL COMMENT 'within the part',
  `PHASH` char(16) NOT NULL COMMENT '64-bit perceptual hash, hex',
  `PAGE_OFFSET_PX` int(11) DEFAULT NULL COMMENT 'rolling credits: position on the virtual page',
  `HAS_TEXT` tinyint(1) NOT NULL DEFAULT 1,
  `EVIDENCE_PATH` varchar(250) DEFAULT NULL COMMENT 'where the master stores the WebP sent in the bundle, if any',
  `CROP_X` int(5) DEFAULT NULL,
  `CROP_Y` int(5) DEFAULT NULL,
  `CROP_W` int(5) DEFAULT NULL,
  `CROP_H` int(5) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_FRAME`),
  KEY `ID_OC_SEGMENT` (`ID_OC_SEGMENT`,`TIMECODE_MS`),
  KEY `PHASH` (`PHASH`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 1: one image read by the OCR';

CREATE TABLE `T_WC_OC_TEXT_BOX` (
  `ID_OC_TEXT_BOX` uuid NOT NULL COMMENT 'generated by the importer: text boxes carry no id in the bundle',
  `ID_OC_FRAME` uuid NOT NULL,
  `X` int(5) NOT NULL,
  `Y` int(5) NOT NULL,
  `W` int(5) NOT NULL,
  `H` int(5) NOT NULL,
  `TEXT` varchar(1000) NOT NULL COMMENT 'as read',
  `CONFIDENCE` float NOT NULL COMMENT '0 to 1',
  `FONT_HEIGHT_PX` int(5) DEFAULT NULL,
  `IS_UPPER_CASE` tinyint(1) DEFAULT NULL,
  `IS_BOLD` tinyint(1) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL COMMENT 'order of the box in the frame',
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_TEXT_BOX`),
  KEY `ID_OC_FRAME` (`ID_OC_FRAME`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 2a: one line box read on one frame';

CREATE TABLE `T_WC_OC_TEXT_LINE` (
  `ID_OC_TEXT_LINE` uuid NOT NULL,
  `ID_OC_SEGMENT` uuid NOT NULL,
  `Y_PAGE` int(11) NOT NULL COMMENT 'on the virtual page',
  `X` int(5) NOT NULL COMMENT 'gives the column',
  `W` int(5) NOT NULL,
  `H` int(5) NOT NULL,
  `TEXT` varchar(1000) NOT NULL COMMENT 'voted reading',
  `READINGS` int(5) NOT NULL,
  `AGREEING` int(5) NOT NULL,
  `CONFIDENCE` float NOT NULL,
  `FRAME_IDS` json NOT NULL COMMENT 'ID_OC_FRAME list: the evidence chain',
  `FIRST_MS` int(11) NOT NULL COMMENT 'Wikidata P4895 time index',
  `LAST_MS` int(11) NOT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_TEXT_LINE`),
  KEY `ID_OC_SEGMENT` (`ID_OC_SEGMENT`,`Y_PAGE`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 2b: a line rebuilt across frames, the pivot of the model';


-- -----------------------------------------------------------------------------
-- Layer 3: blocks, credits, entities
-- -----------------------------------------------------------------------------

CREATE TABLE `T_WC_OC_BLOCK` (
  `ID_OC_BLOCK` uuid NOT NULL,
  `ID_OC_SEGMENT` uuid NOT NULL,
  `HEADING_RAW` varchar(500) DEFAULT NULL COMMENT 'as on screen; empty for the first cast list',
  `BLOCK_TYPE` varchar(20) NOT NULL COMMENT 'cast, crew, unit, vendor_staff, songs, thanks, dedication, dubbing, locations, companies, legal, logos',
  `UNIT` varchar(200) DEFAULT NULL COMMENT 'main, second_unit, additional_photography, aerial, or a place as written',
  `ID_OC_COMPANY_VENDOR` uuid DEFAULT NULL COMMENT 'the company whose staff the block lists',
  `VERSION_LANGUAGE` varchar(20) DEFAULT NULL COMMENT 'dubbing blocks',
  `LINE_IDS` json NOT NULL COMMENT 'ID_OC_TEXT_LINE list',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(11) NOT NULL COMMENT 'order on screen',
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_BLOCK`),
  KEY `ID_OC_SEGMENT` (`ID_OC_SEGMENT`,`DISPLAY_ORDER`),
  KEY `BLOCK_TYPE` (`BLOCK_TYPE`),
  KEY `ID_OC_COMPANY_VENDOR` (`ID_OC_COMPANY_VENDOR`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 3a: a heading and the credits under it';

CREATE TABLE `T_WC_OC_CREDIT` (
  `ID_OC_CREDIT` uuid NOT NULL,
  `ID_OC_BLOCK` uuid NOT NULL,
  `ENTITY_KIND` varchar(10) NOT NULL COMMENT 'person, company, place, song, work, other',
  `NAME_RAW` varchar(1000) NOT NULL COMMENT 'Wikidata P1932, as credited',
  `ID_OC_ENTITY` uuid DEFAULT NULL COMMENT 'T_WC_OC_PERSON, _COMPANY, _PLACE or _SONG by ENTITY_KIND; empty until resolved',
  `ROLE_RAW` varchar(500) DEFAULT NULL COMMENT 'Wikidata P13187, as credited',
  `ID_OC_ROLE` uuid DEFAULT NULL COMMENT 'the base job',
  `ROLE_MODIFIERS` json DEFAULT NULL COMMENT 'T_WC_OC_ROLE_MODIFIER.CODE list, in on-screen order',
  `ID_OC_PERSON_TARGET` uuid DEFAULT NULL COMMENT 'assistant to, double for',
  `ID_OC_SONG` uuid DEFAULT NULL COMMENT 'when the credit belongs to a song',
  `CHARACTER_RAW` varchar(500) DEFAULT NULL COMMENT 'Wikidata P4633',
  `ID_OC_CHARACTER` uuid DEFAULT NULL COMMENT 'Wikidata P453; no table yet',
  `LANGUAGE` varchar(20) DEFAULT NULL COMMENT 'Wikidata P407, dubbing',
  `QUALIFIER_RAW` varchar(250) DEFAULT NULL COMMENT 'as, with the participation of, and',
  `LINE_IDS` json NOT NULL COMMENT 'ID_OC_TEXT_LINE list',
  `PARSE_CONFIDENCE` float DEFAULT NULL,
  `IS_PRIVATE_INDIVIDUAL` tinyint(1) NOT NULL DEFAULT 0 COMMENT 'charter decision 10: kept out of public views and contributions',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(11) NOT NULL COMMENT 'Wikidata P1545',
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_CREDIT`),
  KEY `ID_OC_BLOCK` (`ID_OC_BLOCK`,`DISPLAY_ORDER`),
  KEY `ID_OC_ENTITY` (`ID_OC_ENTITY`),
  KEY `ID_OC_ROLE` (`ID_OC_ROLE`),
  KEY `ID_OC_PERSON_TARGET` (`ID_OC_PERSON_TARGET`),
  KEY `ID_OC_SONG` (`ID_OC_SONG`),
  KEY `ENTITY_KIND` (`ENTITY_KIND`),
  KEY `IS_PRIVATE_INDIVIDUAL` (`IS_PRIVATE_INDIVIDUAL`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 3b: one assertion, an entity in a role, with its on-screen wording';

CREATE TABLE `T_WC_OC_PERSON` (
  `ID_OC_PERSON` uuid NOT NULL,
  `DISPLAY_NAME` varchar(250) NOT NULL,
  `IS_PRIVATE_INDIVIDUAL` tinyint(1) NOT NULL DEFAULT 0,
  `ID_PERSON` int(11) DEFAULT NULL COMMENT 'TMDb person id',
  `ID_IMDB` varchar(20) DEFAULT NULL COMMENT 'nm...',
  `ID_WIKIDATA` varchar(50) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_PERSON`),
  KEY `DISPLAY_NAME` (`DISPLAY_NAME`),
  KEY `ID_PERSON` (`ID_PERSON`),
  KEY `ID_IMDB` (`ID_IMDB`),
  KEY `ID_WIKIDATA` (`ID_WIKIDATA`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 3c: a person';

CREATE TABLE `T_WC_OC_COMPANY` (
  `ID_OC_COMPANY` uuid NOT NULL,
  `DISPLAY_NAME` varchar(250) NOT NULL,
  `COMPANY_CLASS` varchar(50) DEFAULT NULL COMMENT 'T_WC_OC_COMPANY_CLASS.CODE',
  `COUNTRY` char(2) DEFAULT NULL COMMENT 'ISO 3166-1 alpha-2',
  `ID_COMPANY` int(11) DEFAULT NULL COMMENT 'TMDb company id',
  `ID_IMDB` varchar(20) DEFAULT NULL COMMENT 'co...',
  `ID_WIKIDATA` varchar(50) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_COMPANY`),
  KEY `DISPLAY_NAME` (`DISPLAY_NAME`),
  KEY `COMPANY_CLASS` (`COMPANY_CLASS`),
  KEY `ID_COMPANY` (`ID_COMPANY`),
  KEY `ID_IMDB` (`ID_IMDB`),
  KEY `ID_WIKIDATA` (`ID_WIKIDATA`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 3c: a company';

CREATE TABLE `T_WC_OC_PLACE` (
  `ID_OC_PLACE` uuid NOT NULL,
  `DISPLAY_NAME` varchar(250) NOT NULL,
  `PLACE_TYPE` varchar(20) DEFAULT NULL COMMENT 'country, region, city, structure, studio_facility, nature',
  `ID_WIKIDATA` varchar(50) DEFAULT NULL COMMENT 'P131 gives the hierarchy',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_PLACE`),
  KEY `DISPLAY_NAME` (`DISPLAY_NAME`),
  KEY `ID_WIKIDATA` (`ID_WIKIDATA`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 3c: a place (filming location, studio facility)';

CREATE TABLE `T_WC_OC_SONG` (
  `ID_OC_SONG` uuid NOT NULL,
  `TITLE_RAW` varchar(500) NOT NULL COMMENT 'as credited',
  `ID_WIKIDATA` varchar(50) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_SONG`),
  KEY `TITLE_RAW` (`TITLE_RAW`),
  KEY `ID_WIKIDATA` (`ID_WIKIDATA`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 3c: a song; its own credits point to it through T_WC_OC_CREDIT.ID_OC_SONG';


-- -----------------------------------------------------------------------------
-- Layer 4: consolidated credits, history, reports
-- -----------------------------------------------------------------------------

CREATE TABLE `T_WC_OC_CONSOLIDATED_CREDIT` (
  `ID_OC_CONSOLIDATED_CREDIT` uuid NOT NULL,
  `ID_OC_WORK` uuid NOT NULL,
  `ID_OC_ROLE` uuid DEFAULT NULL,
  `ENTITY_KIND` varchar(10) NOT NULL COMMENT 'person, company, place, song, work, other',
  `ID_OC_ENTITY` uuid DEFAULT NULL COMMENT 'by ENTITY_KIND',
  `NAME_DISPLAY` varchar(500) NOT NULL,
  `CHARACTER_DISPLAY` varchar(500) DEFAULT NULL,
  `SUPPORT` int(11) NOT NULL DEFAULT 1 COMMENT 'submissions that carry it',
  `SUPPORT_COPIES` int(11) NOT NULL DEFAULT 1 COMMENT 'distinct copies that carry it',
  `SCORE` float DEFAULT NULL COMMENT 'agreement weighted by reputation',
  `STATUS` varchar(10) NOT NULL DEFAULT 'proposed' COMMENT 'proposed, confirmed, locked, rejected',
  `SOURCE_CREDIT_IDS` json NOT NULL COMMENT 'ID_OC_CREDIT list: the evidence chain',
  `IS_PRIVATE_INDIVIDUAL` tinyint(1) NOT NULL DEFAULT 0,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(11) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_CONSOLIDATED_CREDIT`),
  KEY `ID_OC_WORK` (`ID_OC_WORK`,`DISPLAY_ORDER`),
  KEY `ID_OC_ROLE` (`ID_OC_ROLE`),
  KEY `ID_OC_ENTITY` (`ID_OC_ENTITY`),
  KEY `STATUS` (`STATUS`),
  KEY `IS_PRIVATE_INDIVIDUAL` (`IS_PRIVATE_INDIVIDUAL`),
  KEY `DELETED` (`DELETED`),
  KEY `TIM_UPDATED` (`TIM_UPDATED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 4: one distinct credit of a work, computed from the submissions';

CREATE TABLE `T_WC_OC_HISTORY` (
  `ID_OC_HISTORY` uuid NOT NULL,
  `ID_OC_CONSOLIDATED_CREDIT` uuid NOT NULL,
  `ID_OC_CONTRIBUTOR` uuid NOT NULL,
  `EDITED_AT` datetime NOT NULL,
  `VALUE_BEFORE` json DEFAULT NULL COMMENT 'the consolidated credit before the edit',
  `VALUE_AFTER` json DEFAULT NULL,
  `REASON` varchar(1000) DEFAULT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_HISTORY`),
  KEY `ID_OC_CONSOLIDATED_CREDIT` (`ID_OC_CONSOLIDATED_CREDIT`,`EDITED_AT`),
  KEY `ID_OC_CONTRIBUTOR` (`ID_OC_CONTRIBUTOR`),
  KEY `EDITED_AT` (`EDITED_AT`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 4: every edit of a consolidated credit';

CREATE TABLE `T_WC_OC_REPORT` (
  `ID_OC_REPORT` uuid NOT NULL,
  `ID_OC_WORK` uuid DEFAULT NULL,
  `ID_OC_CONSOLIDATED_CREDIT` uuid DEFAULT NULL,
  `ID_OC_CONTRIBUTOR` uuid NOT NULL COMMENT 'who files it',
  `REASON` varchar(1000) NOT NULL,
  `IS_PUBLIC` tinyint(1) NOT NULL DEFAULT 1,
  `STATUS` varchar(10) NOT NULL DEFAULT 'open' COMMENT 'open, accepted, rejected',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_REPORT`),
  KEY `ID_OC_WORK` (`ID_OC_WORK`),
  KEY `ID_OC_CONSOLIDATED_CREDIT` (`ID_OC_CONSOLIDATED_CREDIT`),
  KEY `ID_OC_CONTRIBUTOR` (`ID_OC_CONTRIBUTOR`),
  KEY `STATUS` (`STATUS`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 4: a report on a work or a consolidated credit';


-- -----------------------------------------------------------------------------
-- Layer 5: the vocabulary
-- -----------------------------------------------------------------------------

CREATE TABLE `T_WC_OC_ROLE` (
  `ID_OC_ROLE` uuid NOT NULL,
  `CODE` varchar(100) NOT NULL COMMENT 'directing.first_assistant_director',
  `LABEL_EN` varchar(250) NOT NULL,
  `APPLIES_TO` varchar(10) NOT NULL COMMENT 'person, company, place, song, work',
  `ID_OC_ROLE_PARENT` uuid DEFAULT NULL COMMENT 'first assistant director -> assistant director -> director',
  `TMDB_DEPARTMENT` varchar(50) DEFAULT NULL COMMENT 'as in T_WC_TMDB_PERSON_MOVIE.CREW_DEPARTMENT',
  `TMDB_JOB` varchar(100) DEFAULT NULL COMMENT 'as in T_WC_TMDB_PERSON_MOVIE.CREW_JOB',
  `TMDB_CREDIT_COUNT` int(11) DEFAULT NULL COMMENT 'seeding weight: credits using this job in TMDb',
  `WIKIDATA_PROPERTY` varchar(20) DEFAULT NULL COMMENT 'dedicated property, or P3092',
  `WIKIDATA_JOB_ITEM` varchar(50) DEFAULT NULL COMMENT 'P3831 value when the property is P3092',
  `STATUS` varchar(10) NOT NULL DEFAULT 'active' COMMENT 'active, proposed',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_ROLE`),
  UNIQUE KEY `UK_CODE` (`CODE`),
  KEY `ID_OC_ROLE_PARENT` (`ID_OC_ROLE_PARENT`),
  KEY `TMDB_JOB` (`TMDB_DEPARTMENT`,`TMDB_JOB`),
  KEY `WIKIDATA_JOB_ITEM` (`WIKIDATA_JOB_ITEM`),
  KEY `STATUS` (`STATUS`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 5: base jobs, company roles and place roles, mapped to TMDb and Wikidata';

CREATE TABLE `T_WC_OC_ROLE_MODIFIER` (
  `ID_OC_ROLE_MODIFIER` uuid NOT NULL,
  `CODE` varchar(50) NOT NULL COMMENT 'key, second, assistant, additional...',
  `KIND` varchar(10) NOT NULL COMMENT 'rank, unit, scope',
  `LABEL_EN` varchar(100) NOT NULL,
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_ROLE_MODIFIER`),
  UNIQUE KEY `UK_CODE` (`CODE`),
  KEY `KIND` (`KIND`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 5: modifiers composed with a base job';

CREATE TABLE `T_WC_OC_ROLE_ALIAS` (
  `ID_OC_ROLE_ALIAS` uuid NOT NULL,
  `ID_OC_ROLE` uuid NOT NULL,
  `WORDING` varchar(250) NOT NULL COMMENT 'as seen on screen',
  `LANGUAGE` varchar(20) NOT NULL COMMENT 'BCP 47',
  `ROLE_MODIFIERS` json DEFAULT NULL COMMENT 'T_WC_OC_ROLE_MODIFIER.CODE list implied by the wording',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_ROLE_ALIAS`),
  UNIQUE KEY `UK_WORDING` (`WORDING`,`LANGUAGE`),
  KEY `ID_OC_ROLE` (`ID_OC_ROLE`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 5: the on-screen wordings that map to a role, in every language';

CREATE TABLE `T_WC_OC_COMPANY_CLASS` (
  `CODE` varchar(50) NOT NULL COMMENT 'film_production_company, vfx_company...',
  `LABEL_EN` varchar(100) NOT NULL,
  `ID_WIKIDATA` varchar(50) DEFAULT NULL COMMENT 'empty when Wikidata lacks the class',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`CODE`),
  KEY `ID_WIKIDATA` (`ID_WIKIDATA`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits layer 5: classes of company entities, mapped to Wikidata';
