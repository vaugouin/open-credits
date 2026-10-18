# open-credits client (prototype)

Reads the credits of a video file you own, rolling or shown as cards, on your own PC, with classical OCR on the CPU. Nothing is uploaded; the video file is only read.

Pilot stage: one command reads one time window of one file (the rolling credits if the window holds a roll, the cards in the rest of it) and writes everything to a work folder; another writes the runs of a title to the contributor's SQLite file and builds a submission bundle (layers 0 to 2: frames, text boxes and voted lines; the credits themselves, layer 3, come next).

## Install

Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg (with ffprobe) on the PATH. Tesseract is optional (Windows installer from UB Mannheim).

```bash
cd client
uv sync --extra paddle             # add --extra tesseract for the comparison engine
```

## Run

```bash
# Alien: opening cards, then the end roll; the TMDb check counts both windows
uv run opencredits run "T:/public/video/HDFilms/Alien 1979 {edition-Theatrical} REMASTERED PROPER 1080p BluRay x265.mp4" \
    --from 0 --to 170 --work U:/open-credits/work/alien-348 \
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 348
uv run opencredits run "T:/public/video/HDFilms/Alien 1979 {edition-Theatrical} REMASTERED PROPER 1080p BluRay x265.mp4" \
    --from 6800 --to 6996 --work U:/open-credits/work/alien-348 \
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 348

uv run opencredits run "T:/public/video/HDAnimes/Le voyage de Chihiro (2001) [1080p] MULTi BluRay x264-PopHD.mkv" \
    --from 7240 --to 7475 --lang ja --work U:/open-credits/work/chihiro-129 \
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 129

uv run opencredits run "T:/public/video/HDFilms/A Separation 2011 1080p BluRay x264-OFT.mkv" \
    --from 7200 --to 7385 --lang fa --work U:/open-credits/work/separation-60243 \
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 60243
```

`--from` and `--to` bound the search window in seconds (the Plex credits marker is a good start: it may begin early, the scroll analysis finds the real start). `--lang` picks the recognition model (`en`, `ja`, `zh`, `fa`). Frames are shared in `<work>/frames/`; each window writes to `<work>/w<from>-<to>/`, and the TMDb check (`<work>/tmdb-<engine>-<lang>.txt`) counts every window read so far for the title. Keep the work folder outside the repository: a film takes 350 to 400 MB of frames. The pilot keeps its work folders in `U:/open-credits/work/<title>-<tmdb id>/`, and a second copy of a title gets its own (`chihiro-129-disney`), since its credits differ.

## The chain

| Stage | Module | Output in the work folder |
|---|---|---|
| 1. One frame per second with ffmpeg | `frames.py` | `frames/tNNNNN.png` |
| 2. Vertical shift between frames (row profiles of a text mask: bright pixels that stand out from the blurred frame, so a painted background does not count), roll boundaries, page offset of each frame, speed stretches | `scroll.py` | `scroll.json` |
| 3. Virtual page: frames stacked at their offsets (max blend), for review | `page.py` | `page.png` |
| 4. OCR of each frame, one reading per text line, placed on the page | `ocr.py` | `readings-<engine>-<lang>.json` |
| 5. Vote: readings of the same line across frames grouped by page height and span, majority text kept; lines cut by the frame edge dropped; Chinese and Japanese names spaced out by the typesetting rejoined; Persian words, boxed one by one by the detector, joined right to left in each frame before the vote | `vote.py` | `lines-<engine>-<lang>.json`, `.txt` |
| 5b. Cleaning of known OCR slips, the voted text kept as `raw` (shown as `(read: ...)`): lost opening quote, `l` for a capital `I`, small capitals read as capitals in mixed case (`IshII` for `Ishii`); in Japanese, simplified-only characters to their Japanese form and kanji read for their katakana twin (八 for ハ); in Persian, Arabic yeh and kaf to the Persian letters and a few credit words read with kaf for gaf (کارکردان for کارگردان) | `clean.py` | same files |
| 6. Cards: every frame outside the roll with enough text is read; each line is followed through time (same place, similar text, gaps of 2 s bridged); lines on screen together make one card, and a header that stays over several cards is attached to each | `cards.py` | `card-readings-<engine>-<lang>.json`, `cards-<engine>-<lang>.json`, `.txt` |
| 7. Optional check against the TMDb credits (`doc/sql/pilot-tmdb-credits.sql` result), on every name of a person, kanji folded to one form, over every window read for the title | `reference.py` | `../tmdb-<engine>-<lang>.txt` |

