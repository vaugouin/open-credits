"""open-credits importer: loads the submission bundles kept in SHARED/incoming/ into the T_WC_OC_* tables.

One import process, one bundle per transaction (technology-choices, section 4): each bundle is checked again
(schema/check_submission.py), then its work, copy and parts are found or created, and its submission, segments,
frames, text boxes and text lines are written. A loaded bundle moves to SHARED/imported/, a refused one to
SHARED/rejected/ with a <name>.txt giving the reason; a database error leaves it in incoming/ for the next pass.

What it does not do yet: layer 3 (blocks, credits, entities: the client does not send them, a bundle that
carries them is refused) and evidence frames (none are sent; a bundle's frames/ would be kept under
SHARED/evidence/<submission id>/). The uploads carry no identity, so every submission is credited to one
contributor, IMPORT_CONTRIBUTOR (the pilot's only one).

Times: CREATED_AT and SUBMITTED_AT are UTC, as the DDL says; DAT_CREAT and TIM_UPDATED are local time, which
the compose file sets to Europe/Paris like the rest of the database.

    python importer.py            # every POLL seconds, for ever (the oc-importer service)
    python importer.py --once     # one pass over incoming/, then stop"""
import json
import os
import re
import secrets
import shutil
import sys
import time
import traceback
import unicodedata
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pymysql

sys.path[:0] = [str(Path(__file__).parent / "schema"), str(Path(__file__).parent.parent / "schema")]
from check_submission import check, describe_work  # noqa: E402

SHARED = Path(os.environ.get("REVIEW_SHARED", "/shared"))
INCOMING, IMPORTED, REJECTED, EVIDENCE = (SHARED / d for d in ("incoming", "imported", "rejected", "evidence"))
CONTRIBUTOR = os.environ.get("IMPORT_CONTRIBUTOR", "vaugouin")
POLL = 60
STD = "DELETED, DAT_CREAT, TIM_UPDATED"        # standard columns the importer fills; ID_CREATOR, ID_OWNER stay NULL


class Refused(Exception):
    """The bundle is wrong or not supported: it goes to rejected/, never half-loaded."""


