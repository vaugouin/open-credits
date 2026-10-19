"""Plex as the source of what a file is: TMDb and IMDb ids, title, year, edition, audio languages, credits markers.

Optional: without PLEX_SERVER_URL and PLEX_TOKEN (config.py), a job takes these from the command line. Plex is read
through its HTTP API, never through its database file. Plex paths are the server's (/volume1/...): OC_PATH_MAP turns
them into local ones."""
import json
import urllib.parse
import urllib.request
from functools import lru_cache
from pathlib import Path

from . import config

# ISO 639-2 audio codes (Plex streams) to the client's OCR languages. Other Latin-script languages read with the
# English model; a language without a model gives no hint.
AUDIO_LANG = {"eng": "en", "jpn": "ja", "chi": "zh", "zho": "zh", "per": "fa", "fas": "fa",
              **{c: "en" for c in ("fra", "fre", "deu", "ger", "ita", "spa", "por", "nld", "dut", "swe", "dan",
                                   "nor", "fin", "pol", "ces", "cze", "hun", "ron", "rum", "cat", "tur", "ind")}}


def enabled() -> bool:
    return bool(config.get("PLEX_SERVER_URL") and config.get("PLEX_TOKEN"))


def get(path: str, **query) -> dict:
    query["X-Plex-Token"] = config.get("PLEX_TOKEN")
    url = config.get("PLEX_SERVER_URL").rstrip("/") + path + ("&" if "?" in path else "?") + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={"Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r: return json.load(r)["MediaContainer"]


@lru_cache(maxsize=1)
def libraries() -> dict[str, dict]:
    return {d["key"]: d for d in get("/library/sections").get("Directory", [])}


def sections() -> list[str]:
    if config.get("OC_PLEX_SECTIONS"): return [s.strip() for s in config.get("OC_PLEX_SECTIONS").split(",") if s.strip()]
    return [k for k, d in libraries().items() if d["type"] == "movie"]


def local(plex_path: str) -> str:
    for plex_prefix, local_prefix in config.path_map():
        if plex_path.startswith(plex_prefix + "/"): return local_prefix + "/" + plex_path[len(plex_prefix) + 1:]
    return plex_path


def latin(s: str) -> bool:
    return all(ord(c) < 0x250 or not c.isalpha() for c in s)


def item(rating_key: int) -> dict:
    """One Plex movie with its files (one per copy; multi-part copies keep their parts in order)."""
    d = get(f"/library/metadata/{rating_key}", includeMarkers=1)["Metadata"][0]
    ids = {g["id"].split("://")[0]: g["id"].split("://")[1] for g in d.get("Guid", [])}
    library_lang = libraries().get(str(d.get("librarySectionID")), {}).get("language") or ""
    copies = []
    for m in d.get("Media", []):
        parts = [dict(file=local(p["file"]), size=p.get("size"), duration_s=(p.get("duration") or 0) / 1000,
                      audio=[s.get("languageCode") for s in sorted((s for s in p.get("Stream", []) if s["streamType"] == 2),
                                                                   key=lambda s: not s.get("default"))])
                 for p in m.get("Part", [])]
        copies.append(dict(height=m.get("height"), parts=parts))
    title = d["title"]
    return dict(rating_key=int(d["ratingKey"]), title=title, year=d.get("year"), edition=d.get("editionTitle"),
                # the library language says what language Plex titles are in, unless the title is in another script
                title_language=library_lang.split("-")[0] or None if latin(title) else None,
                tmdb_movie_id=int(ids["tmdb"]) if "tmdb" in ids else None, imdb_id=ids.get("imdb"),
                markers=[dict(type=k["type"], start_s=k["startTimeOffset"] / 1000, end_s=k["endTimeOffset"] / 1000,
                              final=bool(k.get("final"))) for k in d.get("Marker", [])],
                copies=copies)


def audio_hint(copy: dict) -> str | None:
    """The OCR language the default audio track suggests. Only a hint: a dubbed copy keeps the original
    credits (Le Voyage de Chihiro, French audio first, Japanese credits), and a Disney copy has English
    credits over Japanese audio."""
    for code in copy["parts"][0]["audio"] if copy["parts"] else []:
        if code in AUDIO_LANG: return AUDIO_LANG[code]
    return None


def find(local_path: str) -> int | None:
    """The Plex movie holding this file: searched by file name, confirmed by the size."""
    p = Path(local_path); size = p.stat().st_size
    for key in sections():
        for m in get(f"/library/sections/{key}/all", file=p.name).get("Metadata", []):
            for media in m.get("Media", []):
                if any(Path(part["file"]).name == p.name and part.get("size") == size for part in media.get("Part", [])):
                    return int(m["ratingKey"])
    return None


def recent(n: int, since: int | None = None) -> list[dict]:
    """Movies added most recently, newest first: rating key and addedAt (Unix seconds). With since, only those
    added after it."""
    out = []
    for key in sections():
        c = get(f"/library/sections/{key}/all", sort="addedAt:desc", **{"X-Plex-Container-Start": 0, "X-Plex-Container-Size": n})
        out += [dict(rating_key=int(m["ratingKey"]), added_at=int(m.get("addedAt", 0))) for m in c.get("Metadata", [])
                if since is None or int(m.get("addedAt", 0)) > since]
    return sorted(out, key=lambda m: -m["added_at"])[:n]


def catalogue(section: str, start: int, size: int) -> list[dict]:
    """One page of a library, newest additions first: rating key, TMDb id, title, year, addedAt."""
    c = get(f"/library/sections/{section}/all", sort="addedAt:desc", includeGuids=1,
            **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": size})
    out = []
    for m in c.get("Metadata", []):
        tmdb = [g["id"][7:] for g in m.get("Guid", []) if g["id"].startswith("tmdb://")]
        out.append(dict(rating_key=int(m["ratingKey"]), tmdb_movie_id=int(tmdb[0]) if tmdb else None, title=m.get("title"),
                        year=m.get("year"), added_at=int(m.get("addedAt", 0))))
    return out


def best_copy(copies: list[dict]) -> dict | None:
    """The copy a job reads when a movie has several: single-file, 1080 lines if there is one (fast to decode,
    sharp enough for credits), else the tallest under 1080, else the smallest file."""
    single = [c for c in copies if len(c["parts"]) == 1]
    if not single: return None
    return min(single, key=lambda c: (abs((c["height"] or 0) - 1080) if (c["height"] or 0) <= 1080 else 10_000,
                                      c["parts"][0]["size"] or 0))
