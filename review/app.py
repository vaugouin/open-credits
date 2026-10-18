"""open-credits review: hand-check of sampled OCR lines (charter, decision 27 c), each verdict saved on click.

Samples are folders copied from the client (`opencredits review`) under SHARED: <sample>/sample.json and
<sample>/crops/NN.png, sent by the client as one zip (`opencredits review --upload`). On upload and on listing,
new samples are loaded into T_WC_OC_REVIEW, and a verdicts.json from the offline page fills the verdicts not yet given."""
import io
import json
import os
import re
import secrets
import shutil
import time
import uuid
from datetime import date, datetime
from pathlib import Path
from zipfile import BadZipFile, ZipFile

import pymysql
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel

VERSION = (Path(__file__).parent / "VERSION").read_text().strip()
SHARED = Path(os.environ.get("REVIEW_SHARED", "/shared"))
VERDICTS = ("exact", "minor", "wrong", "noise")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,99}$")
CROP = re.compile(r"^\d{2,3}\.png$")
MEMBER = re.compile(r"^(sample\.json|verdicts\.json|crops/\d{2,3}\.png)$")   # the only files a sample zip may hold
MAX_ZIP = 30 * 1024 * 1024
MAX_FILES = 300

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


@app.post("/api/samples/{name}")
async def upload(name: str, request: Request, replace: bool = False):
    """A sample zip from the client. An existing sample is refused unless replace, which also drops its verdicts."""
    if not NAME.match(name): raise HTTPException(422, "sample name: lower case letters, digits and hyphens")
    body = await request.body()
    if len(body) > MAX_ZIP: raise HTTPException(413, "zip too large")
    try:
        z = ZipFile(io.BytesIO(body))
        members = [m for m in z.infolist() if not m.is_dir()]
    except BadZipFile:
        raise HTTPException(422, "not a zip")
    bad = [m.filename for m in members if not MEMBER.match(m.filename)]
    if bad or not any(m.filename == "sample.json" for m in members) or len(members) > MAX_FILES:
        raise HTTPException(422, f"unexpected content: {bad[:5]}" if bad else "sample.json missing or too many files")
    if sum(m.file_size for m in members) > 4 * MAX_ZIP: raise HTTPException(413, "zip expands too much")
    try:
        s = json.loads(z.read("sample.json").decode("utf-8")); assert s["tag"] and s["items"]
    except Exception:
        raise HTTPException(422, "sample.json unreadable")
    target = SHARED / name
    if target.exists() and not replace: raise HTTPException(409, "sample already there: upload with replace to redo it (its verdicts are dropped)")
    tmp = SHARED / f".upload-{name}"
    shutil.rmtree(tmp, ignore_errors=True); (tmp / "crops").mkdir(parents=True)
    for m in members: (tmp / m.filename).write_bytes(z.read(m))
    if target.exists():
        shutil.rmtree(target)
        with db() as c, c.cursor() as cur: cur.execute("DELETE FROM T_WC_OC_REVIEW WHERE SAMPLE = %s", (name,))
    tmp.rename(target)
    sync()
    return dict(ok=True, sample=name, items=len(s["items"]), crops=sum(1 for m in members if m.filename.startswith("crops/")))


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
