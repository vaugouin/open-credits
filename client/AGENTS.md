# AGENTS.md - open-credits client prototype

Python package `opencredits` (`src/opencredits/`), the contributor-side client. Repository rules and charter: [../AGENTS.md](../AGENTS.md). Usage and measured results: [README.md](README.md).

## Rules

- Video files are **only read** (ffmpeg input). Frames, pages and results go to a work folder outside the repository; never commit them.
- `reference.py` is the only module that reads data from outside the open-credits tables (TMDb credits today). Keep it that way (repository rule on layer-4 comparisons).
- Each stage writes one output file in the work folder and is skipped when the file exists; keep stages restartable that way.
- Keep the PaddlePaddle pin (`3.2.2`) until a newer release runs PP-OCRv5 on CPU with oneDNN: 3.3.1 raises `NotImplementedError` in `ConvertPirAttribute2RuntimeAttribute`.
- Version: `version` in `pyproject.toml` and `__version__` in `src/opencredits/__init__.py` move together; bump PATCH with every change.

## Commands

```bash
uv sync --extra paddle --extra tesseract
uv run opencredits run VIDEO --from S --to S --work DIR [--engine paddle|tesseract] [--tmdb-credits FILE]
```

## Known limits (pilot)

- One rolling segment per run, white text on black; the speed can change inside the segment (Alien: 120 then 180 px/s).
- No opening-credits (cards) stage yet, no SQLite or submission bundle output yet.
- Paddle drops a tiny opening quote ("Alien' head effects") and reads a capital I as l when the typeface makes them identical.