def db():
    return pymysql.connect(host=os.environ.get("DB_HOST", "127.0.0.1"), port=int(os.environ.get("DB_PORT", "3306")),
                           user=os.environ.get("IMPORT_DB_USER", "oc_importer"), password=os.environ["IMPORT_DB_PASSWORD"],
                           database=os.environ.get("DB_NAME", "vaugouindb"), charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def uuid7() -> str:
    """Time-ordered UUID (version 7), as the T_WC_OC_* keys expect."""
    b = bytearray(int(time.time() * 1000).to_bytes(6, "big") + secrets.token_bytes(10))
    b[6] = (b[6] & 0x0F) | 0x70; b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def utc(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None)


def std() -> tuple:
    return 0, date.today(), datetime.now().replace(microsecond=0)


def log(msg: str) -> None:
    print(f"{datetime.now():%Y-%m-%d %H:%M:%S} {msg}", flush=True)


def plain(s: str | None) -> str:
    """Lower case, no accents, letters and digits only: for the title sanity check."""
    s = unicodedata.normalize("NFKD", s or "")
    return re.sub(r"[^a-z0-9]", "", "".join(c for c in s if not unicodedata.combining(c)).lower())


def contributor(cur) -> str:
    cur.execute("SELECT ID_OC_CONTRIBUTOR AS id FROM T_WC_OC_CONTRIBUTOR WHERE USERNAME = %s", (CONTRIBUTOR,))
    if row := cur.fetchone(): return row["id"]
    cid = uuid7()
    cur.execute(f"INSERT INTO T_WC_OC_CONTRIBUTOR (ID_OC_CONTRIBUTOR, USERNAME, {STD}) VALUES (%s, %s, %s, %s, %s)",
                (cid, CONTRIBUTOR) + std())
    return cid


def work(cur, w: dict) -> tuple[str, str | None]:
    """The work row for the bundle's external ids, created on first sight with its titles from TMDb (never
    from the bundle). Returns its id and a note when title_hint or year disagree with TMDb (kept, not refused:
    the hint is the library's title, often a translation)."""
    if w["kind"] != "movie" or "tmdb_movie_id" not in w:
        raise Refused(f"only movies with a TMDb id are imported yet, not {describe_work(w)}")
    mid = w["tmdb_movie_id"]
    cur.execute("""SELECT ORIGINAL_TITLE, ORIGINAL_LANGUAGE, TITLE, YEAR(DAT_RELEASE) AS YEAR, ID_IMDB
                   FROM T_WC_TMDB_MOVIE WHERE ID_MOVIE = %s AND DELETED = 0""", (mid,))
    t = cur.fetchone()
    note = None
    if not t: note = f"TMDb movie {mid} is not in T_WC_TMDB_MOVIE"
    else:
        cur.execute("SELECT TITLE FROM T_WC_TMDB_MOVIE_LANG WHERE ID_MOVIE = %s", (mid,))
        titles = {plain(t["ORIGINAL_TITLE"]), plain(t["TITLE"])} | {plain(r["TITLE"]) for r in cur.fetchall()}
        if plain(w["title_hint"]) not in titles: note = f"title hint {w['title_hint']!r}, TMDb {t['ORIGINAL_TITLE']!r}"
        elif w.get("year") and t["YEAR"] and abs(w["year"] - t["YEAR"]) > 1: note = f"year {w['year']}, TMDb {t['YEAR']}"
    cur.execute("SELECT ID_OC_WORK AS id FROM T_WC_OC_WORK WHERE ID_MOVIE = %s", (mid,))
    if row := cur.fetchone(): return row["id"], note
    wid = uuid7(); t = t or {}
    cur.execute(f"""INSERT INTO T_WC_OC_WORK (ID_OC_WORK, KIND, ID_MOVIE, ID_IMDB, ID_WIKIDATA, ORIGINAL_TITLE,
                    ORIGINAL_LANGUAGE, TITLE_EN, YEAR, {STD}) VALUES (%s, 'movie', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (wid, mid, t.get("ID_IMDB") or w.get("imdb_id"), w.get("wikidata_id"), t.get("ORIGINAL_TITLE"),
                 t.get("ORIGINAL_LANGUAGE"), t.get("TITLE"), t.get("YEAR")) + std())
    return wid, note


def copy(cur, c: dict, work_id: str) -> tuple[str, dict[int, str]]:
    """The copy with this fingerprint, shared by everyone who holds the same files, and its parts by index."""
    cur.execute("SELECT ID_OC_COPY AS id, ID_OC_WORK AS work FROM T_WC_OC_COPY WHERE FINGERPRINT = %s", (c["fingerprint"],))
    if row := cur.fetchone():
        if row["work"] != work_id: raise Refused(f"copy {c['fingerprint'][:12]} already belongs to another work")
        cur.execute("SELECT PART_INDEX, ID_OC_PART AS id FROM T_WC_OC_PART WHERE ID_OC_COPY = %s", (row["id"],))
        return row["id"], {r["PART_INDEX"]: r["id"] for r in cur.fetchall()}
    cid = uuid7()
    cur.execute(f"""INSERT INTO T_WC_OC_COPY (ID_OC_COPY, ID_OC_WORK, FINGERPRINT, PART_COUNT, DURATION_MS, WIDTH, HEIGHT,
                    FPS, EDITION_HINT, VERSION_LANGUAGE, SOURCE, {STD}) VALUES ({', '.join(['%s'] * 14)})""",
                (cid, work_id, c["fingerprint"], len(c["parts"]), c["duration_ms"], c.get("width"), c.get("height"),
                 c.get("fps"), c.get("edition_hint"), c.get("version_language"), c.get("source")) + std())
    parts = {p["part_index"]: uuid7() for p in c["parts"]}
    cur.executemany(f"""INSERT INTO T_WC_OC_PART (ID_OC_PART, ID_OC_COPY, PART_INDEX, OPENSUBTITLES_HASH, FILE_SIZE,
                        DURATION_MS, OFFSET_MS, {STD}) VALUES ({', '.join(['%s'] * 10)})""",
                    [(parts[p["part_index"]], cid, p["part_index"], p["opensubtitles_hash"], p["file_size"],
                      p["duration_ms"], p["offset_ms"]) + std() for p in c["parts"]])
    return cid, parts


def load(cur, doc: dict, z: ZipFile, submitted_at: datetime) -> str:
    s = doc["submission"]
    if any(g.get("blocks") for g in doc["segments"]) or doc.get("entities"):
        raise Refused("blocks, credits and entities (layer 3) are not imported yet")
    cur.execute("SELECT 1 FROM T_WC_OC_SUBMISSION WHERE ID_OC_SUBMISSION = %s", (s["id"],))
    if cur.fetchone(): return "already loaded"
    work_id, note = work(cur, doc["work"])
    copy_id, parts = copy(cur, doc["copy"], work_id)
    evidence = {n for n in z.namelist() if n.startswith("frames/")}
    cur.execute(f"""INSERT INTO T_WC_OC_SUBMISSION (ID_OC_SUBMISSION, ID_OC_CONTRIBUTOR, ID_OC_COPY, FORMAT_VERSION,
                    CLIENT_NAME, CLIENT_VERSION, OCR_ENGINE, OCR_ENGINE_VERSION, OCR_MODELS, PARAMETERS, VOCABULARY_VERSION,
                    TITLE_HINT, TITLE_LANGUAGE, HAS_EVIDENCE_FRAMES, CREATED_AT, SUBMITTED_AT, STATUS, LICENCE, {STD})
                    VALUES ({', '.join(['%s'] * 21)})""",
                (s["id"], contributor(cur), copy_id, doc["format_version"], s["client"]["name"], s["client"]["version"],
                 s["ocr"]["engine"], s["ocr"]["engine_version"], s["ocr"].get("models"),
                 json.dumps(s["ocr"]["parameters"], ensure_ascii=False) if "parameters" in s["ocr"] else None,
                 s.get("vocabulary_version"), doc["work"]["title_hint"], doc["work"].get("title_language"),
                 bool(evidence), utc(s["created_at"]), submitted_at, "published", s["licence"]) + std())
    segs, frames, boxes, lines = [], [], [], []
    for i, g in enumerate(doc["segments"]):
        segs.append((g["id"], s["id"], parts[g["part_index"]], g["kind"], g["start_ms"], g["end_ms"], g["detected_by"],
                     g["layout"], g.get("scroll_px_per_s"), i) + std())
        for f in g["frames"]:
            ev, crop = f.get("evidence") or {}, (f.get("evidence") or {}).get("crop") or {}
            path = f"evidence/{s['id']}/{f['id']}.webp" if ev.get("file") in evidence else None
            frames.append((f["id"], g["id"], f["timecode_ms"], f["phash"], f.get("page_offset_px"), path,
                           crop.get("x"), crop.get("y"), crop.get("w"), crop.get("h")) + std())
            boxes += [(uuid7(), f["id"], b["x"], b["y"], b["w"], b["h"], b["text"], b["confidence"], b.get("font_height_px"),
                       b.get("is_upper_case"), b.get("is_bold"), j) + std() for j, b in enumerate(f["text_boxes"])]
        lines += [(l["id"], g["id"], l["y_page"], l["x"], l["w"], l["h"], l["text"], l["readings"], l["agreeing"],
                   l["confidence"], json.dumps(l["frame_ids"]), l["first_ms"], l["last_ms"], j) + std()
                  for j, l in enumerate(g["text_lines"])]
    cur.executemany(f"""INSERT INTO T_WC_OC_SEGMENT (ID_OC_SEGMENT, ID_OC_SUBMISSION, ID_OC_PART, KIND, START_MS, END_MS,
                        DETECTED_BY, LAYOUT, SCROLL_PX_PER_S, DISPLAY_ORDER, {STD}) VALUES ({', '.join(['%s'] * 13)})""", segs)
    cur.executemany(f"""INSERT INTO T_WC_OC_FRAME (ID_OC_FRAME, ID_OC_SEGMENT, TIMECODE_MS, PHASH, PAGE_OFFSET_PX,
                        EVIDENCE_PATH, CROP_X, CROP_Y, CROP_W, CROP_H, {STD}) VALUES ({', '.join(['%s'] * 13)})""", frames)
    cur.executemany(f"""INSERT INTO T_WC_OC_TEXT_BOX (ID_OC_TEXT_BOX, ID_OC_FRAME, X, Y, W, H, TEXT, CONFIDENCE,
                        FONT_HEIGHT_PX, IS_UPPER_CASE, IS_BOLD, DISPLAY_ORDER, {STD}) VALUES ({', '.join(['%s'] * 15)})""", boxes)
    cur.executemany(f"""INSERT INTO T_WC_OC_TEXT_LINE (ID_OC_TEXT_LINE, ID_OC_SEGMENT, Y_PAGE, X, W, H, TEXT, READINGS,
                        AGREEING, CONFIDENCE, FRAME_IDS, FIRST_MS, LAST_MS, DISPLAY_ORDER, {STD})
                        VALUES ({', '.join(['%s'] * 17)})""", lines)
    if evidence:   # written last: a failed transaction leaves at most an orphan folder, never a row without its file
        out = EVIDENCE / s["id"]; out.mkdir(parents=True, exist_ok=True)
        for n in evidence: (out / Path(n).name).write_bytes(z.read(n))
    return (f"{describe_work(doc['work'])}: {len(segs)} segments, {len(frames)} frames, {len(boxes)} boxes, "
            f"{len(lines)} lines" + (f" (check: {note})" if note else ""))


def move(f: Path, to: Path, reason: str | None = None) -> None:
    to.mkdir(exist_ok=True)
    f.replace(to / f.name)
    if reason: (to / (f.stem + ".txt")).write_text(reason + "\n", encoding="utf-8")


def one(con, f: Path) -> None:
    sid = f.stem[len("submission-"):]
    try:
        with ZipFile(f) as z:
            doc = json.loads(z.read("submission.json").decode("utf-8"))
            if errors := check(doc, set(z.namelist())): raise Refused("; ".join(errors[:20]))
            if doc["submission"]["id"] != sid: raise Refused(f"the file name says {sid}, the bundle {doc['submission']['id']}")
            submitted = datetime.fromtimestamp(f.stat().st_mtime, timezone.utc).replace(tzinfo=None)
            with con.cursor() as cur: what = load(cur, doc, z, submitted)
            con.commit()
    except (Refused, BadZipFile, KeyError, ValueError, pymysql.err.IntegrityError, pymysql.err.DataError) as e:
        # a duplicate key or an out-of-range value is the bundle's fault: retrying would block the ones after it
        con.rollback(); move(f, REJECTED, f"{type(e).__name__}: {e}"); log(f"{sid[-8:]} rejected: {e}"); return
    move(f, IMPORTED); log(f"{sid[-8:]} {what}")


def run(once: bool = False) -> None:
    log(f"importer started: {INCOMING}, contributor {CONTRIBUTOR}")
    while True:
        files = sorted(INCOMING.glob("submission-*.zip"), key=lambda f: f.stat().st_mtime) if INCOMING.exists() else []
        if files:
            try:
                with db() as con:
                    for f in files: one(con, f)
            except pymysql.err.MySQLError:   # the database is away or refuses: the bundles wait in incoming/
                log("database error, retry at the next pass\n" + traceback.format_exc())
        if once: return
        time.sleep(POLL)


if __name__ == "__main__":
    run("--once" in sys.argv)
