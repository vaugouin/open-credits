# AGENTS.md - Agent guide for open-credits

Single canonical guide for coding agents in this repository. `CLAUDE.md` only points here. Human-facing overview: [README.md](README.md).

## What this repository is

Crowdsourced OCR of the on-screen credits (opening and closing) of movies and series, from video files the contributor owns, into an editable master database, with contributions to TMDb and Wikidata by each contributor under their own account. Public repository `github.com/vaugouin/open-credits`, created 2026-10-16.

It belongs to the **Agent BBB** ecosystem (repos under `%USERPROFILE%/Code/<repo>`, all converging on a shared MariaDB). Role: acquisition. The open-credits master database lives in the T2S MariaDB as `T_WC_OC_*` tables (decided 2026-10-17, revising charter decision 30), so credits can be joined with the TMDb and Wikidata tables; public copies come from export scripts that dump the `T_WC_OC_*` tables only.

## Where the decisions live

The project charter (32 decisions, taken with Philippe on 2026-10-14 and 2026-10-15), the data-model task and the pilot are tracked in the backlog, not here:

- `%USERPROFILE%/Nestor/projets/t2s-backlog/repos/open-credits.md` (OPEN-CREDITS-001 charter, -002 data model, -003 pilot).

Read the charter before changing anything structural. Key decisions an agent must not contradict:

- The client runs on the contributor's PC and **never uploads video**; it sends text and, optionally, cropped evidence frames.
- **Classical OCR on CPU**; vision models only as a measured fallback.
- **One editable master database** (on the VPS at first) with read-only copies; ordinary accounts; moderation on the TMDb model.
- **Several submissions per title** are kept side by side; consolidated credits are computed from them. A single submission is authoritative.
- Data under **CC0**, code under **MIT**.
- Names of private individuals (crowdfunding backers, thanked persons) are stored but kept out of the public view and of contributions until the consent question is settled.

## Pilot arrangement

The client works in a local SQLite file and exports one JSON bundle per submission; an importer loads the bundles into the `T_WC_OC_*` tables (see `doc/technology-choices.md`, sections 4 and 6). `sqlite-plex-to-tmdb` (sibling repository) maps Plex files to TMDb IDs. Plex data in MariaDB: `T_WC_TMDB_PLEX_*`. Keep the `T_WC_OC_*` tables free of foreign keys to other `T_WC_*` tables, and the code that reads non-OC tables (layer 4 comparisons, ROLE seeding) in one module.

## Client prototype

`client/` holds the Python package `opencredits` (its own `pyproject.toml` and `AGENTS.md`): frames, scroll, virtual page, OCR, vote and TMDb check, run by `uv run opencredits run`. Read `client/AGENTS.md` before changing it.

The client also runs as a queue (`opencredits enqueue`, `worker`, `send`): one video file per job, its identity, editions and credits markers from Plex (HTTP API, optional), the credits language decided on the frames, bundles sent to the server. Its SQLite file and settings live in `%LOCALAPPDATA%/opencredits/`, never on a network share.

`review/` is the pilot's online hand-check (charter, decision 27 c): a small FastAPI stack on the VPS (`www.vaugouin.com/oc-review/`, basic auth at the proxy) that shows the samples built by `opencredits review` and saves each verdict in `T_WC_OC_REVIEW`; it also receives the submission bundles (`POST api/submissions`), checks them and keeps them in an incoming folder for the importer. Read `review/AGENTS.md` before changing it.

## Conventions

- Python with `uv`. LF line endings (`.gitattributes`).
- Table definitions: `doc/sql/OC-tables.sql` (master, `T_WC_OC_*`, T2S conventions: upper-case columns, standard columns, no foreign key constraints, native `uuid` keys) and `doc/sql/client-sqlite.sql` (client, logical names, STRICT tables with foreign keys). A column added to one is added to the other, to `doc/data-model.md` and, if it travels, to `schema/submission.schema.json`. The agent's database account cannot run DDL: Philippe runs `OC-tables.sql`.
- Never commit video files, frames, SQLite databases or secrets (`.gitignore`).
- `.sql` files that must run on the VPS follow the ecosystem rule: committed and pushed first, then `~/docker/tools/runsqlvaugouindb.sh` (see `%USERPROFILE%/Code/tools/AGENTS.md`).
- Documentation in English (public repository).
