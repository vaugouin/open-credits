# open-credits technology choices

Status: 2026-10-16, candidates compared before the pilot (backlog ticket OPEN-CREDITS-003); updated 2026-10-17. Three choices are made by Philippe: **SQLite** on the client, **MariaDB** for the master (`T_WC_OC_*` tables in the T2S database), and **JSON bundles** for submissions. The others are recommendations, to be settled by the pilot's measures (charter, decision 27: recall on known credits, ratio of lines found, precision on a sample, CPU time per film).

Versions and licences were checked on the web on 2026-10-16. Speed and accuracy figures are the projects' own unless stated otherwise; the pilot measures them on real credits.

## What credits change in the choice

Most credits are easy text: high contrast, horizontal, a plain typeface. Accuracy is rarely the issue; the exceptions are graphic titles (Saul Bass), small text on DVD-resolution copies (720 × 576) and non-Latin scripts. What weighs most is **CPU time per film**: a rolling sequence of several minutes yields hundreds of frames. The data model already reduces it (lines rebuilt on one virtual page can be recognised a few times instead of once per frame), so text detection may cost more than recognition.

---

## 1. OCR engine (classical, on the CPU)

| Candidate | Licence | Pros | Cons |
|---|---|---|---|
| **PaddleOCR 3.7** (PP-OCRv5, PP-OCRv6 since June 2026) | Apache 2.0 | The most accurate free engine in 2026 comparisons. PP-OCRv6 comes in three sizes (tiny 1.5M, small 7.7M, medium 34.5M parameters), with a 5.2× CPU speed-up announced with OpenVINO. Many languages | The full PaddlePaddle framework is heavy to install. Figures are self-reported. On CPU the mobile v5 model is slower than v4 (about 1.75 s against 1.37 s per document image, larger dictionary) |
| **RapidOCR** (PaddleOCR models on ONNX Runtime) | Apache 2.0 | The same models without the framework: a light install, ONNX Runtime or OpenVINO backends, ports in C#, C++ and Rust | A small community project. Its current Python version and PP-OCRv6 support are not confirmed |
| **Tesseract 5.5** | Apache 2.0 | Mature, fast on CPU, available everywhere, very good on clean printed text, more than 100 languages | Weak on text over images and on stylised typefaces; its own text detection is poor on video frames, so detection should be done separately |
| **EasyOCR** | Apache 2.0 | The quickest prototype, about 80 languages | Depends on PyTorch, slow on CPU, lower accuracy; 2026 comparisons advise against it |
| **docTR / OnnxTR** | Apache 2.0 | Good detection and recognition in one pipeline; OnnxTR runs it without PyTorch | Built for documents, fewer languages; little recent information on OnnxTR |
| **Surya / Surya OCR 2** | GPL code (1.x) or Apache code (2), restricted weights | Strong multilingual and layout recognition | Weights free only under a revenue threshold ($2M or $5M): incompatible with an MIT and CC0 project that anyone can host. Built for GPUs |
| **ocrs / oar-ocr** (Rust) | MIT or Apache, Apache | A single native executable, nothing to install | ocrs calls itself an early preview with more errors; oar-ocr is young (0.2) but uses the PaddleOCR models |
| **Windows OCR** (Windows.Media.Ocr) | free, tied to Windows | Built into Windows, fast, nothing to install | Windows only and closed, against an open project anyone can host; few settings |
| **Apple Vision** | free, tied to macOS | Very good, fast on Apple chips | macOS only and closed |

**Recommendation:** RapidOCR with the PP-OCRv5 or v6 models as the main engine, Tesseract run on the same frames as the baseline; the pilot's measures decide. Surya is left out for its licence, the OS engines for tying the client to one platform.

## 2. Fallback for hard cases (vision models, charter decision 5)

