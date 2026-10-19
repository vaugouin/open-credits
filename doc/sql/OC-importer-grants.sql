-- open-credits importer (review/importer.py, service oc-importer): the rights of its own database account
-- (technology-choices, section 4: write on T_WC_OC_* only, read on the tables it joins).
-- Run by Philippe after creating the account with the password of review/.env (IMPORT_DB_PASSWORD), which
-- never enters git:
--   CREATE USER 'oc_importer'@'%' IDENTIFIED BY '<password>';
-- '%' because the containers reach MariaDB through its port published on 127.0.0.1, from a Docker bridge address.

GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_WORK TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_COPY TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_PART TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_CONTRIBUTOR TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_SUBMISSION TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_SEGMENT TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_FRAME TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_TEXT_BOX TO 'oc_importer'@'%';
GRANT SELECT, INSERT, UPDATE ON vaugouindb.T_WC_OC_TEXT_LINE TO 'oc_importer'@'%';
-- the work's titles come from TMDb, never from the bundle
GRANT SELECT ON vaugouindb.T_WC_TMDB_MOVIE TO 'oc_importer'@'%';
GRANT SELECT ON vaugouindb.T_WC_TMDB_MOVIE_LANG TO 'oc_importer'@'%';

SHOW GRANTS FOR 'oc_importer'@'%';
