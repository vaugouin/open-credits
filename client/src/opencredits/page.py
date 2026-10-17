"""Virtual page: the roll frames stacked at their offsets, for review."""
from pathlib import Path

import numpy as np
from PIL import Image


def stitch(frames: dict[int, Path], offs: dict[int, int], out: Path) -> tuple[int, int]:
    """Max-blend every roll frame at its offset; returns the page size (width, height)."""
    first = Image.open(frames[min(offs)]); w, h = first.size
    page = np.zeros((max(offs.values()) + h, w), dtype=np.uint8)
    for t, y in offs.items():
        a = np.asarray(Image.open(frames[t]).convert("L"))
        page[y:y + h] = np.maximum(page[y:y + h], a)
    Image.fromarray(page).save(out)
    return w, page.shape[0]
