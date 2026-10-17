"""Vote across frames: readings of the same line (page height, horizontal span) grouped, majority text kept."""
import re
from collections import Counter

Y_TOL = 14       # px on the page between readings of the same line
EDGE = 4         # px; a box this close to the top or bottom of the frame is a cut line
SPAN = 0.7       # horizontal overlap, as a share of the wider box, for two readings to be the same line


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def same_box(g: dict, r: dict) -> bool:
    # a reading that merges job and name spans both columns, so it forms its own group
    ov = min(g["x1"], r["x1"]) - max(g["x0"], r["x0"])
    return ov > SPAN * max(g["x1"] - g["x0"], r["x1"] - r["x0"])


RTL_GAP = 0.6    # words of one right-to-left line closer than this many character heights are one text


def join_words_rtl(readings: list[dict]) -> list[dict]:
    """Right-to-left scripts (Persian): the detector boxes each word, so the words of a name or a job are
    joined, per frame, rightmost first. Columns stand far apart (A Separation: 280 px), words touch."""
    out: list[dict] = []
    by_frame: dict[int, list[dict]] = {}
    for r in readings: by_frame.setdefault(r["t"], []).append(r)
    for t, rs in sorted(by_frame.items()):
        rows: list[list[dict]] = []
        for r in sorted(rs, key=lambda r: (r["y0"] + r["y1"]) / 2):
            if rows and abs((r["y0"] + r["y1"]) / 2 - (rows[-1][0]["y0"] + rows[-1][0]["y1"]) / 2) <= (r["y1"] - r["y0"]) / 2:
                rows[-1].append(r)
            else: rows.append([r])
        for row in rows:
            cur = None
            for r in sorted(row, key=lambda r: -r["x1"]):
                h = max(r["y1"] - r["y0"], 1)
                if cur and cur["x0"] - r["x1"] < RTL_GAP * h:
                    page = cur["y"] - (cur["y0"] + cur["y1"]) / 2        # page offset of this frame
                    cur = dict(cur, x0=min(cur["x0"], r["x0"]), y0=min(cur["y0"], r["y0"]), y1=max(cur["y1"], r["y1"]),
                               text=f'{cur["text"]} {r["text"]}', conf=min(cur["conf"], r["conf"]))
                    cur["y"] = page + (cur["y0"] + cur["y1"]) / 2
                else:
                    if cur: out.append(cur)
                    cur = dict(r)
            if cur: out.append(cur)
    return out


def vote(readings: list[dict], frame_height: int) -> list[dict]:
    rs = [r for r in readings if r["y0"] > EDGE and r["y1"] < frame_height - EDGE]
    groups: list[dict] = []
    for r in sorted(rs, key=lambda r: r["y"]):
        for g in groups[-12:]:
            if abs(g["y"] - r["y"]) <= Y_TOL and same_box(g, r):
                g["r"].append(r); g["y"] = sum(x["y"] for x in g["r"]) / len(g["r"])
                g["x0"] = min(g["x0"], r["x0"]); g["x1"] = max(g["x1"], r["x1"]); break
        else:
            groups.append(dict(y=r["y"], x0=r["x0"], x1=r["x1"], r=[r]))
    lines = []
    for g in groups:
        text, n = Counter(norm(x["text"]) for x in g["r"]).most_common(1)[0]
        h = sorted(x["y1"] - x["y0"] for x in g["r"])[len(g["r"]) // 2]
        lines.append(dict(y=round(g["y"]), x0=g["x0"], x1=g["x1"], h=h, text=text, agree=n, seen=len(g["r"]),
                          frames=sorted({x["t"] for x in g["r"]})))

    def covered(l):
        # job + name read as one box: dropped when well-seen narrower lines at the same height cover it
        inner = [m for m in lines if m is not l and m["seen"] > 1 and abs(m["y"] - l["y"]) <= Y_TOL
                 and m["x0"] >= l["x0"] - 10 and m["x1"] <= l["x1"] + 10]
        return len(inner) >= 2 or (len(inner) == 1 and inner[0]["seen"] > l["seen"])
    lines = [l for l in lines if not covered(l)]

    def fragment(l):
        # one word of a line, or a stray mark, read in a single frame
        if l["seen"] > 1: return False
        if len(l["text"]) <= 2: return True
        return any(m is not l and m["seen"] > 1 and abs(m["y"] - l["y"]) <= Y_TOL
                   and min(m["x1"], l["x1"]) - max(m["x0"], l["x0"]) > 0 for m in lines)
    lines = [l for l in lines if not fragment(l)]
    return in_rows(lines)


def in_rows(lines: list[dict]) -> list[dict]:
    """Lines in reading order: rows of lines within Y_TOL of the row's first line, each row left to right."""
    rows: list[list[dict]] = []
    for l in sorted(lines, key=lambda l: l["y"]):
        if rows and abs(l["y"] - rows[-1][0]["y"]) <= Y_TOL: rows[-1].append(l)
        else: rows.append([l])
    return [l for r in rows for l in sorted(r, key=lambda l: l["x0"])]


def join_spaced(lines: list[dict]) -> list[dict]:
    """Chinese and Japanese: rejoin a name the typesetting spaced out ("柊   瑠美", "大泉  洋", "ハ  ク").

    The gap alone cannot tell a spaced name from two names in adjacent columns, so only short pieces are
    joined: one of them at most 2 characters, together at most 4, gap under 2.5 character heights."""
    out: list[dict] = []
    for l in in_rows(lines):
        a = out[-1] if out else None
        if a and abs(a["y"] - l["y"]) <= Y_TOL:
            ta, tb = a["text"].replace(" ", ""), l["text"].replace(" ", "")
            if tb in ta and l["x0"] >= a["x0"] - a["h"] and l["x1"] <= a["x1"] + a["h"]:   # a second reading of a piece already there
                continue
        if a and abs(a["y"] - l["y"]) <= Y_TOL and -a["h"] <= l["x0"] - a["x1"] < 2.5 * max(a["h"], l["h"]):
            if min(len(ta), len(tb)) <= 2 and len(ta) + len(tb) <= 4:
                out[-1] = dict(a, x1=max(a["x1"], l["x1"]), text=f"{a['text']} {l['text']}",
                               agree=min(a["agree"], l["agree"]), seen=min(a["seen"], l["seen"]),
                               frames=sorted(set(a["frames"]) | set(l["frames"])))
                continue
        out.append(l)
    return out
