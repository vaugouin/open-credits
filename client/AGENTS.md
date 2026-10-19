# AGENTS.md - open-credits client prototype

Python package `opencredits` (`src/opencredits/`), the contributor-side client. Repository rules and charter: [../AGENTS.md](../AGENTS.md). Usage and measured results: [README.md](README.md).

## Rules

- Video files are **only read** (ffmpeg input). Frames, pages and results go to a work folder outside the repository; never commit them. The pilot's hand-run work folders live in `U:/open-credits/work/<title>-<tmdb id>/` (NAS; C: is nearly full, a film takes 350 to 400 MB); queue jobs work in `%LOCALAPPDATA%/opencredits/work/<job id>/`, deleted once the bundle is built, so C: holds one film at a time.
- The SQLite file must be on a local disk (`%LOCALAPPDATA%/opencredits/opencredits.sqlite` by default; `store.connect` refuses a network drive): SQLite's file locks are unreliable on SMB. The pilot's file moved there from `U:/open-credits/work/` on 2026-10-18. Schema changes bump `PRAGMA user_version` in `doc/sql/client-sqlite.sql` and get a step in `store.connect` for existing files.
- Settings and secrets (Plex token, server login) come from `%LOCALAPPDATA%/opencredits/opencredits.env` or the environment (`config.py`), never from the repository.
- `plex.py` reads Plex through its HTTP API only, never its database file. Plex is optional: every job field it fills can be given on the command line. The credits language is decided on the frames (`lang.py`); the Plex audio language is only a hint, wrong on two of the four pilot copies. Latin credits get the Latin model (`--lang latin`) when it reads accents on the frames (`lang.accented`). `clean.kept` drops a short line (under 4 letters and digits in Latin script, 3 in Arabic, 2 CJK characters) seen on 2 frames or fewer: the review of three queue titles found such lines were noise, while real short credits ("Ash", "AS", 坊) are seen longer.
- Cleaning (`clean.py`) never loses the voted text: a changed line keeps it in `raw`. Japanese names may keep old kanji forms (亞, 齋): only characters outside the Japanese character set (Shift JIS) are converted. OpenCC alone maps Japanese characters too (岩 to 巌, 里 to 裏, 郁 to 鬱): the 0.6.1 review of the Japanese copy caught it.
- `reference.py` is the only module that reads data from outside the open-credits tables (TMDb credits today). Keep it that way (repository rule on layer-4 comparisons).
- `store.py` and `bundle.py` read only the stage outputs of the work folder; the bundle is read straight from SQLite and never carries the local-only columns (`part.local_path`, `frame.evidence_path`, `submission.status`, `exported_at`), nor a file name. The video is only read: 128 KB for the OpenSubtitles hash, and ffprobe.
- Each stage writes one output file in the window folder (`<work>/w<from>-<to>/`) and is skipped when the file exists; keep stages restartable that way. Frames are shared in `<work>/frames/`. A second copy of a title gets its own work folder (`chihiro-129-disney`): its credits differ.
- Keep the PaddlePaddle pin (`3.2.2`) until a newer release runs PP-OCRv5 on CPU with oneDNN: 3.3.1 raises `NotImplementedError` in `ConvertPirAttribute2RuntimeAttribute`.
- Version: `version` in `pyproject.toml` and `__version__` in `src/opencredits/__init__.py` move together; bump PATCH with every change.

## Commands

```bash
uv sync --extra paddle --extra tesseract
uv run opencredits run VIDEO --from S --to S --work DIR [--engine paddle|tesseract] [--lang en|ja|zh|fa] [--tmdb-credits FILE --tmdb-movie ID]
uv run opencredits review --work DIR --tag ENGINE-LANG --tmdb-credits FILE --tmdb-movie ID   # sample of new lines to judge
uv run opencredits review --work DIR --tag ENGINE-LANG --score                                 # after verdicts.json is saved
uv run opencredits review --work DIR --tag ENGINE-LANG [--tmdb-credits FILE --tmdb-movie ID] --upload   # to the online review page
uv run opencredits submit VIDEO --work DIR --tag ENGINE-LANG --tmdb-movie ID --title TITLE [--title-language L --year Y] [--db FILE]
uv run ../schema/check_submission.py DIR/submission-<id>.zip                                          # the format checker
uv run opencredits enqueue FILE... | --plex KEY... | --plex-recent N [--tmdb-movie ID --title T --lang L --window FROM TO]
uv run opencredits jobs [--status S]
uv run opencredits enqueue --collection ID...                                                          # a T2S collection's movies in Plex
uv run opencredits worker [--once] [--send] [--watch-plex] [--back-catalogue] [--keep-work]
powershell -ExecutionPolicy Bypass -File install-task.ps1 [-Remove]                                    # the worker as a scheduled task
uv run opencredits send [JOB...]; uv run opencredits retry [JOB...]
```

## Known limits (pilot)

- One rolling segment per run, light text; the speed can change inside the segment (Alien: 120 then 180 px/s). Painted backgrounds and live footage work through the text mask (Spirited Away, A Separation).
- Cards are found from the OCR text, not from the picture: every frame outside the roll with at least 400 text-mask pixels is read (1.3 to 2.5 s each). Text in the picture itself (a sign, a screen) would make a card too; none appeared in the windows tried. The 20th Century Fox logo comes out as a card ("CENTU").
- Small capitals (Disney copy) come out in mixed case ("Toshio SuzukI", "DONgURI"): `clean.small_caps` lowers the letters after the first in a word whose case has no pattern (64 lines of the Disney copy), sparing names with one inner capital (McDonald, DeVito) and words that start in lower case. A whole word read in capitals stays so ("LORI Korngiebel"): it cannot be told from a word set in capitals.
- `submit` writes layers 0 to 2 (work, copy, part, submission, segments, frames, text boxes, voted lines) to the SQLite file (`doc/sql/client-sqlite.sql`, default `%LOCALAPPDATA%/opencredits/opencredits.sqlite`) and builds `submission-<id>.zip`, valid for `schema/check_submission.py`. Layer 3 (blocks and credits with role codes) is not written: it needs the role vocabulary on the client (submission-format open point 3). No evidence frames yet. A rerun replaces the copy's submission for the same engine until it is exported. The queue (`jobs.py`) takes the title, ids and markers from Plex and sends bundles (`outbox.py`); without a Plex credits marker it reads the first 240 s and the last 600 s, which costs more card reading than a hand-set window and may let picture text in as cards.
- Paddle drops a tiny opening quote and reads a capital I as l when the typeface makes them identical; in Japanese it sometimes answers a simplified Chinese form (岛 for 島) or a kanji for its katakana twin (八 for ハ). `clean.py` corrects these; other single-kanji confusions (乾 for 幹, 系 for 糸) remain.
- Persian: the Arabic-script model (`arabic_PP-OCRv5_mobile_rec`) boxes word by word and often drops the gaf's second stroke (ک for گ). Job words are corrected from a short list in `clean.py`; names are not (a kaf can be right), and the matching folds گ with ک. TMDb names that exist only romanised cannot be matched yet.
- Joining spaced-out CJK names is a length heuristic (pieces of at most 2 characters, at most 4 together): the gap alone cannot tell a spaced name from two adjacent columns.
