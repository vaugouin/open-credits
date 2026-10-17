"""OCR engines. Each returns one reading per detected text line: frame box (px) and text."""
import time
from pathlib import Path

ENGINES = ("paddle", "tesseract")
# PP-OCRv5 recognition model per credits language: the base model reads Chinese, Japanese and English,
# the Arabic-script model reads Persian (PaddleOCR maps fa to it)
PADDLE_REC = {"en": "en_PP-OCRv5_mobile_rec", "ja": "PP-OCRv5_mobile_rec", "zh": "PP-OCRv5_mobile_rec",
              "fa": "arabic_PP-OCRv5_mobile_rec"}
TESSERACT_LANG = {"en": "eng", "ja": "jpn", "zh": "chi_sim", "fa": "fas"}
TESSERACT_EXE = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
THRESHOLD = 110    # Tesseract input: brighter than this becomes black ink on white


def reader(engine: str, lang: str = "en"):
    """A function path -> [dict(x0, y0, x1, y1, text, conf)]."""
    if engine == "paddle":
        from paddleocr import PaddleOCR
        o = PaddleOCR(text_detection_model_name="PP-OCRv5_mobile_det", text_recognition_model_name=PADDLE_REC[lang],
                      use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False,
                      enable_mkldnn=True)

        def read(path: Path) -> list[dict]:
            r = o.predict(str(path))[0]
            return [dict(x0=int(b[0]), y0=int(b[1]), x1=int(b[2]), y1=int(b[3]), text=txt, conf=float(sc))
                    for txt, sc, b in zip(r["rec_texts"], r["rec_scores"], r["rec_boxes"]) if txt.strip()]
        return read
    if engine == "tesseract":
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_EXE

        def read(path: Path) -> list[dict]:
            im = Image.open(path).convert("L").point(lambda v: 0 if v > THRESHOLD else 255)
            d = pytesseract.image_to_data(im, lang=TESSERACT_LANG[lang], config="--psm 11", output_type=pytesseract.Output.DICT)
            lines: dict[tuple, list[int]] = {}
            for i, w in enumerate(d["text"]):
                if w.strip() and float(d["conf"][i]) >= 0:
                    lines.setdefault((d["block_num"][i], d["par_num"][i], d["line_num"][i]), []).append(i)
            return [dict(x0=min(d["left"][i] for i in ix), y0=min(d["top"][i] for i in ix),
                         x1=max(d["left"][i] + d["width"][i] for i in ix), y1=max(d["top"][i] + d["height"][i] for i in ix),
                         text=" ".join(d["text"][i] for i in ix),
                         conf=sum(float(d["conf"][i]) for i in ix) / len(ix) / 100) for ix in lines.values()]
        return read
    raise ValueError(f"unknown engine {engine}")


def read_roll(engine: str, lang: str, frames: dict[int, Path], offs: dict[int, int], log=print) -> tuple[list[dict], float]:
    """Read every roll frame; each reading gets its frame time t and its page height y (centre of the box)."""
    read = reader(engine, lang); out = []; t0 = time.time()
    for i, t in enumerate(sorted(offs)):
        for r in read(frames[t]):
            out.append(dict(r, t=t, y=offs[t] + (r["y0"] + r["y1"]) / 2))
        if i % 20 == 19: log(f"  {engine}: {i + 1}/{len(offs)} frames")
    return out, (time.time() - t0) / len(offs)
