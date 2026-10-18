"""open-credits review: hand-check of sampled OCR lines (charter, decision 27 c), each verdict saved on click.

Samples are folders copied from the client (`opencredits review`) under SHARED: <sample>/sample.json and
<sample>/crops/NN.png. On listing, new samples are loaded into T_WC_OC_REVIEW, and a verdicts.json left in a
folder by the offline page fills the verdicts not yet given."""
import json
import os
import re
import secrets
import time
import uuid
from datetime import date, datetime
from pathlib import Path

import pymysql
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
SHARED = Path(os.environ.get("REVIEW_SHARED", "/shared"))
VERDICTS = ("exact", "minor", "wrong", "noise")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
CROP = re.compile(r"^\d{2,3}\.png$")

app = FastAPI(title="open-credits review", version=VERSION)


def db():
    return pymysql.connect(host=os.environ.get("DB_HOST", "127.0.0.1"), port=int(os.environ.get("DB_PORT", "3306")),
                           user=os.environ["DB_USER"], password=os.environ["DB_PASSWORD"],
                           database=os.environ.get("DB_NAME", "vaugouindb"), charset="utf8mb4",
                           cursorclass=pymysql.cursors.DictCursor, autocommit=True)


def uuid7() -> str:
    """Time-ordered UUID (version 7), as the T_WC_OC_* keys expect."""
    b = bytearray(int(time.time() * 1000).to_bytes(6, "big") + secrets.token_bytes(10))
    b[6] = (b[6] & 0x0F) | 0x70; b[8] = (b[8] & 0x3F) | 0x80
    return str(uuid.UUID(bytes=bytes(b)))


def sample_dir(name: str) -> Path:
    if not NAME.match(name) or not (SHARED / name / "sample.json").is_file(): raise HTTPException(404, "no such sample")
    return SHARED / name


def sync() -> None:
    """Load the sample folders not yet in the table, then the verdicts of an offline verdicts.json."""
    with db() as c, c.cursor() as cur:
        for f in sorted(SHARED.glob("*/sample.json")):
            name = f.parent.name
            if not NAME.match(name): continue
            s = json.loads(f.read_text(encoding="utf-8"))
            cur.execute("SELECT COUNT(*) AS n FROM T_WC_OC_REVIEW WHERE SAMPLE = %s", (name,))
            if cur.fetchone()["n"] < len(s["items"]):
                for it in s["items"]:
                    cur.execute("""INSERT IGNORE INTO T_WC_OC_REVIEW (ID_OC_REVIEW, SAMPLE, ID_MOVIE, TAG, ITEM, LINE_TEXT,
                        LINE_RAW, LINE_KIND, WINDOW_NAME, FRAME_T, DISPLAY_ORDER, DAT_CREAT, TIM_UPDATED)
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                        (uuid7(), name, s.get("movie"), s["tag"], it["id"], it["text"], it.get("raw"), it["kind"],
                         it["window"], it["t"], it["id"], date.today(), datetime.now()))
            v = f.parent / "verdicts.json"
            if v.is_file():
                for item, x in json.loads(v.read_text(encoding="utf-8")).items():
                    if x.get("verdict") in VERDICTS:
                        cur.execute("""UPDATE T_WC_OC_REVIEW SET VERDICT = %s, NOTE = %s, TIM_UPDATED = %s
                            WHERE SAMPLE = %s AND ITEM = %s AND VERDICT IS NULL""",
                            (x["verdict"], x.get("note") or None, datetime.now(), name, int(item)))


@app.get("/api/samples")
def samples():
    sync()
    with db() as c, c.cursor() as cur:
        cur.execute("""SELECT SAMPLE, ID_MOVIE, TAG, COUNT(*) AS total, COUNT(VERDICT) AS judged,
            SUM(VERDICT = 'exact') AS exact, SUM(VERDICT IN ('exact', 'minor')) AS exact_or_minor
            FROM T_WC_OC_REVIEW WHERE DELETED = 0 GROUP BY SAMPLE, ID_MOVIE, TAG ORDER BY SAMPLE""")
        rows = cur.fetchall()
    for r in rows:
        for k in ("exact", "exact_or_minor"): r[k] = int(r[k] or 0)
    return dict(version=VERSION, samples=rows)


@app.get("/api/samples/{name}")
def sample(name: str):
    s = json.loads((sample_dir(name) / "sample.json").read_text(encoding="utf-8"))
    with db() as c, c.cursor() as cur:
        cur.execute("""SELECT ITEM, LINE_TEXT, LINE_RAW, LINE_KIND, WINDOW_NAME, FRAME_T, VERDICT, NOTE
            FROM T_WC_OC_REVIEW WHERE SAMPLE = %s AND DELETED = 0 ORDER BY ITEM""", (name,))
        items = cur.fetchall()
    return dict(sample=name, title=s.get("title", name), tag=s["tag"], new_lines=s.get("new_lines"), items=items)


class Verdict(BaseModel):
    verdict: str | None = None
    note: str | None = None


@app.put("/api/samples/{name}/{item}")
def judge(name: str, item: int, v: Verdict):
    sample_dir(name)
    if v.verdict is not None and v.verdict not in VERDICTS: raise HTTPException(422, "unknown verdict")
    with db() as c, c.cursor() as cur:
        n = cur.execute("""UPDATE T_WC_OC_REVIEW SET VERDICT = %s, NOTE = %s, TIM_UPDATED = %s
            WHERE SAMPLE = %s AND ITEM = %s""", (v.verdict, (v.note or "").strip()[:500] or None, datetime.now(), name, item))
    if not n: raise HTTPException(404, "no such line")
    return dict(ok=True)


@app.get("/crops/{name}/{file}")
def crop(name: str, file: str):
    if not CROP.match(file): raise HTTPException(404)
    p = sample_dir(name) / "crops" / file
    if not p.is_file(): raise HTTPException(404)
    return FileResponse(p, media_type="image/png")


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html", headers={"Cache-Control": "no-cache"})


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=os.environ.get("REVIEW_HOST", "172.17.0.1"), port=int(os.environ.get("REVIEW_PORT", "8196")))