| Candidate | Licence | Pros | Cons |
|---|---|---|---|
| **PaddleOCR-VL 1.6** (0.9B parameters) | Apache 2.0 | Small enough to run locally; supported by llama.cpp since February 2026 | CPU speed not measured; the official documentation assumes a GPU |
| **Small Qwen-VL models, Florence-2** | open, varies by model | Read text inside images (Saul Bass) | Slow on CPU; can invent text |
| **Cloud APIs** (Claude, GPT, Gemini) | paid | The best results on graphic credits | Token costs, which the charter rules out, and the frames leave the contributor's machine |

**Recommendation:** off in the pilot until the measures show how many cases need it.

## 3. Programming language

| Candidate | Pros | Cons |
|---|---|---|
| **Python** | Every OCR engine above has a Python binding; ffmpeg, PyAV, OpenCV and SQLite are at hand; Philippe's main language and that of `sqlite-plex-to-tmdb`; the largest pool of volunteer developers. The heavy work runs in compiled libraries, so Python's own speed matters little | Distribution to volunteers needs an installer (PyInstaller, Nuitka), heavy once the models are included (hundreds of MB), sometimes flagged by antivirus software |
| **Rust** | A single executable with nothing to install; fast and memory-safe; ONNX Runtime and ffmpeg bindings exist | Fewer OCR choices (ocrs, oar-ocr); slower to write; fewer volunteers; a new language for Philippe |
| **C# / .NET** | Self-contained Windows installers; RapidOCR ports (RapidOcrNet mentions PP-OCRv6); Windows OCR reachable directly | Less natural on Linux and macOS; fewer frame-analysis libraries; absent from the ecosystem |
| **Go** | Single executables, simple deployment | OCR only through C bindings or ONNX; little computer-vision code |
| **C++** | The fastest; native language of Tesseract, OpenCV and ffmpeg | Slow to write, hard to package on every platform, fewer volunteers |
| **TypeScript** (Electron or Tauri) | A rich cross-platform interface | OCR and video through native modules or a Python helper: two languages to maintain |

The review views are static HTML generated from SQLite and opened in a browser, so they do not weigh on the choice.

**Recommendation:** Python for the pilot and the first client. If installation becomes the main obstacle for volunteers, rewrite only the hot path in Rust (oar-ocr with the same models), which keeps results comparable.

## 4. Databases: SQLite on the client, MariaDB for the master (chosen)

### Client: SQLite

Chosen by Philippe for the client (charter, decision 23): small, fast and portable. It holds the client's working data (frames, text boxes, votes, parsed credits) and feeds the review views.

| Pros | Cons |
|---|---|
| One file, no server: nothing for a volunteer to install or administer | **One writer at a time.** WAL mode lets readers work while one process writes, and a second writer waits instead of failing; enough for one client. Several workers on one machine can each write their own file, merged afterwards |
| Portable across Windows, macOS and Linux, byte for byte: a contributor's whole working state is one file to back up or move | **No accounts or permissions** in the database; harmless on a single-user client |
| In Python's standard library; mature, heavily tested, used by Plex itself | **Unsafe on network shares** (SMB, NFS): file locking is unreliable, so the database must sit on a local disk, never on the NAS beside the videos |
| Fast for reads and for bulk inserts in one transaction; JSON functions; FTS5 full-text search for names and wordings | **Loose typing** by default: use `STRICT` tables so a text cannot land in an integer column |
| Easy to inspect (DB Browser for SQLite, the `sqlite3` shell) and to diff between versions | **No native UUID type**: store UUIDs as 16-byte `BLOB` (compact) or 36-character `TEXT` (readable); one choice for the whole schema |
| Never sent as such: the client exports a JSON bundle per submission (section 6), so its schema can change without breaking the master | `ALTER TABLE` is limited: some schema changes mean rebuilding a table, so migrations need a small versioned script (`PRAGMA user_version`) |

### Master: `T_WC_OC_*` tables in the T2S MariaDB

