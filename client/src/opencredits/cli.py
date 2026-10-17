"""Command line: opencredits run VIDEO --from S --to S --work DIR [--engine paddle] [--tmdb-credits FILE].

Each stage writes its output to the work folder and is skipped when that output is already there,
so a run can be resumed or redone from one stage by deleting its file."""
import argparse
import json
from pathlib import Path

from PIL import Image

from . import clean, frames, ocr, page, reference, scroll, vote


def stage_json(path: Path, build):
    if path.exists(): return json.loads(path.read_text(encoding="utf-8"))
    data = build(); path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    return data


def run(a) -> None:
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    end = a.to if a.to is not None else int(frames.duration(a.video))
    print(f"1. frames {a.start}..{end} s")
    fr = frames.extract(a.video, a.start, end, work / "frames")
    h = Image.open(next(iter(fr.values()))).height; w = Image.open(next(iter(fr.values()))).width

    print("2. scroll")
    rows = [tuple(r) for r in stage_json(work / "scroll.json", lambda: scroll.shifts(fr))]
    first, last = scroll.find_roll(rows)
    offs = scroll.offsets(rows, first, last)
    for f, t, s in scroll.speeds(offs): print(f"   {f}..{t} s: {s} px/s")
    print(f"   roll {first}..{last} s, {len(offs)} frames, page {max(offs.values()) + h} px")

    if not (work / "page.png").exists():
        print("3. virtual page"); page.stitch(fr, offs, work / "page.png")

    tag = f"{a.engine}-{a.lang}"
    print(f"4. OCR, {a.engine}, {a.lang}")
    def read():
        rs, per = ocr.read_roll(a.engine, a.lang, fr, offs)
        print(f"   {per:.2f} s/frame"); return dict(engine=a.engine, lang=a.lang, seconds_per_frame=per, readings=rs)
    readings = stage_json(work / f"readings-{tag}.json", read)["readings"]

    print("5. vote")
    lines = vote.vote(readings, h)
    if a.lang in ("ja", "zh"): lines = vote.join_spaced(lines)
    lines = clean.clean(lines, name_x0=w // 2 - 20, lang=a.lang)
    (work / f"lines-{tag}.json").write_text(json.dumps(lines, ensure_ascii=False, indent=0), encoding="utf-8")
    (work / f"lines-{tag}.txt").write_text(
        "".join(f'{l["y"]:6} {l["x0"]:5}-{l["x1"]:<5} {l["agree"]}/{l["seen"]}  {l["text"]}' + (f'  (read: {l["raw"]})' if "raw" in l else "") + "\n" for l in lines), encoding="utf-8")
    print(f"   {len(lines)} lines, {sum(1 for l in lines if l['seen'] == 1)} seen once, {sum(1 for l in lines if 'raw' in l)} cleaned -> lines-{tag}.txt")

    if a.tmdb_credits:
        print("6. TMDb reference")
        people = reference.load_tmdb(Path(a.tmdb_credits), a.tmdb_movie)
        m = reference.match(lines, people, name_x0=w // 2 - 20)
        out = [f"{'TMDb person':24} {'score':>5}  reading  [TMDb jobs]"]
        for p, (r, txt) in sorted(m["found"].items(), key=lambda kv: -kv[1][0]):
            out.append(f"{p:24} {r:5.2f}  {txt if r >= reference.CLOSE else '-'}  [{', '.join(people[p]['jobs'])}]")
        out.append(f"\n{len(people)} TMDb people: exact {m['exact']}, close {m['close']}, absent {m['absent']}")
        out.append(f"on screen, not in TMDb ({len(m['extra'])}): " + " | ".join(m["extra"]))
        (work / f"tmdb-{tag}.txt").write_text("\n".join(out) + "\n", encoding="utf-8")
        print("   " + out[-2].strip() + f"; {len(m['extra'])} on screen not in TMDb -> tmdb-{tag}.txt")


def main() -> None:
    p = argparse.ArgumentParser(prog="opencredits")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="read the rolling credits of a video file")
    r.add_argument("video", help="video file; it is only read")
    r.add_argument("--from", dest="start", type=int, required=True, help="search window start, seconds")
    r.add_argument("--to", type=int, help="search window end, seconds (default: end of file)")
    r.add_argument("--work", required=True, help="work folder for frames and results (never in the repository)")
    r.add_argument("--engine", choices=ocr.ENGINES, default="paddle")
    r.add_argument("--lang", choices=sorted(ocr.PADDLE_REC), default="en", help="language of the credits (recognition model)")
    r.add_argument("--tmdb-credits", help="result file of doc/sql/pilot-tmdb-credits.sql")
    r.add_argument("--tmdb-movie", type=int, help="TMDb movie ID of this title in that file")
    a = p.parse_args()
    if a.cmd == "run" and a.tmdb_credits and not a.tmdb_movie: p.error("--tmdb-credits needs --tmdb-movie")
    if a.cmd == "run": run(a)


if __name__ == "__main__":
    main()
