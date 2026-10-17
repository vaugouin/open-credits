# /// script
# requires-python = ">=3.11"
# dependencies = ["jsonschema>=4.23", "rfc3339-validator"]
# ///
"""Check a submission.json, or a submission bundle (.zip), against the open-credits format.

Two passes: the JSON Schema (schema/submission.schema.json), then what a schema cannot
express: references between objects, times inside their part, the copy fingerprint,
evidence files present in the zip. The client runs it before sending; the importer runs
it again on arrival.

Usage: uv run schema/check_submission.py <submission.json | bundle.zip> [...]
"""

import hashlib
import json
import sys
import zipfile
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

SCHEMA = json.loads((Path(__file__).parent / "submission.schema.json").read_text(encoding="utf-8"))


def fingerprint(parts):
    lines = [f"{p['opensubtitles_hash']}:{p['file_size']}" for p in sorted(parts, key=lambda p: p["part_index"])]
    return hashlib.sha256("\n".join(lines).encode("ascii")).hexdigest()


def check_references(doc, zip_names):
    errors = []
    parts = {p["part_index"]: p for p in doc["copy"]["parts"]}
    entities = {e["id"]: e for e in doc.get("entities", [])}
    seen_ids = set()

    def unique(obj_id, where):
        if obj_id in seen_ids:
            errors.append(f"{where}: id {obj_id} used twice")
        seen_ids.add(obj_id)

    def entity(ref, where, kinds=None):
        if ref is None:
            return
        if ref not in entities:
            errors.append(f"{where}: unknown entity {ref}")
        elif kinds and entities[ref]["kind"] not in kinds:
            errors.append(f"{where}: entity {ref} is a {entities[ref]['kind']}, expected {'/'.join(kinds)}")

    if sorted(parts) != list(range(1, len(parts) + 1)):
        errors.append("copy.parts: part_index must run 1, 2, 3... without gaps")
    if doc["copy"]["fingerprint"] != fingerprint(doc["copy"]["parts"]):
        errors.append("copy.fingerprint does not match the parts")
    offset = 0
    for i in sorted(parts):
        if parts[i]["offset_ms"] != offset:
            errors.append(f"part {i}: offset_ms {parts[i]['offset_ms']}, expected {offset}")
        offset += parts[i]["duration_ms"]

    for e in doc.get("entities", []):
        unique(e["id"], "entity")

    for s in doc["segments"]:
        where = f"segment {s['id']}"
        unique(s["id"], where)
        part = parts.get(s["part_index"])
        if part is None:
            errors.append(f"{where}: unknown part_index {s['part_index']}")
            continue
        if not s["start_ms"] < s["end_ms"] <= part["duration_ms"]:
            errors.append(f"{where}: start_ms < end_ms <= part duration is false")
        frames = {}
        for f in s["frames"]:
            unique(f["id"], f"frame {f['id']}")
            frames[f["id"]] = f
            if not s["start_ms"] <= f["timecode_ms"] <= s["end_ms"]:
                errors.append(f"frame {f['id']}: timecode outside its segment")
            ev = f.get("evidence")
            if ev:
                if ev["file"] != f"frames/{f['id']}.webp":
                    errors.append(f"frame {f['id']}: evidence file must be frames/{f['id']}.webp")
                if zip_names is not None and ev["file"] not in zip_names:
                    errors.append(f"frame {f['id']}: {ev['file']} missing from the bundle")
        lines = set()
        for t in s["text_lines"]:
            unique(t["id"], f"text line {t['id']}")
            lines.add(t["id"])
            if t["agreeing"] > t["readings"]:
                errors.append(f"text line {t['id']}: agreeing > readings")
            if t["first_ms"] > t["last_ms"]:
                errors.append(f"text line {t['id']}: first_ms > last_ms")
            for fid in t["frame_ids"]:
                if fid not in frames:
                    errors.append(f"text line {t['id']}: frame {fid} not in its segment")
        for b in s.get("blocks", []):
            unique(b["id"], f"block {b['id']}")
            entity(b.get("vendor_entity_ref"), f"block {b['id']}", ["company"])
            for lid in b["line_ids"]:
                if lid not in lines:
                    errors.append(f"block {b['id']}: line {lid} not in its segment")
            for c in b["credits"]:
                where_c = f"credit {c['id']}"
                unique(c["id"], where_c)
                entity(c.get("entity_ref"), where_c, [c["entity_kind"]] if c["entity_kind"] in ("person", "company", "place", "song") else None)
                entity(c.get("role_target_entity_ref"), where_c, ["person"])
                entity(c.get("song_ref"), where_c, ["song"])
                for lid in c["line_ids"]:
                    if lid not in b["line_ids"]:
                        errors.append(f"{where_c}: line {lid} not in its block")
    return errors


def describe_work(w):
    """The work as the bundle names it, to eyeball that title_hint and the ids agree."""
    ids = [f"{k} {w[k]}" for k in ("tmdb_movie_id", "tmdb_serie_id", "imdb_id", "wikidata_id") if k in w]
    if w["kind"] == "episode" and "season_number" in w:
        ids.insert(1, f"S{w['season_number']:02}E{w.get('episode_number', 0):02}")
    lang = f" [{w['title_language']}]" if "title_language" in w else ""
    year = f" ({w['year']})" if "year" in w else ""
    return f"{w['kind']} \"{w['title_hint']}\"{lang}{year}, {', '.join(ids)}"


def load(path):
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as z:
            return json.loads(z.read("submission.json").decode("utf-8")), set(z.namelist())
    return json.loads(path.read_text(encoding="utf-8")), None


def main(paths):
    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    failed = False
    for name in paths:
        doc, zip_names = load(Path(name))
        errors = [f"{'/'.join(map(str, e.absolute_path)) or '(root)'}: {e.message}" for e in validator.iter_errors(doc)]
        if not errors:
            errors = check_references(doc, zip_names)
        if errors:
            failed = True
            print(f"{name}: {len(errors)} error(s)")
            for e in errors:
                print(f"  {e}")
        else:
            print(f"{name}: valid, {describe_work(doc['work'])}")
    return 1 if failed else 0


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    sys.exit(main(sys.argv[1:]))