Decided by Philippe on 2026-10-17, revising charter decision 30 ("open-credits is the master; the T2S database holds a copy"): the master (decision 29, on the VPS) lives in the MariaDB database of the T2S stack, in `T_WC_OC_*` tables following the ecosystem's conventions. The reason: comparing the credits with TMDb and Wikidata (layer 4) becomes a plain join with the `T_WC_TMDB_*` and `T_WC_WIKIDATA_*` tables already there, instead of API calls or reference extracts.

| Pros | Cons |
|---|---|
| Already run, backed up and tuned on the VPS; no new server | Production data of the T2S stack and public writes share one server: the importer and the site need their own MariaDB account, with write rights on `T_WC_OC_*` only and read rights on the tables they join |
| Layer 4 is SQL: a consolidated credit is checked against TMDb and Wikidata credits by a join; the ROLE table is seeded from the TMDb jobs by an `INSERT ... SELECT` | "Anyone can host a copy" (decision 19) needs **export scripts** that dump the `T_WC_OC_*` tables only, never the rest of the T2S database |
| Many writers at once (row locks): the importer, moderators and website edits can write at the same time | The schema exists twice, lower-case names in the client's SQLite and `T_WC_OC_*` in MariaDB: one definition, mapped by the importer |
| Accounts, permissions, strict types, full `ALTER TABLE` | UUID storage must match on both sides: MariaDB's native `UUID` type (10.7 and later, stored in 16 bytes) or `BINARY(16)`, against a 16-byte `BLOB` in SQLite |

**Keeping open-credits separable.** The client and the bundle format know nothing of the T2S stack. Only the master's server code touches MariaDB, and only two parts of it read non-OC tables: the layer 4 comparisons and the ROLE seeding. Keeping those in one module, and the `T_WC_OC_*` tables free of foreign keys to other `T_WC_*` tables (TMDb and Wikidata IDs stored as plain values), means the OC tables can be exported, or moved to their own database later, without untangling them.

**Concurrency comes from a queue, not from the database.** The API only stores each uploaded bundle in an incoming folder, which any number of contributors can do at once. One import process validates each bundle and loads it into `T_WC_OC_*`, one bundle per transaction. A bad bundle is rejected whole and never half-loaded.

## 5. Other choices

| Component | Candidates | Pros and cons | Recommendation |
|---|---|---|---|
| **Frame decoding** | ffmpeg command line; PyAV (ffmpeg as a library); OpenCV `VideoCapture`; decord | The ffmpeg command line is the simplest and decodes everything, but only through files or pipes. PyAV gives frames in memory with exact timestamps and fast seeking. OpenCV is easy but seeks imprecisely in some containers. decord is fast but little maintained | PyAV, with the ffmpeg command line for `blackdetect` |
| **Finding the credits** | Plex credit markers; ffmpeg `blackdetect` and scene changes; a text detector on sampled frames | Plex markers are free when they exist (not on every title); black frames and scene changes are cheap but approximate; a text detector is reliable but costs CPU | All three in that order: markers, then black frames, then text detection to fix the boundaries |
| **Scroll speed** (rolling credits) | OpenCV phase correlation; optical flow; matching OCR line positions between frames | Phase correlation is fast and exact for a uniform scroll; optical flow is heavier; matching lines comes free once the OCR has run but depends on it | Phase correlation, checked against matched lines |
| **Duplicate frames** | perceptual hash (`imagehash`, OpenCV `img_hash`); pixel difference | A perceptual hash survives compression noise and also matches frames between copies; a pixel difference is cheaper but brittle | Perceptual hash (already in the data model, `phash`) |
| **Evidence frames** | WebP; AVIF; JPEG; PNG | WebP is small, decoded by every browser and by Pillow; AVIF is smaller still but slower to encode; JPEG blurs small text; PNG is lossless but large | WebP, cropped to the line |
| **Name matching** (entities, roles) | RapidFuzz; `thefuzz`; full-text search (FTS5) | RapidFuzz is fast (C++), MIT, already used in the ecosystem; `thefuzz` is slower; FTS5 finds candidates, RapidFuzz scores them | FTS5 for candidates, RapidFuzz for scores |
| **Review views** | static HTML from templates (Jinja2); a local web server (FastAPI, Flask); a desktop interface (Qt, Tauri) | Static HTML needs nothing running and can be zipped and shared; a local server allows editing in place; a desktop interface is the heaviest to build | Static HTML in the pilot; editing moves to the master site |
| **Submission format** (client to master) | JSON in a zip; the SQLite file of one submission; Parquet | JSON is plain data, checked against a schema before anything touches the master, readable by a volunteer, and independent of the client's tables; a SQLite file reuses the client's schema but is a database written by a stranger, which the master would have to open defensively; Parquet is compact but opaque to volunteers | **Chosen (2026-10-17):** a JSON bundle per submission, section 6 |
| **Master API and site** | FastAPI (Python); Django; PHP as in `tmdb-front` | FastAPI is already run in the ecosystem (`fastapi-text2sql`) and shares the client's language; Django brings accounts and an admin out of the box but more weight; PHP fits `tmdb-front` but splits the code base | FastAPI, with Django kept in mind if accounts and moderation screens grow |
| **UUIDs** | UUID version 7 (standard library since Python 3.14, or the `uuid6` package); version 4 | Version 7 is time-ordered, so inserts stay grouped in the index; version 4 is random and fragments indexes | Version 7 (data model, Identifiers) |
| **Client packaging** | PyInstaller; Nuitka; Briefcase; `uv tool install` | PyInstaller is the most used, but its executables are large and sometimes flagged by antivirus; Nuitka compiles to C, smaller and faster but slower to build; Briefcase makes native installers; `uv tool install` is light but assumes a technical volunteer | `uv tool install` for the pilot and early volunteers, an installer later |

