"""Sending bundles to the server: POST api/submissions, one zip per request, basic auth (config.py).

The server checks each bundle against the format and keeps it for the importer; sending the same bundle twice is
harmless (the server answers that it has it). A sent job is marked sent and its submission exported."""
import base64
import json
import sqlite3
import urllib.error
import urllib.request
from pathlib import Path

from . import config
from .jobs import now


def post(path: Path) -> dict:
    user, pwd = config.get("OC_REVIEW_USER"), config.get("OC_REVIEW_PASSWORD")
    if not user or not pwd: raise SystemExit("set OC_REVIEW_USER and OC_REVIEW_PASSWORD (the server's basic-auth login)")
    url = config.get("OC_SERVER_URL", config.SERVER_URL).rstrip("/") + "/api/submissions"
    req = urllib.request.Request(url, data=path.read_bytes(), method="POST", headers={
        "Content-Type": "application/zip", "Authorization": "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()})
    with urllib.request.urlopen(req, timeout=300) as r: return json.loads(r.read())


def send(db: sqlite3.Connection, job_id: str) -> str:
    row = db.execute("SELECT status, bundle_path, submission_id FROM job WHERE id = ?", (job_id,)).fetchone()
    if not row: return f"{job_id}: no such job"
    status, bundle, sid = row
    if status != "ready": return f"{job_id[-8:]}: {status}, not ready"
    if not bundle or not Path(bundle).is_file(): return f"{job_id[-8:]}: bundle missing ({bundle})"
    try:
        r = post(Path(bundle))
    except urllib.error.HTTPError as e:
        msg = f"refused ({e.code}) {e.read().decode(errors='replace')[:300]}"
        if e.code in (409, 422):   # the bundle itself is wrong: sending it again would only be refused again
            db.execute("UPDATE job SET status = 'failed', error = ? WHERE id = ?", (msg, job_id)); db.commit()
        return f"{job_id[-8:]}: {msg}"
    except (urllib.error.URLError, TimeoutError) as e:
        return f"{job_id[-8:]}: server unreachable ({e}), kept for later"
    t = now()
    db.execute("UPDATE job SET status = 'sent' WHERE id = ?", (job_id,))
    db.execute("UPDATE submission SET status = 'exported', exported_at = ? WHERE id = ?", (t, sid))
    db.commit()
    return f"{job_id[-8:]}: sent ({'already there' if r.get('already') else r.get('work', 'stored')})"


def send_ready(db: sqlite3.Connection, ids: list[str] | None = None) -> list[str]:
    """Send the given jobs (the start or the end of an id is enough), or every ready one."""
    if ids:
        full = []
        for i in ids:
            m = [r[0] for r in db.execute("SELECT id FROM job WHERE id LIKE ? OR id LIKE ?", (i + "%", "%" + i)).fetchall()]
            full += m if len(m) == 1 else []
            if len(m) != 1: print(f"{i}: {'no job' if not m else 'several jobs'} with this id")
    else:
        full = [r[0] for r in db.execute("SELECT id FROM job WHERE status = 'ready' ORDER BY finished_at").fetchall()]
    out = [send(db, j) for j in full]
    for line in out: print(line, flush=True)
    return out
