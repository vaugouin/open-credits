# open-credits client (prototype)

Reads the rolling end credits of a video file you own, on your own PC, with classical OCR on the CPU. Nothing is uploaded; the video file is only read.

Pilot stage: one command runs the whole chain on one file and writes everything to a work folder. It does not yet write the client SQLite database nor a submission bundle.

## Install

Python 3.12, [uv](https://docs.astral.sh/uv/) and ffmpeg (with ffprobe) on the PATH. Tesseract is optional (Windows installer from UB Mannheim).

```bash
cd client
uv sync --extra paddle             # add --extra tesseract for the comparison engine
```

## Run

```bash
uv run opencredits run "T:/public/video/HDFilms/Alien 1979 {edition-Theatrical} REMASTERED PROPER 1080p BluRay x265.mp4" \
    --from 6800 --to 6996 --work ../../oc-work/alien-348 \
    --tmdb-credits ../doc/sql/pilot-tmdb-credits-20261017.txt
```

`--from` and `--to` bound the search window in seconds (the Plex credits marker is a good start: it may begin early, the scroll analysis finds the real start). Keep the work folder outside the repository.

## The chain

| Stage | Module | Output in the work folder |
|---|---|---|
| 1. One frame per second with ffmpeg | `frames.py` | `frames/tNNNNN.png` |
| 2. Vertical shift between frames (row-profile correlation), roll boundaries, page offset of each frame, speed stretches | `scroll.py` | `scroll.json` |
| 3. Virtual page: frames stacked at their offsets (max blend), for review | `page.py` | `page.png` |
| 4. OCR of each frame, one reading per text line, placed on the page | `ocr.py` | `readings-<engine>.json` |
| 5. Vote: readings of the same line across frames grouped by page height and span, majority text kept; lines cut by the frame edge dropped | `vote.py` | `lines-<engine>.json`, `.txt` |
| 6. Optional check against the TMDb credits (`doc/sql/pilot-tmdb-credits.sql` result) | `reference.py` | `tmdb-<engine>.txt` |

A stage whose output exists is skipped: delete the file to redo it.

## Engines

Measured on *Alien* (1979), 159 frames of 1920×800, on 2026-10-17:

| Engine | Time | TMDb people found exactly, of 80 in the end roll |
|---|---|---|
| PaddleOCR 3, PP-OCRv5 mobile detection + English mobile recognition, PaddlePaddle 3.2.2 with oneDNN (default) | 2.0 s/frame | 79 (one "lan" for "Ian") |
| Tesseract 5.4, thresholded, `--psm 11` | 0.3 s/frame | 61, and it misses most short job titles and all character names |

PaddlePaddle is pinned to 3.2.2: 3.3 fails on CPU with oneDNN, and without oneDNN the same models take 5.3 s/frame. The PP-OCRv5 server models take 37 s/frame and split lines into words.