## 6. Submission bundle (chosen)

One submission (one run of the client on one copy) travels as one zip:

```
submission-<uuid>.zip
├── submission.json        the submission, its copy and parts, segments, text lines, credits
├── frames/<uuid>.webp     evidence frames, cropped to the line (optional, decision 3)
└── native/                the OCR engine's own output (optional, for reprocessing)
```

- `submission.json` carries a `format_version`. A **JSON Schema** published in this repository defines it; the client checks its own bundle before sending, the importer checks it again on arrival.
- It contains data only: the logical names of the data model, UUIDs as text, times in milliseconds. Never a file path (private) nor any SQL.
- Size: a film yields a few hundred credits and some thousands of text lines, well under a megabyte compressed. Frames are the bulk.
- The same importer serves the pilot: the pilot's client writes bundles and the importer loads them into `T_WC_OC_*`, so the path to the master is tested from the first title.

## Sources

- [PaddleOCR on PyPI](https://pypi.org/project/PaddleOCR/) (3.7.0, PP-OCRv6, Apache 2.0)
- [PP-OCRv5 benchmarks](https://www.paddleocr.ai/latest/version3.x/algorithm/PP-OCRv5/PP-OCRv5.html)
- [PaddleOCR-VL](https://paddlepaddle.github.io/PaddleX/3.5/en/pipeline_usage/tutorials/ocr_pipelines/PaddleOCR-VL.html), [PaddleOCR-VL with llama.cpp](https://insiderllm.com/guides/paddleocr-vl-local-document-ocr/)
- [Codesota, Python OCR libraries in 2026](https://codesota.com/ocr/best-for-python)
- [Tesseract (Wikipedia)](https://en.wikipedia.org/wiki/Tesseract_(software))
- [RapidOCR](https://www.linuxlinks.com/rapidocr-ocr-toolkit/), [RapidOcrNet](https://feed.nuget.org/packages/RapidOcrNet/)
- [Surya OCR](https://depscope.dev/pkg/pypi/surya-ocr), [Surya OCR 2](https://llmrun.dev/model/datalab-to-surya-ocr-2)
- [ocrs](https://docs.rs/crate/ocrs/0.2.1), [oar-ocr](https://docs.rs/crate/oar-ocr/0.2.1)
