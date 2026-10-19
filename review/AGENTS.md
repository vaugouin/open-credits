# AGENTS.md - open-credits review stack

Small web app on the VPS for the pilot's hand-check of new lines (charter, decision 27 c): it shows the samples built by the client (`opencredits review`), one crop per line, and saves each verdict in `T_WC_OC_REVIEW` as it is clicked. Repository rules: [../AGENTS.md](../AGENTS.md). Deployment and use: [README.md](README.md).

## Rules

- Version: `VERSION` in this folder (shown on the sample list); bump PATCH with every change. The page is served with `Cache-Control: no-cache`, so no cache key is needed.
- Host network (`network_mode: host`), listening on `172.17.0.1:8196`: MariaDB is published on `127.0.0.1:3306` only, so a container on the `reverseproxy` bridge could not reach it. Nginx reaches the app at `172.17.0.1:8196`, which needs the ufw rules for the Docker bridges on port 8196 (README, step 4): without them the page stays blank and the app logs no request.
- Access control is basic auth at the reverse proxy only (`/oc-review/` block in `reverseproxy/sites-enabled/vaugouin-site.conf`, shared `vaugouin.htpasswd`). The app has no login: never publish port 8196 on a public address.
- Crops are frames of Philippe's copies: they live on the VPS in `~/docker/shared_data/oc-review/<sample>/`, never in git. The client sends them (`opencredits review --upload`, one zip to `POST api/samples/<sample>`); the mount is writable for that, and the container runs as uid 1000 (`debian`), who owns the folder. The upload accepts only `sample.json`, `verdicts.json` and `crops/NN.png`, and refuses an existing sample unless `replace`, which deletes its rows.
- Sample folder names are `<work folder>-<engine>-<lang>` (`alien-348-paddle-en`), lower case, digits and hyphens: the app refuses any other name.
- Submission bundles arrive at `POST api/submissions` (`opencredits send`): checked with `../schema/check_submission.py` (the image is built from the repository root to copy it in, see `Dockerfile`), then kept in `~/docker/shared_data/oc-review/incoming/submission-<id>.zip` for the importer. The app writes no OC table. The same bundle sent twice is answered `already`; another bundle with the same id is refused (409). `GET api/submissions` lists what waits.
- The importer (`importer.py`, service `oc-importer`, same image) is the only writer of the layer 0 to 2 tables: one bundle per transaction, moved to `imported/` or `rejected/` (with a `.txt`) afterwards. It connects with its own account, `oc_importer` (`IMPORT_DB_USER`/`IMPORT_DB_PASSWORD` in `.env`, rights in `../doc/sql/OC-importer-grants.sql`): SELECT, INSERT, UPDATE on the nine tables it writes, SELECT on `T_WC_TMDB_MOVIE` and `T_WC_TMDB_MOVIE_LANG`. A table it starts writing needs a line there. It refuses layer 3 and episodes for now; adding them means the grants, `load()`, and the movie page reader in `tmdb-front` (`lib/open-credits.inc.php`). Times: `CREATED_AT`, `SUBMITTED_AT` UTC; `DAT_CREAT`, `TIM_UPDATED` Paris (`TZ` in the compose file).
- The DDL is `../doc/sql/OC-review-table.sql` (Philippe runs it). The agent reads the scores with `ssh vps-agent run open-credits/doc/sql/oc-review-score.sql`; it cannot write the table.

## Commands

```bash
docker compose up -d --build        # on the VPS, in ~/docker/open-credits/review, after git pull
docker compose logs -f oc-review
docker compose logs -f oc-importer
python importer.py --once           # one pass (needs IMPORT_DB_USER, IMPORT_DB_PASSWORD, REVIEW_SHARED)
```
