"""Reference check against TMDb credits. The only module that reads data from outside the open-credits tables.

Input: the result file of doc/sql/pilot-tmdb-credits.sql (mariadb table output), until the client reads TMDb itself."""
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

CLOSE = 0.8      # similarity from which a reading counts as the same name, read or credited differently


def load_tmdb(path: Path) -> dict[str, list[str]]:
    """Person name -> TMDb jobs (crew) or 'cast: character'."""
    people: dict[str, list[str]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.split("|")[1:-1]]
        if len(cells) == 8 and cells[0] in ("cast", "crew"):
            typ, order, pid, name, imdb, dept, job, char = cells
            people.setdefault(name, []).append(job or f"cast: {char}")
    return people


def fold(s: str) -> str:
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9 ]", "", s).strip()


def best(name: str, lines: list[dict]) -> tuple[float, str]:
    """Best similarity of the name with any run of words of the same length in any line."""
    n = fold(name); k = len(n.split()); top = (0.0, "")
    for l in lines:
        w = fold(l["text"]).split()
        for i in range(max(1, len(w) - k + 1)):
            r = SequenceMatcher(None, n, " ".join(w[i:i + k])).ratio()
            if r > top[0]: top = (r, l["text"])
    return top


def match(lines: list[dict], people: dict[str, list[str]], name_x0: int) -> dict:
    """TMDb people found on screen, and names on screen (right column, x0 > name_x0) missing from TMDb."""
    found = {p: best(p, lines) for p in people}
    known = [fold(p) for p in people]
    extra = [l["text"] for l in lines if l["x0"] > name_x0
             and max(SequenceMatcher(None, fold(l["text"]), k).ratio() for k in known) < CLOSE]
    return dict(found=found, extra=extra,
                exact=sum(1 for r, _ in found.values() if r == 1),
                close=sum(1 for r, _ in found.values() if CLOSE <= r < 1),
                absent=sum(1 for r, _ in found.values() if r < CLOSE))
