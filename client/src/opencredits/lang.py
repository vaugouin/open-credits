"""Which OCR model reads a copy's credits, decided on its frames.

The audio language is not enough: a dubbed copy keeps its original credits (Le Voyage de Chihiro: French audio
first, Japanese credits) and the Disney copy of Spirited Away has English credits over Japanese audio. So a few
frames with the most text are read with the base model, which reads Japanese, Chinese and English, and the script
of what it reads decides. The base model cannot read Arabic script: when it reads nothing convincing, the
Arabic-script model gets the same frames. The audio hint decides only when the frames do not."""
from pathlib import Path

from . import ocr
from .scroll import text_mask

SAMPLE = 6          # frames read
MIN_LETTERS = 40    # letters read below which the frames decide nothing


def text_frames(frames: dict[int, Path], n: int = SAMPLE) -> list[int]:
    """The n frames with the most text, at least 5 s apart (one roll position or one card each)."""
    ink = sorted(((int(text_mask(p).sum()), t) for t, p in frames.items() if t % 2 == 0), reverse=True)
    out: list[int] = []
    for _, t in ink:
        if all(abs(t - u) >= 5 for u in out): out.append(t)
        if len(out) == n: break
    return out


def script_counts(texts: list[str]) -> dict[str, int]:
    c = dict(kana=0, han=0, latin=0, arabic=0)
    for s in texts:
        for ch in s:
            o = ord(ch)
            if 0x3040 <= o <= 0x30FF: c["kana"] += 1
            elif 0x4E00 <= o <= 0x9FFF or 0x3400 <= o <= 0x4DBF: c["han"] += 1
            elif 0x0600 <= o <= 0x06FF or 0xFB50 <= o <= 0xFEFF: c["arabic"] += 1
            elif ch.isalpha() and o < 0x250: c["latin"] += 1
    return c


def decide(c: dict[str, int], conf: float) -> str | None:
    letters = sum(c.values())
    if letters < MIN_LETTERS: return None
    if c["kana"] >= 0.05 * letters: return "ja"
    if c["han"] >= 0.5 * letters: return "zh"
    if c["arabic"] >= 0.7 * letters: return "fa"
    if c["latin"] >= 0.7 * letters and conf >= 0.85: return "en"
    return None


def read(lang: str, frames: dict[int, Path], ts: list[int]) -> tuple[dict[str, int], float]:
    rd = ocr.reader("paddle", lang); rs = [r for t in ts for r in rd(frames[t])]
    return script_counts([r["text"] for r in rs]), (sum(r["conf"] for r in rs) / len(rs) if rs else 0.0)


def detect(frames: dict[int, Path], hint: str | None = None, log=print) -> tuple[str, str]:
    """(language, how it was decided)."""
    ts = text_frames(frames)
    if not ts: return (hint or "en"), "no text frame: " + ("audio hint" if hint else "default")
    c, conf = read("ja", frames, ts)       # the base model: Japanese, Chinese and English
    log(f"   base model on {len(ts)} frames: {c}, confidence {conf:.2f}")
    found = decide(c, conf)
    if found: return found, f"frames ({c}, confidence {conf:.2f})"
    c2, conf2 = read("fa", frames, ts)
    log(f"   Arabic-script model: {c2}, confidence {conf2:.2f}")
    if decide(c2, conf2) == "fa" and conf2 >= 0.8: return "fa", f"frames, Arabic script ({c2}, confidence {conf2:.2f})"
    return (hint or "en"), "frames undecided: " + ("audio hint" if hint else "default")
