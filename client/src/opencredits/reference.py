"""Reference check against TMDb credits. The only module that reads data from outside the open-credits tables.

Input: the result file of doc/sql/pilot-tmdb-credits.sql (mariadb table output), until the client reads TMDb itself."""
import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from pathlib import Path

CLOSE = 0.8      # similarity from which a reading counts as the same name, read or credited differently


def load_tmdb(path: Path, movie: int) -> dict[str, dict]:
    """Person name -> {"jobs": TMDb jobs (crew) or 'cast: character', "names": the name and its other forms}."""
    people: dict[str, dict] = {}; head = None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"): continue
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if "CAST_CHARACTER" in cells: head = cells; continue
        if head is None or len(cells) != len(head): continue
        r = dict(zip(head, cells))
        if r["ID_MOVIE"] != str(movie): continue
        p = people.setdefault(r["NAME"], dict(jobs=[], names=[r["NAME"]]))
        p["jobs"].append(r["CREW_JOB"] or f"cast: {r['CAST_CHARACTER']}")
        for a in (r.get("ALSO_KNOWN_AS") or "").split(" ; "):
            if a.strip() and a.strip() not in p["names"]: p["names"].append(a.strip())
    return people


@lru_cache(maxsize=1)
def _opencc():
    import opencc
    return opencc.OpenCC("s2t"), opencc.OpenCC("t2jp")


def fold(s: str) -> str:
    """Lower case, accents off, punctuation off; letters of every script kept, Chinese characters in their
    Japanese form (TMDb holds many Japanese names in simplified Chinese: 石桥彻郎 for 石橋徹郎)."""
    if re.search(r"[㐀-鿿]", s):
        s2t, t2jp = _opencc(); s = t2jp.convert(s2t.convert(s))
    s = "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[^\w ]", " ", s)).strip()


def best(names: list[str], lines: list[dict]) -> tuple[float, str]:
    """Best similarity of any of the names with any run of words of the same length in any line.

    Spaces are ignored in the comparison: Japanese credits space family and given names freely."""
    top = (0.0, "")
    for name in names:
        n = fold(name); k = len(n.split()); nk = n.replace(" ", "")
        for l in lines:
            w = fold(l["text"]).split()
            runs = {" ".join(w[i:i + k]) for i in range(max(1, len(w) - k + 1))} | {"".join(w)}
            for cand in runs:
                r = SequenceMatcher(None, nk, cand.replace(" ", "")).ratio()
                if r > top[0]: top = (r, l["text"])
    return top


def match(lines: list[dict], people: dict[str, dict], name_x0: int) -> dict:
    """TMDb people found on screen, and names on screen (right column, x0 > name_x0) missing from TMDb."""
    found = {p: best(v["names"], lines) for p, v in people.items()}
    known = [fold(n).replace(" ", "") for v in people.values() for n in v["names"]]
    extra = [l["text"] for l in lines if l["x0"] > name_x0
             and max(SequenceMatcher(None, fold(l["text"]).replace(" ", ""), k).ratio() for k in known) < CLOSE]
    return dict(found=found, extra=extra,
                exact=sum(1 for r, _ in found.values() if r == 1),
                close=sum(1 for r, _ in found.values() if CLOSE <= r < 1),
                absent=sum(1 for r, _ in found.values() if r < CLOSE))