Stages 2 to 6 write to the window folder; a stage whose output exists is skipped: delete the file to redo it.

## SQLite file and submission bundle

Once a title's windows are read, `submit` writes them to the contributor's SQLite file ([`../doc/sql/client-sqlite.sql`](../doc/sql/client-sqlite.sql); default `%LOCALAPPDATA%/opencredits/opencredits.sqlite`, refused on a network share) as one submission for the copy and engine, then builds `submission-<id>.zip` in the work folder ([`../doc/submission-format.md`](../doc/submission-format.md)):

```bash
uv run opencredits submit "T:/public/video/HDFilms/Alien 1979 {edition-Theatrical} REMASTERED PROPER 1080p BluRay x265.mp4"     --work U:/open-credits/work/alien-348 --tag paddle-en --tmdb-movie 348 --title Alien --title-language en --year 1979
uv run ../schema/check_submission.py U:/open-credits/work/alien-348/submission-<id>.zip
```

The copy is identified by its OpenSubtitles hash and size (the file's path and name stay in the SQLite file, never in the bundle); its edition and source come from the file name (`{edition-Theatrical}`, `BluRay`). Each window gives a segment: the roll (`rolling`, with its scroll speed and each frame's page offset) and the cards (`cards`), with every frame read, its text boxes and perceptual hash, and the voted lines with the frames that saw them. Layer 3, blocks and credits with role codes, is not written yet.

## The queue: a continuous flow of titles

The commands above read one title by hand. The queue reads titles one after the other, unattended: each job is a video file, taken in the order queued, and goes from frames to bundle on its own.

```bash
uv run opencredits enqueue --plex-recent 20             # the 20 movies added to Plex last
uv run opencredits enqueue "T:/public/video/HDFilms/Alien 1979 {edition-Theatrical} REMASTERED PROPER 1080p BluRay x265.mp4"
uv run opencredits enqueue FILE --tmdb-movie 348 --title Alien --year 1979 --lang en --window 0 170 --window 6800 6996   # without Plex
uv run opencredits jobs                                 # counts and latest jobs
uv run opencredits worker                               # runs until stopped; --once stops when the queue is empty
uv run opencredits worker --send --watch-plex           # the continuous flow: new Plex movies queued, bundles sent once ready
uv run opencredits send [JOB ...]                       # send ready bundles (all of them without ids)
uv run opencredits retry [JOB ...]                      # queue failed jobs again
```

What a job finds on its own:

- **What the file is**, from Plex when it knows the file (searched by name, confirmed by size): TMDb and IMDb ids, title (`title_hint`, with the library language when the title is in Latin script), year, edition, audio languages, credits markers. A file Plex does not know needs `--tmdb-movie` and `--title`, or it is skipped. A Plex movie with several files is queued once, with its single-file copy closest to 1080 lines; multi-part copies are skipped for now.
- **Where to read**: around each Plex credits marker (from 60 s before it), else the first 240 s and the last 600 s. `--window` overrides this.
- **The credits language** (OCR model), decided on the frames, not the audio: the 6 frames with the most text in the last window are read with the base model (Japanese, Chinese, English), and the script of what comes out decides; when it reads nothing convincing, the Arabic-script model gets the same frames. The audio language decides only when the frames do not. On the four pilot copies the frames gave en, ja, en and fa, all right, where the default audio track would have been wrong twice (the French audio of *Le Voyage de Chihiro*, Japanese credits; the Japanese audio of the Disney copy, English credits).

Measured on *Alien* (theatrical, 1080p, from the NAS): Plex gave the ids and the credits marker, the frames gave English, and the job read the first 240 s (16 cards, 174 frames with text, 354 s) and 6749 to 6997 s (the roll and one card, 337 s): 255 lines against 254 for the hand-set windows, 751 s in all, a 65 KB bundle.

Each job works in `%LOCALAPPDATA%/opencredits/work/<job id>/` (deleted once the bundle is built; `--keep-work` keeps it), and its bundle goes to `%LOCALAPPDATA%/opencredits/outbox/`. A job left running by a crash returns to the queue when the worker starts, and fails after 3 starts. The worker appends what it prints to `%LOCALAPPDATA%/opencredits/worker.log`. Sending posts each bundle to the server's `api/submissions` ([`../review/`](../review/README.md)), which checks it against the format and keeps it for the importer; a job sent is marked `sent`, its submission `exported`.

