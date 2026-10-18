"""Precision check of the new lines (charter, decision 27 c): a random sample of the lines TMDb does not have,
each shown with a crop of a frame where it is on screen, for a person to judge; then the score of the verdicts."""
import base64
import html
import io
import json
import random
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

from PIL import Image

from . import config, frames, reference, scroll

SAMPLE = 50
SEED = 27            # fixed, so the same sample comes back for a title
MARGIN = 0.6         # crop margin around the line, in line heights
URL = "https://www.vaugouin.com/oc-review/"   # the review stack (review/ in this repository)
VERDICTS = [("exact", "exact: the text is what the screen shows"),
            ("minor", "minor: case, spacing or punctuation only"),
            ("wrong", "wrong: a letter or a word differs"),
            ("noise", "noise: not credit text on screen")]


def new_lines(work: Path, tag: str, people: dict[str, dict]) -> list[dict]:
    """Every line read in every window of the work folder (roll and cards) that holds no TMDb name of the title."""
    out = []
    for win in sorted(work.glob("w*")):
        f = win / f"lines-{tag}.json"
        if f.exists():
            for l in json.loads(f.read_text(encoding="utf-8")): out.append(dict(l, window=win.name, kind="roll"))
        f = win / f"cards-{tag}.json"
        if f.exists():
            for c in json.loads(f.read_text(encoding="utf-8")):
                out += [dict(l, window=win.name, kind="card") for l in c["lines"] if not l.get("header")]
    names = [v["names"] for v in people.values()]
    return [l for l in out if all(reference.best(n, [l])[0] < reference.CLOSE for n in names)]


def frame_y(l: dict, t: int, work: Path, cache: dict) -> float:
    """Line centre in frame t: card lines stand still; roll lines are on the page, minus the frame's offset."""
    if l["kind"] == "card": return l["y"]
    if l["window"] not in cache:
        rows = [tuple(r) for r in json.loads((work / l["window"] / "scroll.json").read_text(encoding="utf-8"))]
        cache[l["window"]] = scroll.offsets(rows, *scroll.find_roll(rows))
    return l["y"] - cache[l["window"]][t]


