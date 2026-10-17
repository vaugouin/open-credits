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
        lines.append(dict(y=round(g["y"]), x0=g["x0"], x1=g["x1"], text=text, agree=n, seen=len(g["r"]),
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
    lines.sort(key=lambda l: (l["y"] // 20, l["x0"]))
    return lines
