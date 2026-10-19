"""The contributor's SQLite file (doc/sql/client-sqlite.sql): one submission per copy and engine, written from the
work folder of a title (layers 0 to 2: work, copy, part, submission, segments, frames, text boxes, voted lines).

Layer 3 (blocks and credits) needs the role vocabulary on the client and is not written yet."""
import hashlib
import json
import secrets
import sqlite3
import statistics
import struct
import subprocess
import time
import uuid
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path

import numpy as np
from PIL import Image

from . import __version__, config, frames, ocr, scroll

DDL_NAME = "client-sqlite.sql"
CLIENT = "opencredits"


def uuid7() -> str:
    """Time-ordered UUID (version 7), as the format asks for every row of a submission."""
    b = bytearray(int(time.time() * 1000).to_bytes(6, "big") + secrets.token_bytes(10))
    b[6] = (b[6] & 0x0F) | 0x70; b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def ddl() -> str:
    """The schema: shipped in the package, or read from the repository when the client runs from a clone."""
    for p in (Path(__file__).parent / DDL_NAME, Path(__file__).parents[3] / "doc" / "sql" / DDL_NAME):
        if p.exists(): return p.read_text(encoding="utf-8")
    raise FileNotFoundError(DDL_NAME)


def default_path() -> Path:
    return config.data_dir() / "opencredits.sqlite"


def connect(path: Path | None = None) -> sqlite3.Connection:
    """The contributor's SQLite file, created or brought to the current schema. Refused on a network share."""
    path = path or default_path()
    if config.is_network(path):
        raise SystemExit(f"{path} is on a network share, where SQLite can corrupt the file: keep it on a local disk "
                         f"(default {default_path()})")
    path.parent.mkdir(parents=True, exist_ok=True)
    new = not path.exists()
    db = sqlite3.connect(path, timeout=30)
    db.execute("PRAGMA foreign_keys = ON"); db.execute("PRAGMA journal_mode = WAL")   # the queue is read while the worker writes
    if new: db.executescript(ddl()); return db
    version = db.execute("PRAGMA user_version").fetchone()[0]
    if version == 2:    # version 3 adds the queue priority (the job section below then adds the Plex index)
        db.execute("ALTER TABLE job ADD COLUMN priority INTEGER NOT NULL DEFAULT 1"); db.execute("DROP INDEX job_queue")
    if version == 3:    # version 4 adds the file of each indexed Plex movie: the index is read again in full
        db.execute("ALTER TABLE plex_movie ADD COLUMN file TEXT"); db.execute("DELETE FROM meta WHERE key = 'plex_index_complete'")
    if version < 4:
        db.executescript(ddl().split("-- Local only: the job queue", 1)[1].split("\n", 1)[1] + "\nPRAGMA user_version = 4;")
    return db


def opensubtitles_hash(path: str) -> tuple[str, int]:
    """64-bit OpenSubtitles hash: file size plus the 64-bit words of the first and last 64 KB. Reads 128 KB."""
    size = Path(path).stat().st_size; h = size; chunk = 65536
    with open(path, "rb") as f:
        for pos in (0, max(0, size - chunk)):
            f.seek(pos); data = f.read(chunk)
            data += b"\0" * (-len(data) % 8)
            for (v,) in struct.iter_unpack("<Q", data): h = (h + v) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}", size


def probe(video: str) -> dict:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                        "stream=width,height,r_frame_rate:format=duration", "-of", "json", video],
                       check=True, capture_output=True, text=True, creationflags=frames.NO_WINDOW)
    d = json.loads(r.stdout); s = d["streams"][0]; num, den = s["r_frame_rate"].split("/")
    return dict(width=s["width"], height=s["height"], fps=round(int(num) / int(den), 3),
                duration_ms=round(float(d["format"]["duration"]) * 1000))


def source_of(name: str) -> str | None:
    """Kind of source from the file name, which stays on this machine."""
    n = name.lower()
    for key, src in (("remux", "remux"), ("bluray", "bluray"), ("blu-ray", "bluray"), ("bdrip", "bluray"),
                     ("web", "web"), ("dvd", "dvd"), ("hdtv", "tv"), ("vhs", "vhs")):
        if key in n: return src
    return None


def edition_of(name: str) -> str | None:
    """Plex edition tag in the file name: {edition-Theatrical}."""
    if "{edition-" in name: return name.split("{edition-", 1)[1].split("}", 1)[0][:200]
    return None


