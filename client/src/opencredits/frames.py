"""Frame extraction with ffmpeg: one frame per second, named after its time in seconds."""
import subprocess
from pathlib import Path


def extract(video: str, start: int, end: int, out: Path, fps: int = 1) -> dict[int, Path]:
    """Extract frames from start to end (seconds, inclusive) into out/tNNNNN.png. The video is only read."""
    out.mkdir(parents=True, exist_ok=True)
    have = frames_in(out)
    if have and min(have) <= start and max(have) >= end:
        return {t: p for t, p in have.items() if start <= t <= end}
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", video,
                    "-t", str(end - start + 1), "-an", "-vf", f"fps={fps}", "-start_number", str(start),
                    "-y", str(out / "t%05d.png")], check=True)
    return {t: p for t, p in frames_in(out).items() if start <= t <= end}


def frames_in(folder: Path) -> dict[int, Path]:
    return {int(p.stem[1:]): p for p in sorted(folder.glob("t*.png"))}


def duration(video: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                       check=True, capture_output=True, text=True)
    return float(r.stdout.strip())
