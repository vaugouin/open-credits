"""Settings and the client's local folder.

The folder (%LOCALAPPDATA%/opencredits, or OC_DATA) holds the SQLite file, the queue's work folders and the
outbox. It must be on a local disk: SQLite's file locks are unreliable on network shares (technology-choices,
section 4). Settings come from opencredits.env in that folder (KEY=VALUE lines), overridden by the environment:

  PLEX_SERVER_URL, PLEX_TOKEN   the Plex server and its X-Plex-Token (optional: without them, jobs are given by hand)
  OC_PLEX_SECTIONS              movie library keys to read, comma-separated (default: every movie library)
  OC_PATH_MAP                   Plex path prefix = local prefix, several separated by ';' (/volume1/sharing=T:/)
  OC_SERVER_URL                 where bundles are sent (default: the pilot's server)
  OC_REVIEW_USER, OC_REVIEW_PASSWORD   basic-auth login of the server"""
import ctypes
import os
from functools import lru_cache
from pathlib import Path

SERVER_URL = "https://www.vaugouin.com/oc-review/"


def data_dir() -> Path:
    if os.environ.get("OC_DATA"): return Path(os.environ["OC_DATA"])
    base = Path(os.environ["LOCALAPPDATA"]) if os.environ.get("LOCALAPPDATA") else Path.home() / ".local" / "share"
    return base / "opencredits"


@lru_cache(maxsize=1)
def _file() -> dict[str, str]:
    p = data_dir() / "opencredits.env"; out = {}
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1); out[k.strip()] = v.strip().strip('"').strip("'")
    return out


def get(key: str, default: str | None = None) -> str | None:
    return os.environ.get(key) or _file().get(key) or default


def path_map() -> list[tuple[str, str]]:
    """(Plex prefix, local prefix) pairs, longest Plex prefix first."""
    pairs = [tuple(s.split("=", 1)) for s in (get("OC_PATH_MAP") or "").split(";") if "=" in s]
    return sorted(((a.strip().rstrip("/"), b.strip().rstrip("/\\")) for a, b in pairs), key=lambda p: -len(p[0]))


def is_network(path: Path) -> bool:
    """A UNC path or a mapped network drive (Windows); a mount elsewhere is not detected."""
    s = str(path.resolve() if path.exists() else path.absolute())
    if s.startswith(("\\\\", "//")): return True
    if os.name == "nt" and len(s) > 1 and s[1] == ":":
        return ctypes.windll.kernel32.GetDriveTypeW(f"{s[0]}:\\") == 4   # DRIVE_REMOTE
    return False
