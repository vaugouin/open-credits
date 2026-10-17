-- open-credits: the T_WC_OC_* tables as the server sees them (columns and indexes per table).
-- Rerun after any change to OC-tables.sql. Expected: 23 tables, all empty at creation.
SELECT t.TABLE_NAME,
       (SELECT COUNT(*) FROM information_schema.COLUMNS c
         WHERE c.TABLE_SCHEMA = t.TABLE_SCHEMA AND c.TABLE_NAME = t.TABLE_NAME) AS columns_count,
       (SELECT COUNT(DISTINCT s.INDEX_NAME) FROM information_schema.STATISTICS s
         WHERE s.TABLE_SCHEMA = t.TABLE_SCHEMA AND s.TABLE_NAME = t.TABLE_NAME) AS indexes_count,
       t.TABLE_ROWS, t.ENGINE, t.TABLE_COLLATION
FROM information_schema.TABLES t
WHERE t.TABLE_SCHEMA = DATABASE() AND t.TABLE_NAME LIKE 'T\_WC\_OC\_%' ESCAPE '|'
ORDER BY t.TABLE_NAME;
