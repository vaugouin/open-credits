# open-credits

Open, crowdsourced extraction of the **on-screen credits** of movies and series.

Every film and every episode ends (and often begins) with a list of the people, companies and places that made it. Public databases such as TMDb and Wikidata hold only part of it: second-unit crews, assistant directors, visual-effects artists, dubbing casts, filming locations, songs and thanks are mostly missing. open-credits reads those credits directly from video files, with classical OCR running on contributors' own computers, and turns them into structured, sourced credit lines.

## Status

Pilot stage (October 2026). Nothing to install yet. The current work is the data model, [`doc/data-model.md`](doc/data-model.md), the comparison of technologies, [`doc/technology-choices.md`](doc/technology-choices.md), the submission format, [`doc/submission-format.md`](doc/submission-format.md), the table definitions, [`doc/sql/`](doc/sql/), and a pilot on twelve deliberately different titles: a CGI blockbuster, a crowdfunded film, Saul Bass titles, graphic credits with dubbing credits, a French film, a TV episode, a DVD rip, Japanese, bilingual Hong Kong and right-to-left Persian credits, a film with several copies and editions, and a film split into two files.

## Principles

- **Contributors process their own copies.** The client runs on the contributor's PC and reads video files they already own, matched to TMDb IDs by their Plex library. No video ever leaves their machine: only text, and optionally the frames each credit line was read from, as evidence.
- **CPU, not tokens.** Classical OCR on the contributor's processor. Vision models are at most a fallback for hard cases.
- **One editable master database, open copies.** Credits stay editable (corrections, moderation, erasure on request). Anyone can host a read-only copy or use the dumps.
- **Moderation in the spirit of TMDb.** Anyone contributes; volunteer moderators handle reports, lock confirmed data and sanction abuse. Contributors earn reputation when independent copies or existing data confirm their lines.
- **Contributions stay personal.** Each contributor submits to TMDb and Wikidata under their own account; open-credits prepares the differences, it does not post on anyone's behalf.

## Licences

- Code: MIT, see [LICENSE](LICENSE).
- Data: every submission is placed under **CC0** (public domain dedication), the condition for it to reach Wikidata.
