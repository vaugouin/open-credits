# open-credits review

Online hand-check of the lines the client reads that TMDb does not have (pilot criterion, charter decision 27 c). The page lists the samples; a sample shows 50 lines, each with a crop of a frame where it is on screen, and each verdict (exact, minor, wrong, noise) and note is saved in MariaDB (`T_WC_OC_REVIEW`) as soon as it is clicked. URL: `https://www.vaugouin.com/oc-review/` (basic auth), one sample at `?s=<sample>`.

## Adding a sample

One command on the PC builds the sample in the title's work folder and sends it to the page, as one zip over HTTPS, under the name `<work folder>-<engine>-<lang>`. The login is the page's basic auth, read from two environment variables:

```powershell
$env:OC_REVIEW_USER = "..."; $env:OC_REVIEW_PASSWORD = "..."
uv run opencredits review --work U:/open-credits/work/alien-348 --tag paddle-en `
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 348 --upload
```

Without `--tmdb-credits`, `--upload` sends the sample already built. A sample already online is refused; `--replace` redoes it and drops its verdicts. A `verdicts.json` saved by the offline page (`review-<tag>/index.html`) in the sample folder travels with it and fills the verdicts not yet given.

The app accepts only `sample.json`, `verdicts.json` and `crops/NN.png` in the zip (30 MB at most), and writes it to `~/docker/shared_data/oc-review/<sample>/` on the VPS.

## Receiving submission bundles

The same app receives the client's submission bundles (`opencredits send`, or `opencredits worker --send`) at `POST /oc-review/api/submissions`, behind the same basic auth. Each bundle is checked against the format (`schema/check_submission.py`); a valid one is kept as `~/docker/shared_data/oc-review/incoming/submission-<id>.zip` for the importer, an invalid one is refused with its first 20 errors. `GET /oc-review/api/submissions` gives the counts (waiting, imported, rejected) and the latest bundles with their state, and the reason of each rejection.

## The importer

`importer.py` runs as a second service, `oc-importer`, from the same image. Every minute it takes the bundles in `incoming/`, checks each again, and loads it into the `T_WC_OC_*` tables in one transaction: the work (titles from `T_WC_TMDB_MOVIE`, never from the bundle), the copy and its parts (shared by fingerprint), then the submission, segments, frames, text boxes and text lines. A loaded bundle moves to `imported/`, a refused one to `rejected/` with a `.txt` giving the reason; when the database is away, bundles wait in `incoming/`. To load a rejected bundle again, move it back to `incoming/`.

Not imported yet: blocks, credits and entities (layer 3; the client does not send them, and a bundle that does is refused), and episodes. Uploads carry no identity, so every submission is credited to `IMPORT_CONTRIBUTOR` (`vaugouin`). A title hint or year that disagrees with TMDb is logged, not refused: the hint is the library's title, often a translation.

The movie page of the site shows what is loaded, in private mode (`tmdb-front` 1.0.17, section *Credits read on screen*).

```bash
docker compose logs -f oc-importer      # one line per bundle: work, segments, frames, boxes, lines, or the rejection
```

`GET /oc-review/api/collections/<id>` gives the movies of a T2S collection (TMDb id, title, year; 5035 is the Criterion Collection), for the client's `enqueue --collection`. The database account needs SELECT on `T_WC_T2S_COLLECTION`, `T_WC_T2S_MOVIE_COLLECTION` and `T_WC_T2S_MOVIE`.

## First deployment (VPS)

1. Table: `cd ~/docker/open-credits && git pull && ~/docker/tools/runsqlvaugouindb.sh ~/docker/open-credits/doc/sql/OC-review-table.sql`
2. Folders and secrets: `mkdir -p ~/docker/shared_data/oc-review` (owned by `debian`, uid 1000, which the container runs as), then `cp review/.env.example review/.env` and fill `DB_USER` and `DB_PASSWORD` (an account that can SELECT, INSERT, UPDATE and DELETE `T_WC_OC_REVIEW`).
3. Start: `cd ~/docker/open-credits/review && docker compose up -d --build`
4. Firewall: the proxy reaches the app from a Docker bridge, which ufw drops until it is allowed (the page stays blank, the app logs nothing): `sudo ufw allow from 172.16.0.0/12 to any port 8196 proto tcp comment 'open-credits review, docker bridges'` and the same from `192.168.128.0/20` (done 2026-10-18).
5. Proxy: `git -C ~/docker/reverseproxy pull && docker exec reverseproxy nginx -t && docker exec reverseproxy nginx -s reload`
6. Importer account (once): in `review/.env`, set `IMPORT_DB_PASSWORD` to a long random value (`openssl rand -hex 24`); create the account with that password in the MariaDB client, `CREATE USER 'oc_importer'@'%' IDENTIFIED BY '<password>';` (the password never enters git), then grant its rights: `~/docker/tools/runsqlvaugouindb.sh ~/docker/open-credits/doc/sql/OC-importer-grants.sql`. Then `docker compose up -d --build` starts both services.

## Update

`cd ~/docker/open-credits && git pull && cd review && docker compose up -d --build`
