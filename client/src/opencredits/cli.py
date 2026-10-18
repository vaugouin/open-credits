"""Command line: opencredits run VIDEO --from S --to S --work DIR [--lang] [--tmdb-credits FILE --tmdb-movie ID].

A run reads one time window: the rolling credits if the window holds a roll, and the cards (credits that stand
still) in the rest of it. Frames are shared in WORK/frames; each window writes to WORK/w<from>-<to>/. Each stage
is skipped when its output is already there, so a run can be resumed or redone from one stage by deleting its file."""
import argparse
import json
from pathlib import Path

from PIL import Image

from . import cards, clean, frames, ocr, page, reference, review, scroll, vote


def stage_json(path: Path, build):
    if path.exists(): return json.loads(path.read_text(encoding="utf-8"))
    data = build(); path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")
    return data


def fmt(l: dict) -> str:
    return f'{l["y"]:6} {l["x0"]:5}-{l["x1"]:<5} {l["agree"]}/{l["seen"]}  {l["text"]}' + (f'  (read: {l["raw"]})' if "raw" in l else "")


def finish(lines: list[dict], lang: str, name_x0: int) -> list[dict]:
    """Script-specific joining, then cleaning. name_x0: where names start (roll), 0 on cards, which centre them."""
    if lang in ("ja", "zh"): lines = vote.join_spaced(lines)
    return clean.clean(lines, name_x0=name_x0, lang=lang)


