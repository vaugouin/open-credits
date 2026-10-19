"""The job queue: one job per video file, taken in the order queued, read from start to bundle by the worker.

A job runs in a work folder of the client's local folder (fast to read back, unlike frames on the NAS), deleted
once the bundle is in the outbox. Statuses: queued, running, ready (bundle built, not sent), sent, failed,
skipped. A job left running by a crash goes back to the queue when the worker starts, and fails after
MAX_ATTEMPTS starts."""
import argparse
import json
import shutil
import sqlite3
import sys
import time
import traceback
from datetime import datetime, timezone
from pathlib import Path

from . import bundle, config, frames, lang, plex, store

ENGINE = "paddle"
OPENING = 240        # s read at the start of a film for opening titles, when no Plex marker says where they are
CLOSING = 600        # s read at the end when Plex has no credits marker
LEAD = 60            # s read before a Plex credits marker: markers may start late, the scroll finds the real start
MAX_ATTEMPTS = 3
POLL = 60            # s between looks at an empty queue


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class Skip(Exception):
    """A job that cannot be read as it stands (no TMDb id, a multi-part copy): skipped, not failed."""


def add(db: sqlite3.Connection, path: str, again: bool = False, **fields) -> str | None:
    """Queue a file. A file already queued, read or sent is not queued twice unless again."""
    path = str(Path(path)).replace("\\", "/")
    if not again and db.execute("SELECT 1 FROM job WHERE local_path = ? AND status IN ('queued', 'running', 'ready', 'sent')",
                                (path,)).fetchone(): return None
    jid = store.uuid7(); cols = {k: v for k, v in fields.items() if v is not None}
    if "windows" in cols: cols["windows"] = json.dumps(cols["windows"])
    db.execute(f"INSERT INTO job (id, local_path, queued_at{''.join(', ' + k for k in cols)}) VALUES (?, ?, ?{', ?' * len(cols)})",
               (jid, path, now(), *cols.values()))
    db.commit()
    return jid


def add_plex(db: sqlite3.Connection, rating_key: int, again: bool = False) -> str | None:
    """Queue the copy of a Plex movie that best_copy picks."""
    it = plex.item(rating_key); c = plex.best_copy(it["copies"])
    if c is None: return None
    return add(db, c["parts"][0]["file"], again, plex_rating_key=rating_key)


def windows(duration: int, markers: list[dict]) -> list[list[int]]:
    """Time windows to read: around each Plex credits marker, else the opening and the last CLOSING seconds."""
    credits = [m for m in markers if m["type"] == "credits"]
    out = [[max(0, int(m["start_s"]) - LEAD), duration if m["final"] or m["end_s"] >= duration - 30 else int(m["end_s"]) + 10]
           for m in credits]
    if not any(w[0] < duration / 2 for w in out): out.append([0, min(OPENING, duration)])
    if not any(w[1] >= duration - 30 for w in out): out.append([max(0, duration - CLOSING), duration])
    out.sort(); merged = [out[0]]
    for w in out[1:]:
        if w[0] <= merged[-1][1]: merged[-1][1] = max(merged[-1][1], w[1])
        else: merged.append(w)
    return merged


