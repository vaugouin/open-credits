"""Submission bundle (doc/submission-format.md): submission.json read straight from the contributor's SQLite file,
zipped as submission-<id>.zip. Columns that stay on this machine (part.local_path, frame.evidence_path,
submission.status and exported_at) are never read here."""
import json
import sqlite3
import zipfile
from pathlib import Path

FORMAT_VERSION = "0.1.0"


def _rows(db: sqlite3.Connection, sql: str, *args) -> list[dict]:
    cur = db.execute(sql, args)
    names = [d[0] for d in cur.description]
    return [dict(zip(names, r)) for r in cur.fetchall()]


def _clean(d: dict) -> dict:
    """The format leaves optional fields out rather than null."""
    return {k: v for k, v in d.items() if v is not None}


def document(db: sqlite3.Connection, sub_id: str) -> dict:
    s = _rows(db, "SELECT * FROM submission WHERE id = ?", sub_id)[0]
    c = _rows(db, "SELECT * FROM copy WHERE id = ?", s["copy_id"])[0]
    w = _rows(db, "SELECT * FROM work WHERE id = ?", c["work_id"])[0]
    parts = _rows(db, "SELECT * FROM part WHERE copy_id = ? ORDER BY part_index", c["id"])
    part_index = {p["id"]: p["part_index"] for p in parts}

    segments = []
    for g in _rows(db, "SELECT * FROM segment WHERE submission_id = ? ORDER BY start_ms", sub_id):
        frames = []
        for f in _rows(db, "SELECT * FROM frame WHERE segment_id = ? ORDER BY timecode_ms", g["id"]):
            boxes = [_clean(dict(x=b["x"], y=b["y"], w=b["w"], h=b["h"], text=b["text"], confidence=b["confidence"],
                                 font_height_px=b["font_height_px"],
                                 is_upper_case=None if b["is_upper_case"] is None else bool(b["is_upper_case"]),
                                 is_bold=None if b["is_bold"] is None else bool(b["is_bold"])))
                     for b in _rows(db, "SELECT * FROM text_box WHERE frame_id = ? ORDER BY y, x", f["id"])]
            frames.append(_clean(dict(id=f["id"], timecode_ms=f["timecode_ms"], phash=f["phash"],
                                      page_offset_px=f["page_offset_px"], text_boxes=boxes)))
        lines = [dict(id=t["id"], y_page=t["y_page"], x=t["x"], w=t["w"], h=t["h"], text=t["text"], readings=t["readings"],
                      agreeing=t["agreeing"], confidence=t["confidence"], frame_ids=json.loads(t["frame_ids"]),
                      first_ms=t["first_ms"], last_ms=t["last_ms"])
                 for t in _rows(db, "SELECT * FROM text_line WHERE segment_id = ? ORDER BY y_page, x", g["id"])]
        segments.append(_clean(dict(id=g["id"], part_index=part_index[g["part_id"]], kind=g["kind"], start_ms=g["start_ms"],
                                    end_ms=g["end_ms"], detected_by=g["detected_by"], layout=g["layout"],
                                    scroll_px_per_s=g["scroll_px_per_s"], frames=frames, text_lines=lines)))

    return dict(
        format_version=FORMAT_VERSION,
        submission=_clean(dict(id=s["id"], created_at=s["created_at"], client=dict(name=s["client_name"], version=s["client_version"]),
                               ocr=_clean(dict(engine=s["ocr_engine"], engine_version=s["ocr_engine_version"], models=s["ocr_models"],
                                               parameters=json.loads(s["parameters"]) if s["parameters"] else None)),
                               licence=s["licence"], vocabulary_version=s["vocabulary_version"],
                               has_evidence_frames=bool(s["has_evidence_frames"]))),
        work=_clean({k: w[k] for k in ("kind", "tmdb_movie_id", "tmdb_serie_id", "season_number", "episode_number",
                                       "imdb_id", "wikidata_id", "title_hint", "title_language", "year")}),
        copy=_clean(dict(fingerprint=c["fingerprint"], duration_ms=c["duration_ms"], width=c["width"], height=c["height"], fps=c["fps"],
                         edition_hint=c["edition_hint"], version_language=c["version_language"], source=c["source"],
                         parts=[{k: p[k] for k in ("part_index", "opensubtitles_hash", "file_size", "duration_ms", "offset_ms")}
                                for p in parts])),
        segments=segments)


def write(db: sqlite3.Connection, sub_id: str, out_dir: Path) -> Path:
    """submission-<id>.zip in out_dir. The submission stays in review: it is marked exported once sending exists."""
    doc = document(db, sub_id)
    out = out_dir / f"submission-{sub_id}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("submission.json", json.dumps(doc, ensure_ascii=False, indent=1))
    return out
