# AGENTS.md - open-credits client prototype

Python package `opencredits` (`src/opencredits/`), the contributor-side client. Repository rules and charter: [../AGENTS.md](../AGENTS.md). Usage and measured results: [README.md](README.md).

## Rules

- Video files are **only read** (ffmpeg input). Frames, pages and results go to a work folder outside the repository; never commit them. The pilot's work folders live in `U:/open-credits/work/<title>-<tmdb id>/` (NAS; C: is nearly full, a film takes 350 to 400 MB).
- Cleaning (`clean.py`) never loses the voted text: a changed line keeps it in `raw`. Japanese names may keep old kanji forms (亞, 齋): only characters that exist solely in simplified Chinese are converted.
- `reference.py` is the only module that reads data from outside the open-credits tables (TMDb credits today). Keep it that way (repository rule on layer-4 comparisons).
- Each stage writes one output file in the work folder and is skipped when the file exists; keep stages restartable that way.
- Keep the PaddlePaddle pin (`3.2.2`) until a newer release runs PP-OCRv5 on CPU with oneDNN: 3.3.1 raises `NotImplementedError` in `ConvertPirAttribute2RuntimeAttribute`.
- Version: `version` in `pyproject.toml` and `__version__` in `src/opencredits/__init__.py` move together; bump PATCH with every change.

## Commands

```bash
uv sync --extra paddle --extra tesseract
uv run opencredits run VIDEO --from S --to S --work DIR [--engine paddle|tesseract] [--lang en|ja|zh] [--tmdb-credits FILE --tmdb-movie ID]
```

## Known limits (pilot)

- One rolling segment per run, light text; the speed can change inside the segment (Alien: 120 then 180 px/s). Painted backgrounds work through the text mask (Spirited Away).
- No opening-credits or end cards stage yet (Spirited Away's Disney copy opens its end credits with cards), no SQLite or submission bundle output yet.
- Paddle drops a tiny opening quote and reads a capital I as l when the typeface makes them identical; in Japanese it sometimes answers a simplified Chinese form (岛 for 島) or a kanji for its katakana twin (八 for ハ). `clean.py` corrects these; other single-kanji confusions (乾 for 幹, 系 for 糸) remain.
- Joining spaced-out CJK names is a length heuristic (pieces of at most 2 characters, at most 4 together): the gap alone cannot tell a spaced name from two adjacent columns.
