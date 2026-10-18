"""Post-processing of voted lines: known OCR slips corrected, the voted text kept in raw when changed."""
import re
from functools import lru_cache

PARTICLES = {"la", "le", "les", "lo", "los", "las", "lu"}   # lower-case name particles that must stay as read


def opening_quote(text: str) -> str:
    """A word ending with a closing quote that was never opened gets its opening quote back.

    PP-OCRv5 drops a small opening quote: "Alien' head effects" for "'Alien' head effects"."""
    if text.count("'") % 2 == 0: return text
    return re.sub(r"(^|[\s(])([^\s'(]+)'(?=[\s)]|$)", r"\1'\2'", text, count=1)


def capital_i(text: str, name_column: bool) -> str:
    """In a name, a first word read with a lower-case l before lower-case letters is a capital I.

    In sans-serif typefaces the capital I and the lower-case l are the same glyph: "lan Whittaker" is "Ian Whittaker"."""
    if not name_column: return text
    words = text.split()
    if len(words) < 2 or not all(w[:1].isupper() for w in words[1:]): return text
    w = words[0]
    if len(w) >= 3 and w[0] == "l" and w[1:].isalpha() and w[1:].islower() and w.lower() not in PARTICLES:
        words[0] = "I" + w[1:]
    return " ".join(words)


INNER_CAPITAL = re.compile(r"^[A-Z][a-z]+[A-Z][a-z]{2,}$")    # McDonald, DeVito, MacArthur: kept as read (not DavId)


def small_caps(text: str) -> str:
    """A Latin word whose case is mixed with no pattern gets its letters after the first in lower case.

    In small capitals a lower-case letter is a smaller copy of the capital, and PP-OCRv5 answers the capital
    for some of them: "Tomohiko IshII" is "Tomohiko Ishii", "DONgURI" is "Donguri". Words all in lower or
    upper case, capitalised words, names with one inner capital and words that start in lower case (iPhone,
    a logo) are left as read."""
    def fix(m: re.Match) -> str:
        w = m.group(0)
        if w[0].islower() or w.isupper() or w[1:].islower() or INNER_CAPITAL.match(w): return w
        return w[0] + w[1:].lower()
    return re.sub(r"[A-Za-z]{2,}", fix, text)


@lru_cache(maxsize=1)
def _opencc():
    import opencc
    return opencc.OpenCC("s2t"), opencc.OpenCC("t2jp")


def japanese_forms(text: str) -> str:
    """Japanese credits: a character that exists only in simplified Chinese becomes its Japanese form.

    PP-OCRv5 is trained mostly on Chinese and sometimes answers 岛 for 島 or 凉 for 涼. A character that is
    also Japanese (国) or an old form kept in a name (亞, 齋) is left as read."""
    s2t, t2jp = _opencc()
    out = []
    for c in text:
        t = s2t.convert(c)
        out.append(t2jp.convert(t) if t != c and t2jp.convert(t) != c else c)
    return "".join(out)


# kanji (and the long-vowel mark) drawn exactly like a katakana: 八 ハ, 二 ニ, 口 ロ, 工 エ, 力 カ, 卜 ト, 夕 タ, 一 ー
KATAKANA_TWINS = str.maketrans("八二口工力卜夕一", "ハニロエカトター")
KATAKANA = re.compile(r"[ァ-ヺー]")


def katakana_twins(text: str) -> str:
    """A kanji that has a katakana twin becomes the katakana when the line around it is katakana ("八 ク" is "ハ ク")."""
    letters = text.replace(" ", "")
    if not letters or not KATAKANA.search(letters): return text
    twins = sum(1 for c in letters if c in "八二口工力卜夕一")
    if KATAKANA.findall(letters).__len__() + twins != len(letters): return text   # mixed with real kanji or kana: leave it
    return text.translate(KATAKANA_TWINS)


# Arabic letters that Persian writes with its own code points (yeh, kaf, and the final-form yeh), and the
# Arabic-Indic digits, which Persian writes with its own (١٣٨٩ is ۱۳۸۹)
PERSIAN_FORMS = str.maketrans({"ي": "ی", "ى": "ی", "ك": "ک", **{chr(0x0660 + d): chr(0x06f0 + d) for d in range(10)}})


# credit words the Arabic-script model reads with kaf for gaf (the gaf's second stroke dropped); names are not
# corrected, since a kaf in a name can be right
PERSIAN_GAF = {"کارکردان": "کارگردان", "کروه": "گروه", "بازیکر": "بازیگر", "کذار": "گذار"}


def persian_forms(text: str) -> str:
    """Persian credits: the Arabic yeh and kaf an Arabic-script model may answer become the Persian letters,
    and credit words read with kaf for gaf get their gaf back."""
    text = text.translate(PERSIAN_FORMS)
    for wrong, right in PERSIAN_GAF.items(): text = text.replace(wrong, right)
    return text


def clean(lines: list[dict], name_x0: int, lang: str = "en") -> list[dict]:
    for l in lines:
        text = l["text"]
        if lang == "ja": text = katakana_twins(japanese_forms(text))
        if lang == "fa": text = persian_forms(text)
        text = capital_i(small_caps(opening_quote(text)), l["x0"] > name_x0)
        if text != l["text"]: l["raw"], l["text"] = l["text"], text
    return lines
