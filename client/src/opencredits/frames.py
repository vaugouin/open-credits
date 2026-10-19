"""Frame extraction with ffmpeg: one frame per second, named after its time in seconds."""
import subprocess
from pathlib import Path

NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)   # under pythonw (the scheduled worker) ffmpeg would open a console


def extract(video: str, start: int, end: int, out: Path, fps: int = 1) -> dict[int, Path]:
    """Extract frames from start to end (seconds, inclusive) into out/tNNNNN.png. The video is only read."""
    out.mkdir(parents=True, exist_ok=True)
    have = {t: p for t, p in frames_in(out).items() if start <= t <= end}
    if len(have) >= (end - start) * fps:   # every frame there (frames outside the window say nothing about it)
        return have
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(start), "-i", video,
                    "-t", str(end - start + 1), "-an", "-vf", f"fps={fps}", "-start_number", str(start),
                    "-y", str(out / "t%05d.png")], check=True, creationflags=NO_WINDOW)
    return {t: p for t, p in frames_in(out).items() if start <= t <= end}


def frames_in(folder: Path) -> dict[int, Path]:
    return {int(p.stem[1:]): p for p in sorted(folder.glob("t*.png"))}


def duration(video: str) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", video],
                       check=True, capture_output=True, text=True, creationflags=NO_WINDOW)
    return float(r.stdout.strip())
