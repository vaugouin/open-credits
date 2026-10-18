# open-credits review

Online hand-check of the lines the client reads that TMDb does not have (pilot criterion, charter decision 27 c). The page lists the samples; a sample shows 50 lines, each with a crop of a frame where it is on screen, and each verdict (exact, minor, wrong, noise) and note is saved in MariaDB (`T_WC_OC_REVIEW`) as soon as it is clicked. URL: `https://www.vaugouin.com/oc-review/` (basic auth).

## First deployment (VPS)

1. Table: `cd ~/docker/open-credits && git pull && ~/docker/tools/runsqlvaugouindb.sh ~/docker/open-credits/doc/sql/OC-review-table.sql`
2. Folders and secrets: `mkdir -p ~/docker/shared_data/oc-review`, then `cp review/.env.example review/.env` and fill `DB_USER` and `DB_PASSWORD` (an account that can SELECT, INSERT and UPDATE `T_WC_OC_REVIEW`).
3. Start: `cd ~/docker/open-credits/review && docker compose up -d --build`
4. Proxy: `git -C ~/docker/reverseproxy pull && docker exec reverseproxy nginx -t && docker exec reverseproxy nginx -s reload`

## Adding a sample

On the PC, the client builds it in the title's work folder, then the folder is copied to the VPS under its sample name:

```bash
uv run opencredits review --work U:/open-credits/work/alien-348 --tag paddle-en \
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 348
scp -r U:/open-credits/work/alien-348/review-paddle-en debian@vps-adacb908.vps.ovh.net:docker/shared_data/oc-review/alien-348-paddle-en
```

The sample appears on the list at the next page load. A `verdicts.json` saved by the offline page (`review-<tag>/index.html`) in the folder fills the verdicts not yet given.

## Update

`cd ~/docker/open-credits && git pull && cd review && docker compose up -d --build`
