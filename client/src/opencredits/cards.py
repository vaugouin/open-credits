"""Cards: credits that stand still on screen (opening credits, end cards), read frame by frame.

A card is not found from the picture alone: a title that builds up over several cards (Alien) keeps the text
mask changing while the credits under it change too. Every frame outside the roll that holds text is read,
each line is followed through time, and lines on screen at the same time make one card."""
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from .scroll import text_mask
from .vote import Y_TOL, in_rows, norm, same_box

CARD_INK = 400      # text-mask pixels from which a frame is worth reading
MIN_SECONDS = 2     # a line on screen in fewer frames is a fade or noise
MIN_CONF = 0.6      # mean recognition confidence of a kept line
MAX_GAP = 2         # s; a line missing for this long (a fade) still continues
SAME_TEXT = 0.6     # similarity under which a reading at the same place is the next card, not the same line


def frames_with_text(frames: dict[int, Path], skip: set[int]) -> list[int]:
    return [t for t in sorted(frames) if t not in skip and int(text_mask(frames[t]).sum()) >= CARD_INK]


def read(read_fn, frames: dict[int, Path], ts: list[int], log=print) -> list[dict]:
    out = []
    for i, t in enumerate(ts):
        for r in read_fn(frames[t]):
            out.append(dict(r, t=t, y=(r["y0"] + r["y1"]) / 2))   # y in the frame: a card does not move
        if i % 20 == 19: log(f"  cards: {i + 1}/{len(ts)} frames")
    return out


def letters(s: str) -> int:
    """Letters and digits: a year alone (۱۳۸۹, 1979) is worth keeping on a last card."""
    return sum(1 for c in s if c.isalnum())


def lines(readings: list[dict]) -> list[dict]:
    """Each line followed through time: same place, same span, similar text, no gap longer than MAX_GAP.

    The text test matters: successive cast cards put each name at the same place (Alien)."""
    groups: list[dict] = []
    for r in sorted(readings, key=lambda r: (r["t"], r["y"])):
        for g in reversed(groups):
            if (r["t"] - g["t1"] <= MAX_GAP and abs(g["y"] - r["y"]) <= Y_TOL and same_box(g, r)
                    and SequenceMatcher(None, norm(g["r"][-1]["text"]), norm(r["text"])).ratio() >= SAME_TEXT):
                g["r"].append(r); g["t1"] = r["t"]; g["x0"] = min(g["x0"], r["x0"]); g["x1"] = max(g["x1"], r["x1"])
                break
        else:
            groups.append(dict(y=r["y"], x0=r["x0"], x1=r["x1"], t0=r["t"], t1=r["t"], r=[r]))
    out = []
    for g in groups:
        texts: dict[str, int] = {}
        for x in g["r"]: texts[norm(x["text"])] = texts.get(norm(x["text"]), 0) + 1
        text, n = max(texts.items(), key=lambda kv: kv[1])
        conf = float(np.mean([x["conf"] for x in g["r"]]))
        frames_seen = sorted({x["t"] for x in g["r"]})
        if len(frames_seen) < MIN_SECONDS or conf < MIN_CONF or letters(text) < 2: continue
        h = sorted(x["y1"] - x["y0"] for x in g["r"])[len(g["r"]) // 2]
        out.append(dict(y=round(g["y"]), x0=g["x0"], x1=g["x1"], h=h, text=text, agree=n, seen=len(g["r"]),
                        t0=g["t0"], t1=g["t1"], frames=frames_seen))
    return out


def group(ls: list[dict]) -> list[dict]:
    out: list[dict] = []
    for l in sorted(ls, key=lambda l: l["t0"]):
        if out and l["t0"] <= out[-1]["t1"]:
            out[-1]["lines"].append(l); out[-1]["t1"] = max(out[-1]["t1"], l["t1"])
        else:
            out.append(dict(t0=l["t0"], t1=l["t1"], lines=[l]))
    return out


def cards(card_lines: list[dict]) -> list[dict]:
    """Lines whose time spans overlap make one card; within a card, lines in reading order.

    A header that stays while the cards under it change ("U.S. PRODUCTION" over four Disney cards) would chain
    them into one: a line spanning two cards or more of the other lines is attached to each of them instead."""
    base = group(card_lines)
    headers = []
    for l in card_lines:
        others = group([m for m in card_lines if m is not l])
        if sum(1 for c in others if c["t0"] <= l["t1"] and c["t1"] >= l["t0"]) >= 2: headers.append(l)
    if headers:
        base = group([l for l in card_lines if l not in headers])
        for h in headers:
            hit = [c for c in base if c["t0"] <= h["t1"] and c["t1"] >= h["t0"]]
            for c in hit: c["lines"].append(dict(h, header=True))
            if not hit: base.append(dict(t0=h["t0"], t1=h["t1"], lines=[h]))
        base.sort(key=lambda c: c["t0"])
    for c in base: c["lines"] = in_rows(drop_pieces(c["lines"]))
    return base


def drop_pieces(ls: list[dict]) -> list[dict]:
    """A line read whole in some frames and word by word in others ("David Giler", "David" + "Giler"):
    the pieces go when they sit within the whole line and close together (gap under one character height).
    Pieces far apart ("music by" and "Jerry Goldsmith") are separate texts and the whole one goes."""
    drop = set()
    for i, w in enumerate(ls):
        inner = [j for j, p in enumerate(ls) if j != i and abs(p["y"] - w["y"]) <= Y_TOL
                 and p["x0"] >= w["x0"] - 10 and p["x1"] <= w["x1"] + 10]
        if len(inner) < 2: continue
        xs = sorted((ls[j]["x0"], ls[j]["x1"]) for j in inner)
        if all(b[0] - a[1] < w["h"] for a, b in zip(xs, xs[1:])): drop.update(inner)
        else: drop.add(i)
    return [l for k, l in enumerate(ls) if k not in drop]