def build(work: Path, tag: str, people: dict[str, dict], movie: int, n: int = SAMPLE) -> Path:
    fr = frames.frames_in(work / "frames")
    lines = new_lines(work, tag, people)
    sample = sorted(random.Random(SEED).sample(lines, min(n, len(lines))), key=lambda l: (l["window"], l["frames"][0], l["y"]))
    out = work / f"review-{tag}"; (out / "crops").mkdir(parents=True, exist_ok=True)
    cache: dict = {}; items = []
    for i, l in enumerate(sample, 1):
        t = l["frames"][len(l["frames"]) // 2]
        im = Image.open(fr[t]); y = frame_y(l, t, work, cache); m = MARGIN * l["h"]
        box = (max(0, l["x0"] - 2 * m), max(0, y - l["h"] / 2 - m), min(im.width, l["x1"] + 2 * m), min(im.height, y + l["h"] / 2 + m))
        im.crop(tuple(round(v) for v in box)).save(out / "crops" / f"{i:02}.png")
        items.append(dict(id=i, text=l["text"], raw=l.get("raw"), kind=l["kind"], window=l["window"], t=t,
                          agree=l["agree"], seen=l["seen"]))
    (out / "sample.json").write_text(json.dumps(dict(title=work.name, movie=movie, tag=tag, seed=SEED, new_lines=len(lines), items=items),
                                                ensure_ascii=False, indent=1), encoding="utf-8")
    (out / "index.html").write_text(page(work.name, tag, len(lines), items), encoding="utf-8")
    return out


def page(title: str, tag: str, total: int, items: list[dict]) -> str:
    rtl = ' dir="auto"'
    rows = "".join(f'''
<div class="item" id="i{it["id"]}">
  <div class="meta">{it["id"]:02} · {it["kind"]} · {it["window"]} · {it["t"]} s · {it["agree"]}/{it["seen"]}</div>
  <img src="crops/{it["id"]:02}.png" alt="">
  <div class="text"{rtl}>{html.escape(it["text"])}</div>{f'<div class="raw"{rtl}>voted: {html.escape(it["raw"])}</div>' if it["raw"] else ""}
  <div class="v">{"".join(f'<label title="{html.escape(d)}"><input type="radio" name="v{it["id"]}" value="{k}"> {k}</label>' for k, d in VERDICTS)}
  <input class="note" name="n{it["id"]}" placeholder="what the screen shows, if different"{rtl}></div>
</div>''' for it in items)
    legend = "".join(f"<li>{html.escape(d)}</li>" for _, d in VERDICTS)
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Review {html.escape(title)}</title>
<style>
:root {{ --bg:#fafafa; --fg:#222; --card:#fff; --line:#ddd; --mute:#777; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#161616; --fg:#eee; --card:#222; --line:#444; --mute:#999; }} }}
body {{ background:var(--bg); color:var(--fg); font:16px/1.4 system-ui, sans-serif; margin:0 auto; max-width:1000px; padding:16px; }}
.item {{ background:var(--card); border:1px solid var(--line); border-radius:8px; padding:12px; margin:12px 0; }}
.item.done {{ opacity:.6; }}
img {{ max-width:100%; background:#000; display:block; margin:6px 0; }}
.meta, .raw {{ color:var(--mute); font-size:13px; }}
.text {{ font-size:22px; margin:4px 0; }}
.v label {{ margin-right:14px; white-space:nowrap; }}
.note {{ width:100%; box-sizing:border-box; margin-top:6px; padding:4px; font-size:16px; }}
#bar {{ position:sticky; top:0; background:var(--bg); padding:8px 0; border-bottom:1px solid var(--line); }}
</style></head><body>
<h1>{html.escape(title)}, {tag}</h1>
<p>{len(items)} lines drawn at random from the {total} lines that hold no TMDb name. Judge the text against the crop:</p><ul>{legend}</ul>
<div id="bar"><span id="count"></span> <button id="save">Save verdicts</button> (downloads <code>verdicts.json</code>: put it in this folder)</div>
{rows}
<script>
const KEY = "review-{html.escape(title)}-{tag}";
const ids = {json.dumps([it["id"] for it in items])};
function state() {{ const s = {{}}; for (const i of ids) {{ const v = document.querySelector(`input[name=v${{i}}]:checked`);
  s[i] = {{verdict: v ? v.value : null, note: document.querySelector(`input[name=n${{i}}]`).value}}; }} return s; }}
function refresh() {{ const s = state(); let n = 0;
  for (const i of ids) {{ document.getElementById("i" + i).classList.toggle("done", !!s[i].verdict); if (s[i].verdict) n++; }}
  document.getElementById("count").textContent = `${{n}} of ${{ids.length}} judged`;
  try {{ localStorage.setItem(KEY, JSON.stringify(s)); }} catch (e) {{}} }}
try {{ const s = JSON.parse(localStorage.getItem(KEY) || "{{}}");
  for (const i in s) {{ if (s[i].verdict) {{ const r = document.querySelector(`input[name=v${{i}}][value=${{s[i].verdict}}]`); if (r) r.checked = true; }}
    document.querySelector(`input[name=n${{i}}]`).value = s[i].note || ""; }} }} catch (e) {{}}
document.addEventListener("input", refresh); refresh();
document.getElementById("save").onclick = () => {{
  const a = document.createElement("a");
  a.href = URL.createObjectURL(new Blob([JSON.stringify(state(), null, 1)], {{type: "application/json"}}));
  a.download = "verdicts.json"; a.click(); }};
</script></body></html>
'''


def score(folder: Path) -> str:
    sample = json.loads((folder / "sample.json").read_text(encoding="utf-8"))
    v = json.loads((folder / "verdicts.json").read_text(encoding="utf-8"))
    judged = [i for i in sample["items"] if v.get(str(i["id"]), {}).get("verdict")]
    count = {k: sum(1 for i in judged if v[str(i["id"])]["verdict"] == k) for k, _ in VERDICTS}
    n = len(judged) or 1
    out = [f"{len(judged)} of {len(sample['items'])} judged, from {sample['new_lines']} new lines",
           "  ".join(f"{k} {c}" for k, c in count.items()),
           f"precision: {count['exact'] / n:.0%} exact, {(count['exact'] + count['minor']) / n:.0%} exact or minor"]
    for i in judged:
        x = v[str(i["id"])]
        if x["verdict"] != "exact": out.append(f"  {i['id']:02} {x['verdict']:5} {i['text']}" + (f"  -> {x['note']}" if x["note"] else ""))
    return "\n".join(out)


def upload(folder: Path, name: str, url: str = URL, replace: bool = False) -> dict:
    """Send a sample folder to the review stack as one zip; basic auth from OC_REVIEW_USER and OC_REVIEW_PASSWORD."""
    user, pwd = config.get("OC_REVIEW_USER"), config.get("OC_REVIEW_PASSWORD")
    if not user or not pwd: raise SystemExit("set OC_REVIEW_USER and OC_REVIEW_PASSWORD (the basic-auth login of the review page)")
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_STORED) as z:        # PNG files are compressed already
        for f in ["sample.json", "verdicts.json"] + [f"crops/{p.name}" for p in sorted((folder / "crops").glob("*.png"))]:
            if (folder / f).is_file(): z.write(folder / f, f)
    req = urllib.request.Request(url.rstrip("/") + f"/api/samples/{name}" + ("?replace=true" if replace else ""),
                                 data=buf.getvalue(), method="POST", headers={"Content-Type": "application/zip",
                                 "Authorization": "Basic " + base64.b64encode(f"{user}:{pwd}".encode()).decode()})
    try:
        with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"upload refused ({e.code}): {e.read().decode(errors='replace')[:300]}")