_DCT = None


def phash(path: Path) -> str:
    """64-bit perceptual hash (DCT of a 32x32 grey image, 8x8 low frequencies against their median)."""
    global _DCT
    if _DCT is None:
        n = np.arange(32); _DCT = np.cos(np.pi * (2 * n[None, :] + 1) * n[:, None] / 64)
    a = np.asarray(Image.open(path).convert("L").resize((32, 32), Image.Resampling.LANCZOS), dtype=float)
    low = (_DCT @ a @ _DCT.T)[:8, :8].flatten()
    bits = low > np.median(low[1:])
    return f"{int(''.join('1' if b else '0' for b in bits), 2):016x}"


def engine_info(engine: str, lang: str) -> tuple[str, str, str]:
    if engine == "paddle":
        return "paddleocr", metadata.version("paddleocr"), f"PP-OCRv5_mobile_det + {ocr.PADDLE_REC[lang]}; paddlepaddle {metadata.version('paddlepaddle')}"
    return "tesseract", metadata.version("pytesseract"), f"tesseract {ocr.TESSERACT_LANG[lang]}, psm 11"


def write(db: sqlite3.Connection, video: str, work_dir: Path, tag: str, tmdb_movie: int, title: str,
          year: int | None = None, title_language: str | None = None, edition: str | None = None,
          plex_rating_key: int | None = None, imdb_id: str | None = None) -> str:
    """One submission for this copy and engine-lang tag, from every window of the work folder. A previous
    submission of the same copy and tag that was not exported is replaced. The edition is Plex's, else the
    file name's {edition-...} tag."""
    engine, lang = tag.split("-", 1)
    name = Path(video).name
    osh, size = opensubtitles_hash(video); info = probe(video)
    fp = hashlib.sha256(f"{osh}:{size}".encode("ascii")).hexdigest()
    cur = db.cursor()

    row = cur.execute("SELECT id FROM work WHERE tmdb_movie_id = ?", (tmdb_movie,)).fetchone()
    work_id = row[0] if row else uuid7()
    if not row:
        cur.execute("""INSERT INTO work (id, kind, tmdb_movie_id, imdb_id, title_hint, title_language, year, plex_rating_key)
                       VALUES (?, 'movie', ?, ?, ?, ?, ?, ?)""", (work_id, tmdb_movie, imdb_id, title, title_language, year, plex_rating_key))
    row = cur.execute("SELECT id FROM copy WHERE fingerprint = ?", (fp,)).fetchone()
    copy_id = row[0] if row else uuid7()
    if not row:
        cur.execute("""INSERT INTO copy (id, work_id, fingerprint, part_count, duration_ms, width, height, fps, edition_hint, source)
                       VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?)""",
                    (copy_id, work_id, fp, info["duration_ms"], info["width"], info["height"], info["fps"], (edition or edition_of(name) or "")[:200] or None, source_of(name)))
        cur.execute("""INSERT INTO part (id, copy_id, part_index, opensubtitles_hash, file_size, duration_ms, offset_ms, local_path)
                       VALUES (?, ?, 1, ?, ?, ?, 0, ?)""", (uuid7(), copy_id, osh, size, info["duration_ms"], str(video)))
    part_id = cur.execute("SELECT id FROM part WHERE copy_id = ? AND part_index = 1", (copy_id,)).fetchone()[0]

    eng, eng_version, models = engine_info(engine, lang)
    for (old,) in cur.execute("SELECT id FROM submission WHERE copy_id = ? AND ocr_engine = ? AND ocr_models = ? AND status <> 'exported'",
                              (copy_id, eng, models)).fetchall():
        cur.execute("DELETE FROM submission WHERE id = ?", (old,))
    sub_id = uuid7()
    cur.execute("""INSERT INTO submission (id, copy_id, created_at, client_name, client_version, ocr_engine, ocr_engine_version,
                   ocr_models, parameters, status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'review')""",
                (sub_id, copy_id, datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), CLIENT, __version__,
                 eng, eng_version, models, json.dumps(dict(lang=lang, frames_per_second=1, windows=sorted(w.name for w in work_dir.glob("w*"))))))

    fr = frames.frames_in(work_dir / "frames")
    for win in sorted(work_dir.glob("w*")):
        rf, lf = win / f"readings-{tag}.json", win / f"lines-{tag}.json"
        # a roll found but nothing read on it gives no segment (the format wants a segment's frames)
        if rf.exists() and lf.exists() and (lines := json.loads(lf.read_text(encoding="utf-8"))):
            rows = [tuple(r) for r in json.loads((win / "scroll.json").read_text(encoding="utf-8"))]
            first, last = scroll.find_roll(rows); offs = scroll.offsets(rows, first, last)
            readings = json.loads(rf.read_text(encoding="utf-8"))["readings"]
            px = (max(offs.values()) - min(offs.values())) / max(1, last - first)
            kind = "closing_credits" if first * 1000 > info["duration_ms"] / 2 else "opening_titles"
            segment(cur, sub_id, part_id, kind, "rolling", first, last, readings, lines, fr, offs, px)
        cf, kf = win / f"card-readings-{tag}.json", win / f"cards-{tag}.json"
        if cf.exists() and kf.exists():
            cards = json.loads(kf.read_text(encoding="utf-8"))
            lines = [dict(l) for c in cards for l in c["lines"] if not l.get("header")]
            seen = {}
            for c in cards:   # a header attached to several cards is one line on screen
                for l in c["lines"]:
                    if l.get("header"): seen[(l["text"], l["t0"], l["t1"])] = l
            lines += list(seen.values())
            if not lines: continue
            readings = json.loads(cf.read_text(encoding="utf-8"))["readings"]
            t0 = min(l["t0"] for l in lines); t1 = max(l["t1"] for l in lines)
            kind = "card" if t0 * 1000 > info["duration_ms"] / 2 else "opening_titles"
            segment(cur, sub_id, part_id, kind, "cards", t0, t1, readings, lines, fr, None, None)
    db.commit()
    return sub_id