Settings live in `%LOCALAPPDATA%/opencredits/opencredits.env` (`KEY=VALUE` lines, overridden by the environment; never in git):

```
PLEX_SERVER_URL=https://...plex.direct:32400
PLEX_TOKEN=...
OC_PLEX_SECTIONS=4                 # movie libraries to read (default: all)
OC_PATH_MAP=/volume1/sharing=T:    # Plex paths to local paths
OC_REVIEW_USER=...                 # the server's basic-auth login, also used by review --upload
OC_REVIEW_PASSWORD=...
```

To run it at every logon, a Task Scheduler task can start `uv run --project C:/Users/vaugo/Code/open-credits/client opencredits worker --send --watch-plex`.

## Precision check of the new lines

Once a title's windows are read, `review` draws 50 lines at random (fixed seed) among those that hold no TMDb name of the title, and writes `<work>/review-<engine>-<lang>/index.html` with a crop of a frame for each. Open the page in a browser, judge each line (exact, minor, wrong, noise), click *Save verdicts* and put the downloaded `verdicts.json` in that folder; `--score` then gives the precision (charter, decision 27 c). With `--upload`, the sample goes to the online review page instead ([`../review/`](../review/README.md)), where each verdict is saved as it is clicked.

```bash
uv run opencredits review --work U:/open-credits/work/alien-348 --tag paddle-en     --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt --tmdb-movie 348
uv run opencredits review --work U:/open-credits/work/alien-348 --tag paddle-en --score
uv run opencredits review --work U:/open-credits/work/alien-348 --tag paddle-en --upload   # OC_REVIEW_USER, OC_REVIEW_PASSWORD
```

## Results

| Title | Credits read | Lines | Time | TMDb people read exactly |
|---|---|---|---|---|
| *Alien* (1979), English, white on black, 1920×800 | opening: 13 credit cards and the Nostromo card (0 to 170 s); end roll 6832 to 6990 s, 159 frames, 120 then 180 px/s | 31 + 223 | 1.3 s/frame | 86 of 94; the 7 absent are uncredited (Ben Burtt, the two Williamses…) |
| *Spirited Away* (2001), Japanese, over painted backgrounds, 1920×1040 | end roll 7256 to 7461 s, 206 frames, 137 px/s, then 2 cards (監督 宮崎駿, おわり) | 636 + 2 | 2.3 s/frame | 86 of the 97 with a Japanese name in TMDb |
| *Spirited Away*, Disney English copy | 8 cards from 7259 s (a U.S. PRODUCTION header over 6 of them), roll 7288 to 7401 s, 2 end cards | | | 83 of 137 (TMDb names are romanised) |
| *A Separation* (2011), Persian, right to left, over moving live footage, 1920×1080 | end roll 7228 to 7358 s, 131 frames, 159 px/s, then 2 cards (Asia Pacific Screen Awards; title and year ۱۳۸۹) | 324 + 6 | 2.5 s/frame | 14 of the 14 with a Persian name in TMDb |

On *Spirited Away*, the 11 misses checked against the frames are 2 OCR errors (森乾生 for 森 幹生, 系川 for 糸川), 5 names that TMDb holds differently from the screen (小野織香 for 小野香織, 山形厚志 for 山形厚史…), and names credited under another form or not in the end roll. Of the two copies in the pilot library, the one labelled JAPANESE carries the Disney English credits and the French MULTi copy the original Japanese ones: credits belong to a copy, not to a title.

On *A Separation*, TMDb lists 26 people and only 14 have a name in Persian script; the 12 others are romanised only, though several are on screen (سارینا فرهادی, اصغر فرهادی, مریم نراقی): matching them would need transliteration. About 100 names on screen are not in TMDb at all.

## Engines

Measured on *Alien* (1979), 159 frames of 1920×800, on 2026-10-17:

| Engine | Time | TMDb people found exactly, of 80 in the end roll |
|---|---|---|
| PaddleOCR 3, PP-OCRv5 mobile detection + English mobile recognition, PaddlePaddle 3.2.2 with oneDNN (default) | 2.0 s/frame | 79 (one "lan" for "Ian", now cleaned) |
| Tesseract 5.4, thresholded, `--psm 11` | 0.3 s/frame | 61, and it misses most short job titles and all character names |

PaddlePaddle is pinned to 3.2.2: 3.3 fails on CPU with oneDNN, and without oneDNN the same models take 5.3 s/frame. The PP-OCRv5 server models take 37 s/frame and split lines into words.
