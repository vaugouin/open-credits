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

## First deployment (VPS)

1. Table: `cd ~/docker/open-credits && git pull && ~/docker/tools/runsqlvaugouindb.sh ~/docker/open-credits/doc/sql/OC-review-table.sql`
2. Folders and secrets: `mkdir -p ~/docker/shared_data/oc-review` (owned by `debian`, uid 1000, which the container runs as), then `cp review/.env.example review/.env` and fill `DB_USER` and `DB_PASSWORD` (an account that can SELECT, INSERT, UPDATE and DELETE `T_WC_OC_REVIEW`).
3. Start: `cd ~/docker/open-credits/review && docker compose up -d --build`
4. Proxy: `git -C ~/docker/reverseproxy pull && docker exec reverseproxy nginx -t && docker exec reverseproxy nginx -s reload`

## Update

`cd ~/docker/open-credits && git pull && cd review && docker compose up -d --build`