def segment(cur, sub_id, part_id, kind, layout, first, last, readings, lines, fr, offs, px) -> None:
    """One segment with its frames (those the kept lines were seen on, and every frame read in the stretch),
    their text boxes and the voted lines."""
    seg_id = uuid7()
    cur.execute("""INSERT INTO segment (id, submission_id, part_id, kind, start_ms, end_ms, detected_by, layout, scroll_px_per_s)
                   VALUES (?, ?, ?, ?, ?, ?, 'text_detection', ?, ?)""",
                (seg_id, sub_id, part_id, kind, first * 1000, (last if last > first else first + 1) * 1000, layout,
                 round(px, 1) if px is not None else None))
    by_t: dict[int, list] = {}
    for r in readings:
        if first <= r["t"] <= last: by_t.setdefault(r["t"], []).append(r)
    frame_id = {}
    for t, rs in sorted(by_t.items()):
        fid = frame_id[t] = uuid7()
        cur.execute("INSERT INTO frame (id, segment_id, timecode_ms, phash, page_offset_px, has_text) VALUES (?, ?, ?, ?, ?, 1)",
                    (fid, seg_id, t * 1000, phash(fr[t]), offs.get(t) if offs else None))
        for r in rs:
            x, y = max(0, int(r["x0"])), max(0, int(r["y0"]))
            cur.execute("""INSERT INTO text_box (id, frame_id, x, y, w, h, text, confidence, font_height_px)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (uuid7(), fid, x, y, max(1, int(r["x1"]) - x), max(1, int(r["y1"]) - y), r["text"],
                         min(1.0, max(0.0, float(r["conf"]))), max(1, int(r["y1"]) - int(r["y0"]))))
    for l in lines:
        ts = [t for t in l["frames"] if t in frame_id]
        if not ts: continue
        conf = [float(r["conf"]) for t in ts for r in by_t[t] if r["text"].strip() == (l.get("raw") or l["text"]).strip()]
        cur.execute("""INSERT INTO text_line (id, segment_id, y_page, x, w, h, text, readings, agreeing, confidence, frame_ids, first_ms, last_ms)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (uuid7(), seg_id, int(l["y"]), max(0, int(l["x0"])), max(1, int(l["x1"]) - int(l["x0"])), max(1, int(l["h"])),
                     l["text"], int(l["seen"]), min(int(l["agree"]), int(l["seen"])),
                     round(statistics.fmean(conf), 4) if conf else round(l["agree"] / l["seen"], 4),
                     json.dumps([frame_id[t] for t in ts]), min(ts) * 1000, max(ts) * 1000))
