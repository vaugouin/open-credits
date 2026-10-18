-- =============================================================================
-- open-credits pilot: hand-check verdicts on sampled OCR lines (charter, decision 27 c)
-- Written by the review stack (review/), one row per sampled line, verdict saved on each click.
-- DDL: run by Philippe (runsqlvaugouindb.sh). Also in OC-tables.sql.
-- =============================================================================

CREATE TABLE IF NOT EXISTS `T_WC_OC_REVIEW` (
  `ID_OC_REVIEW` uuid NOT NULL,
  `SAMPLE` varchar(100) NOT NULL COMMENT 'sample folder name: <work folder>-<engine>-<lang>, e.g. alien-348-paddle-en',
  `ID_MOVIE` int(11) DEFAULT NULL COMMENT 'TMDb movie id of the title',
  `TAG` varchar(30) NOT NULL COMMENT 'engine-lang of the run, e.g. paddle-en',
  `ITEM` int(5) NOT NULL COMMENT 'line number in the sample, 1 to 50',
  `LINE_TEXT` varchar(500) NOT NULL COMMENT 'text as the client wrote it (after cleaning)',
  `LINE_RAW` varchar(500) DEFAULT NULL COMMENT 'voted text before cleaning, when cleaning changed it',
  `LINE_KIND` varchar(10) NOT NULL COMMENT 'roll or card',
  `WINDOW_NAME` varchar(30) NOT NULL COMMENT 'time window folder, e.g. w6800-6996',
  `FRAME_T` int(11) NOT NULL COMMENT 'second of the frame the crop comes from',
  `VERDICT` varchar(10) DEFAULT NULL COMMENT 'exact, minor, wrong, noise; NULL until judged',
  `NOTE` varchar(500) DEFAULT NULL COMMENT 'what the screen shows, when different',
  `DELETED` int(5) DEFAULT 0,
  `DISPLAY_ORDER` int(5) DEFAULT NULL,
  `ID_CREATOR` int(5) DEFAULT NULL,
  `DAT_CREAT` date DEFAULT NULL,
  `ID_OWNER` int(5) DEFAULT NULL,
  `TIM_UPDATED` datetime DEFAULT NULL,
  `ID_USER_UPDATED` int(5) DEFAULT NULL,
  PRIMARY KEY (`ID_OC_REVIEW`),
  UNIQUE KEY `SAMPLE_ITEM` (`SAMPLE`, `ITEM`),
  KEY `ID_MOVIE` (`ID_MOVIE`),
  KEY `VERDICT` (`VERDICT`),
  KEY `DELETED` (`DELETED`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='open-credits pilot: hand-check verdict on a sampled OCR line';