def process(db: sqlite3.Connection, job: dict, keep: bool = False) -> dict:
    """Read one job from frames to bundle. Returns the report stored with the job."""
    from .cli import run           # the cli module holds the window run; imported here to avoid a cycle
    t0 = time.time(); video = job["local_path"]; rep: dict = {}
    if not Path(video).is_file(): raise Skip(f"file not found: {video}")
    meta = dict(title=job["title"], year=job["year"], title_language=job["title_language"], tmdb_movie_id=job["tmdb_movie_id"])
    markers, hint, edition, imdb = [], None, None, None
    if job["plex_rating_key"] or plex.enabled():
        key = job["plex_rating_key"] or plex.find(video)
        if key:
            it = plex.item(key); job["plex_rating_key"] = key
            mine = [c for c in it["copies"] if any(Path(p["file"]).name == Path(video).name for p in c["parts"])]
            if mine and len(mine[0]["parts"]) > 1: raise Skip("multi-part copy: not read yet")
            markers, edition, imdb = it["markers"], it["edition"], it["imdb_id"]
            hint = plex.audio_hint(mine[0]) if mine else None
            for k in meta: meta[k] = meta[k] or it[k]
    if not meta["tmdb_movie_id"]: raise Skip("no TMDb id (not in Plex, or Plex has none): queue it with --tmdb-movie")
    if not meta["title"]: raise Skip("no title: queue it with --title")
    duration = int(frames.duration(video))
    wins = json.loads(job["windows"]) if job["windows"] else windows(duration, markers)
    rep.update(title=meta["title"], tmdb_movie_id=meta["tmdb_movie_id"], windows=wins,
               markers=[m for m in markers if m["type"] == "credits"], audio_hint=hint)
    work = config.data_dir() / "work" / job["id"]; work.mkdir(parents=True, exist_ok=True)

    code = job["lang"]
    if not code:   # decided on the last window, where the end credits are
        a, b = wins[-1]
        print(f"language: frames {a}..{b} s")
        code, how = lang.detect(frames.extract(video, a, b, work / "frames"), hint)
        rep["lang_decided_by"] = how
    rep["lang"] = code; print(f"language: {code}")
    for a, b in wins:
        t1 = time.time()
        run(argparse.Namespace(video=video, start=a, to=b, work=str(work), engine=ENGINE, lang=code, no_cards=False,
                               tmdb_credits=None, tmdb_movie=None))
        rep.setdefault("window_seconds", []).append(round(time.time() - t1))
    tag = f"{ENGINE}-{code}"
    sid = store.write(db, video, work, tag, meta["tmdb_movie_id"], meta["title"], meta["year"], meta["title_language"],
                      edition, job["plex_rating_key"], imdb)
    n = db.execute("""SELECT COUNT(DISTINCT g.id), COUNT(DISTINCT f.id), COUNT(DISTINCT l.id) FROM segment g
                      LEFT JOIN frame f ON f.segment_id = g.id LEFT JOIN text_line l ON l.segment_id = g.id
                      WHERE g.submission_id = ?""", (sid,)).fetchone()
    outbox = config.data_dir() / "outbox"; outbox.mkdir(exist_ok=True)
    out = bundle.write(db, sid, outbox)
    rep.update(segments=n[0], frames=n[1], lines=n[2], bundle_kb=out.stat().st_size // 1024, seconds=round(time.time() - t0))
    db.execute("UPDATE job SET submission_id = ?, bundle_path = ?, plex_rating_key = ? WHERE id = ?",
               (sid, str(out), job["plex_rating_key"], job["id"]))
    if not keep: shutil.rmtree(work, ignore_errors=True)
    return rep


def next_job(db: sqlite3.Connection) -> dict | None:
    db.row_factory = sqlite3.Row
    r = db.execute("SELECT * FROM job WHERE status = 'queued' ORDER BY queued_at, rowid LIMIT 1").fetchone()
    db.row_factory = None
    return dict(r) if r else None


def recover(db: sqlite3.Connection) -> None:
    """Jobs left running by a crash go back to the queue, or fail after MAX_ATTEMPTS starts."""
    db.execute("UPDATE job SET status = 'failed', error = 'stopped during the run ' || attempts || ' times' "
               "WHERE status = 'running' AND attempts >= ?", (MAX_ATTEMPTS,))
    db.execute("UPDATE job SET status = 'queued' WHERE status = 'running'")
    db.commit()


def run_one(db: sqlite3.Connection, job: dict, keep: bool = False) -> str:
    db.execute("UPDATE job SET status = 'running', started_at = ?, attempts = attempts + 1, error = NULL WHERE id = ?",
               (now(), job["id"])); db.commit()
    print(f"\n=== job {job['id']} {job['local_path']}", flush=True)
    try:
        rep = process(db, job, keep)
        status, error = "ready", None
    except Skip as e:
        rep, status, error = None, "skipped", str(e)
    except Exception as e:
        rep, status, error = None, "failed", f"{type(e).__name__}: {e}"
        traceback.print_exc()
    db.execute("UPDATE job SET status = ?, error = ?, report = ?, finished_at = ? WHERE id = ?",
               (status, error, json.dumps(rep, ensure_ascii=False) if rep else None, now(), job["id"]))
    db.commit()
    print(f"=== {status}" + (f": {error}" if error else f", {rep['lines']} lines, {rep['seconds']} s, {rep['bundle_kb']} KB"), flush=True)
    return status


def watch_plex(db: sqlite3.Connection) -> int:
    """Queue the movies added to Plex since the last look. The first look only sets the mark."""
    row = db.execute("SELECT value FROM meta WHERE key = 'plex_added_mark'").fetchone()
    new = plex.recent(200, int(row[0]) if row else None)
    mark = max([m["added_at"] for m in new] + [int(row[0]) if row else int(time.time())])
    n = 0
    if row:
        for m in reversed(new):    # oldest first, so the queue keeps Plex's order
            n += add_plex(db, m["rating_key"]) is not None
    db.execute("INSERT INTO meta (key, value) VALUES ('plex_added_mark', ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
               (str(mark),)); db.commit()
    return n


def worker(db: sqlite3.Connection, once: bool = False, send: bool = False, watch: bool = False, keep: bool = False) -> None:
    from . import outbox
    log = (config.data_dir() / "worker.log").open("a", encoding="utf-8")
    sys.stdout = Tee(sys.stdout, log)
    recover(db)
    print(f"worker started {now()}: {db.execute('SELECT COUNT(*) FROM job WHERE status = ?', ('queued',)).fetchone()[0]} jobs queued", flush=True)
    while True:
        if send: outbox.send_ready(db)
        job = next_job(db)
        if job: run_one(db, job, keep); continue
        if watch and plex.enabled():
            n = watch_plex(db)
            if n: print(f"{now()}: {n} new Plex movies queued", flush=True); continue
        if once: break
        time.sleep(POLL)


class Tee:
    def __init__(self, *streams): self.streams = streams
    def write(self, s):
        for st in self.streams: st.write(s)
        self.streams[-1].flush()     # the log file, so it can be followed while the worker runs
    def flush(self):
        for st in self.streams: st.flush()


def listing(db: sqlite3.Connection, status: str | None = None, limit: int = 50) -> str:
    q = "SELECT id, status, queued_at, local_path, error, report FROM job" + (" WHERE status = ?" if status else "") + \
        " ORDER BY CASE status WHEN 'running' THEN 0 WHEN 'queued' THEN 1 ELSE 2 END, queued_at DESC LIMIT ?"
    rows = db.execute(q, ((status,) if status else ()) + (limit,)).fetchall()
    counts = dict(db.execute("SELECT status, COUNT(*) FROM job GROUP BY status").fetchall())
    out = [" · ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "queue empty"]
    for jid, st, qa, path, err, rep in rows:
        r = json.loads(rep) if rep else {}
        detail = err or (f"{r.get('lang')}, {r.get('lines')} lines, {r.get('seconds')} s" if r else "")
        out.append(f"{jid[-8:]}  {st:8} {qa[:16]}  {Path(path).name[:70]}  {detail}")
    return "\n".join(out)
