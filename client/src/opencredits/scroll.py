"""Scroll measurement: vertical shift between consecutive frames, roll boundaries, page offsets."""
from pathlib import Path

import numpy as np
from PIL import Image

INK = 128          # a pixel brighter than this is text (white credits on black)
MAX_SHIFT = 400    # px per frame searched upward
STEADY = 0.98      # correlation of row profiles above which the shift is trusted
MIN_SHIFT = 20     # px; below this the picture is not scrolling


def gray(path: Path) -> np.ndarray:
    return np.asarray(Image.open(path).convert("L"), dtype=np.float32)


def shifts(frames: dict[int, Path]) -> list[tuple[int, float, int, float]]:
    """(t, ink %, shift px from the previous frame, correlation) for each frame after the first."""
    out, prev = [], None
    for t in sorted(frames):
        a = gray(frames[t]); prof = (a > INK).sum(1).astype(np.float32)
        if prev is not None:
            best, bs = 0, 0.0
            for s in range(min(MAX_SHIFT, len(prof) - 1)):
                p0, p1 = prev[s:], prof[:len(prof) - s]
                c = float(np.dot(p0, p1) / (np.linalg.norm(p0) * np.linalg.norm(p1) + 1e-6))
                if c > bs: bs, best = c, s
            out.append((t, round(float((a > INK).mean()) * 100, 2), best, round(bs, 3)))
        prev = prof
    return out


def find_roll(rows: list[tuple[int, float, int, float]], max_gap: int = 2) -> tuple[int, int]:
    """Longest run of steadily scrolling frames, bridging up to max_gap blank frames (a blank frame has no profile).

    Returns (first, last) frame times of the roll: first is the frame before the first steady shift."""
    steady = [t for t, ink, s, c in rows if c >= STEADY and s >= MIN_SHIFT]
    if not steady: raise ValueError("no steady scroll found")
    runs, cur = [], [steady[0]]
    for t in steady[1:]:
        if t - cur[-1] <= max_gap + 1: cur.append(t)
        else: runs.append(cur); cur = [t]
    runs.append(cur)
    best = max(runs, key=lambda r: r[-1] - r[0])
    return best[0] - 1, best[-1]


def offsets(rows: list[tuple[int, float, int, float]], first: int, last: int) -> dict[int, int]:
    """Page offset of each roll frame. A frame without a trusted shift (blank) keeps the previous speed."""
    shift = {t: s for t, ink, s, c in rows if c >= STEADY and s >= MIN_SHIFT}
    offs, last_s = {first: 0}, next(shift[t] for t in sorted(shift) if t > first)
    for t in range(first + 1, last + 1):
        s = shift.get(t, last_s)
        offs[t] = offs[t - 1] + s; last_s = s
    return offs


def speeds(offs: dict[int, int]) -> list[tuple[int, int, int]]:
    """Stretches of constant speed, (from t, to t, median px/s), with a 10 px/s tolerance (a single frame can measure a few px off)."""
    ts = sorted(offs); runs: list[list] = []
    for a, b in zip(ts, ts[1:]):
        s = offs[b] - offs[a]
        if runs and abs(runs[-1][2][0] - s) <= 10: runs[-1][1] = b; runs[-1][2].append(s)
        else: runs.append([a, b, [s]])
    return [(a, b, sorted(v)[len(v) // 2]) for a, b, v in runs]
