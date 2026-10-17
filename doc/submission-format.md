# Submission format

Draft 1, 2026-10-17. Format version `0.1.0`. Status: proposal, to be validated with the data model (`doc/data-model.md`, draft 3) before the pilot.

A submission is one run of the client on one copy of a work. It travels from the client to the master as one zip (see `doc/technology-choices.md`, section 6):

```
submission-<uuid>.zip
├── submission.json        layers 0 to 3 of the data model
├── frames/<uuid>.webp     evidence frames (optional, charter decision 3)
└── native/                the OCR engine's own output (optional)
```

| File | Role |
|---|---|
| [`schema/submission.schema.json`](../schema/submission.schema.json) | the JSON Schema (draft 2020-12) of `submission.json` |
| [`schema/check_submission.py`](../schema/check_submission.py) | the checker: the schema, then what a schema cannot express |
| [`schema/examples/submission.example.json`](../schema/examples/submission.example.json) | a minimal valid submission (illustrative values) |

```bash
uv run schema/check_submission.py submission.json      # or a bundle: submission-<uuid>.zip
```

The client runs the checker before sending; the importer runs it again on arrival and rejects a failing bundle whole.

## Shape

`submission.json` follows the layers, nested by containment:

```
format_version
submission      id, created_at, client, ocr engine and parameters, vocabulary_version, licence (always CC0-1.0)
work            kind, TMDb / IMDb / Wikidata ids, title, year
copy            fingerprint, duration, resolution, edition_hint, version_language, source
  parts[]       part_index, opensubtitles_hash, file_size, duration_ms, offset_ms
segments[]      part_index, kind, start/end, detected_by, layout, scroll speed
  frames[]      timecode, phash, page offset, evidence file and crop
    text_boxes[]  layer 2a: box, text, confidence, typography
  text_lines[]  layer 2b: position on the virtual page, voted text, readings, frame_ids, first/last time
  blocks[]      layer 3a: heading, block_type, unit, vendor, line_ids
    credits[]   layer 3b: name_raw, role_raw, role_code, role_modifiers, character, line_ids, entity_ref
entities[]      layer 3c: the persons, companies, places and songs the credits point to
```

## Rules the format enforces

- **Data only, closed objects.** Every object forbids unknown fields, so a file path, a file name or any field outside the format is rejected by the schema, not by good intentions. There is no SQL anywhere.
- **No contributor identity.** The master takes it from the authenticated account that uploads the bundle; a bundle cannot claim to come from someone else.
- **Client UUIDs (version 7) for what belongs to the submission**: the submission, segments, frames, text lines, blocks, credits, proposed entities. The master keeps them as primary keys; version 7 makes collisions a non-issue.
- **No ids for shared rows.** The copy is identified by its `fingerprint`, a part by its `opensubtitles_hash` and size, a work by its external ids, an entity by its external ids when it has them. The client cannot know the master's ids for these, and does not need to.
- **No edition.** The client sends `edition_hint`; grouping copies into editions is done by the master and the community.
- **Times are in milliseconds within the part** (`segment.part_index` says which part); the part's `offset_ms` gives the time in the copy.
- **Raw wording always travels with the interpretation**: `name_raw` beside `entity_ref`, `role_raw` beside `role_code` and `role_modifiers`. The interpretation can be redone; the wording is the evidence.

## What the checker adds to the schema

JSON Schema cannot follow references, so `check_submission.py` checks:

- ids are unique across the bundle;
- `frame_ids` of a text line belong to its segment, `line_ids` of a block to its segment, `line_ids` of a credit to its block;
- `entity_ref`, `vendor_entity_ref`, `role_target_entity_ref` and `song_ref` point to an entity of the right kind;
- parts are numbered 1, 2, 3 without gaps, each `offset_ms` is the sum of the previous durations, and the copy `fingerprint` is the SHA-256 of the lines `<opensubtitles_hash>:<file_size>` in part order;
- segments lie inside their part, frames inside their segment, `agreeing <= readings`, `first_ms <= last_ms`;
- in a zip, every evidence file named in `submission.json` is present, and named `frames/<frame id>.webp`.

## Open points

1. **Characters.** The format carries `character_raw` only. The character entity (Wikidata P453) is resolved on the master, like an unresolved name. Should the client propose a character entity too?
2. **Entity candidates.** A credit carries at most one proposed entity. The disambiguation queue (charter, decision 17) may want the client's ranked candidates with scores; that would be a `candidates` list on the credit.
3. **The role vocabulary on the client.** `role_code` and `role_modifiers` need the vocabulary on the contributor's machine. It would be published by the master as a versioned file; `vocabulary_version` records which one was used.
4. **Size.** A rolling sequence of a few minutes gives a few hundred frames and some thousands of text boxes: a few megabytes of JSON, well under one compressed. To measure in the pilot; text boxes could become optional if they weigh too much, since text lines are the pivot.
5. **The `native/` folder** has no format of its own: it is kept for reprocessing, never imported.