def run(a) -> None:
    work = Path(a.work); work.mkdir(parents=True, exist_ok=True)
    end = int(frames.duration(a.video)) if a.to is None else min(a.to, int(frames.duration(a.video)))   # a window past the end would re-extract every run
    win = work / f"w{a.start}-{end}"; win.mkdir(exist_ok=True)      # one folder per time window; frames are shared
    print(f"1. frames {a.start}..{end} s -> {win.name}")
    fr = frames.extract(a.video, a.start, end, work / "frames")
    h = Image.open(next(iter(fr.values()))).height; w = Image.open(next(iter(fr.values()))).width
    tag = f"{a.engine}-{a.lang}"

    print("2. scroll")
    rows = [tuple(r) for r in stage_json(win / "scroll.json", lambda: scroll.shifts(fr))]
    try:
        first, last = scroll.find_roll(rows)
    except ValueError:
        first = last = None; print("   no roll in this window")
    roll: set[int] = set()
    if first is not None:
        offs = scroll.offsets(rows, first, last); roll = set(offs)
        for f, t, s in scroll.speeds(offs): print(f"   {f}..{t} s: {s} px/s")
        print(f"   roll {first}..{last} s, {len(offs)} frames, page {max(offs.values()) + h} px")
        if not (win / "page.png").exists():
            print("3. virtual page"); page.stitch(fr, offs, win / "page.png")

        print(f"4. roll OCR, {a.engine}, {a.lang}")
        def read():
            rs, per = ocr.read_roll(a.engine, a.lang, fr, offs)
            print(f"   {per:.2f} s/frame"); return dict(engine=a.engine, lang=a.lang, seconds_per_frame=per, readings=rs)
        readings = stage_json(win / f"readings-{tag}.json", read)["readings"]

        print("5. vote")
        if a.lang in ("fa",): readings = vote.join_words_rtl(readings)
        lines = finish(vote.vote(readings, h), a.lang, w // 2 - 20)
        (win / f"lines-{tag}.json").write_text(json.dumps(lines, ensure_ascii=False, indent=0), encoding="utf-8")
        (win / f"lines-{tag}.txt").write_text("".join(fmt(l) + "\n" for l in lines), encoding="utf-8")
        print(f"   {len(lines)} lines, {sum(1 for l in lines if l['seen'] == 1)} seen once, {sum(1 for l in lines if 'raw' in l)} cleaned -> lines-{tag}.txt")

    if not a.no_cards:
        print(f"6. cards, {a.engine}, {a.lang}")
        def read_cards():
            ts = cards.frames_with_text(fr, roll)
            print(f"   {len(ts)} frames with text outside the roll")
            return dict(engine=a.engine, lang=a.lang, readings=cards.read(ocr.reader(a.engine, a.lang), fr, ts))
        cr = stage_json(win / f"card-readings-{tag}.json", read_cards)["readings"]
        if a.lang in ("fa",): cr = vote.join_words_rtl(cr)
        found = cards.cards(finish(cards.lines(cr), a.lang, 0))
        (win / f"cards-{tag}.json").write_text(json.dumps(found, ensure_ascii=False, indent=0), encoding="utf-8")
        (win / f"cards-{tag}.txt").write_text("".join(
            f'card {c["t0"]}..{c["t1"]} s\n' + "".join(fmt(l) + "\n" for l in c["lines"]) + "\n" for c in found), encoding="utf-8")
        print(f"   {len(found)} cards, {sum(len(c['lines']) for c in found)} lines -> cards-{tag}.txt")

    if a.tmdb_credits:
        # every window read so far in this work folder counts: opening cards, end roll, end cards
        every = []
        for f in sorted(work.glob(f"w*/lines-{tag}.json")): every += json.loads(f.read_text(encoding="utf-8"))
        for f in sorted(work.glob(f"w*/cards-{tag}.json")):
            for c in json.loads(f.read_text(encoding="utf-8")): every += c["lines"]
        print(f"7. TMDb reference, {len(every)} lines from {len({p.parent for p in work.glob(f'w*/*-{tag}.json')})} windows")
        people = reference.load_tmdb(Path(a.tmdb_credits), a.tmdb_movie)
        m = reference.match(every, people, name_x0=w // 2 - 20)
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
    r = sub.add_parser("run", help="read the credits (roll and cards) in one time window of a video file")
    r.add_argument("video", help="video file; it is only read")
    r.add_argument("--from", dest="start", type=int, required=True, help="search window start, seconds")
    r.add_argument("--to", type=int, help="search window end, seconds (default: end of file)")
    r.add_argument("--work", required=True, help="work folder for frames and results (never in the repository)")
    r.add_argument("--engine", choices=ocr.ENGINES, default="paddle")
    r.add_argument("--no-cards", action="store_true", help="read the roll only")
    r.add_argument("--lang", choices=sorted(ocr.PADDLE_REC), default="en", help="language of the credits (recognition model)")
    r.add_argument("--tmdb-credits", help="result file of doc/sql/pilot-tmdb-credits.sql")
    r.add_argument("--tmdb-movie", type=int, help="TMDb movie ID of this title in that file")
    v = sub.add_parser("review", help="sample the new lines of a work folder for a precision check, or score the verdicts")
    v.add_argument("--work", required=True, help="work folder of the title, after its runs")
    v.add_argument("--tag", default="paddle-en", help="engine-lang of the runs to sample")
    v.add_argument("--tmdb-credits", help="result file of doc/sql/pilot-tmdb-credits.sql")
    v.add_argument("--tmdb-movie", type=int)
    v.add_argument("--score", action="store_true", help="score WORK/review-TAG/verdicts.json")
    a = p.parse_args()
    if a.cmd in ("run", "review") and a.tmdb_credits and not a.tmdb_movie: p.error("--tmdb-credits needs --tmdb-movie")
    if a.cmd == "run": run(a)
    if a.cmd == "review":
        if a.score: print(review.score(Path(a.work) / f"review-{a.tag}")); return
        if not a.tmdb_credits: p.error("review needs --tmdb-credits and --tmdb-movie")
        out = review.build(Path(a.work), a.tag, reference.load_tmdb(Path(a.tmdb_credits), a.tmdb_movie), a.tmdb_movie)
        print(f"{out / 'index.html'}")


if __name__ == "__main__":
    main()
