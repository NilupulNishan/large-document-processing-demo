# Build log

One entry per working slice: the outcome, why it exists, the exact commands, the observable result,
and a checkpoint. Written in the same commit as the slice it describes.

---

## Slice 0 — Docling spike: parse speed and chunk metadata

### Outcome

Docling parses this corpus at an acceptable speed on CPU, extracts tables as clean markdown, and
attaches headings and page numbers to every chunk. Two ingestion problems were found that were not
visible from the plan.

### Why

Parse speed on a CPU-only i7-1355U was the only unmeasured number in the architecture, and the
chunk metadata shape decides whether D4 and the citation requirement are buildable as designed. Both
had to be settled before `ingest.py` was written rather than after.

### Commands

```bash
cd backend && uv sync --python 3.12 && cd ..

# prose-heavy range
uv run --project backend python playground/spike_docling.py 130 149

# table-heavy range (Technical Parameters)
uv run --project backend python playground/spike_docling.py 268 281
```

`HF_HUB_DISABLE_SYMLINKS_WARNING=1` and `TORCHDYNAMO_DISABLE=1` suppress two pages of harmless
warnings. Neither changes the result.

### Observed

| | Prose, p130–149 | Tables, p268–281 |
| --- | ---: | ---: |
| Per page | 1.70 s | 4.06 s |
| Chunks | 69 from 20 pages | 15 from 14 pages |
| Chunks with headings | 69/69 | 15/15 |
| Chunks with page numbers | 69/69 | 15/15 |
| Chunks spanning >1 page | 2/69 | 1/15 |
| Tables detected | 0 | 9 |

Blended across 546 pages: **roughly 15–20 minutes** for a full corpus ingest. Table-dense pages cost
about 2.4x a prose page, so the figure depends on the mix, not on a single rate.

Extrapolated chunk count for the corpus is **~1,600**, which is also the number of `gpt-4o-mini` calls
the contextual-retrieval pass in D4 will make.

Tables extract as correctly aligned markdown with headers intact:

```
| Name                      | Meaning                                          |
|---------------------------|--------------------------------------------------|
| High voltage danger signs | Do not touch high-voltage compo- nents, ...      |
```

This is the capability the previous build lacked entirely — it used raw PyMuPDF text extraction,
which flattens tables into unusable prose.

### Two problems found

**1. Headings are single-level, not a path.** Every chunk has one, but the observed values are
`['Driving and Operation']`, `['Technical Parameters']`, `['Vehicle nameplate']` and `['Attention']`.
Docling never produced a hierarchy such as `Technical Parameters > Vehicle nameplate > VIN`.
`Driving and Operation` spans 86 of 283 pages, so it barely narrows a search, and `Attention` is a
callout-box title that recurs throughout the manual and locates nothing. Recorded against D4.

**2. Text needs normalising before it is indexed.** Hyphenation survives line breaks and some spaces
are lost entirely:

| Extracted | Should be |
| --- | --- |
| `compo- nents` | `components` |
| `in-dicator` | `indicator` |
| `ensur-ing` | `ensuring` |
| `Bei-jing` | `Beijing` |
| `isdisplaved` | `is displayed` |
| `calculationthe` | `calculation, the` |

A keyword search for *components* will never match `compo- nents`, so this directly damages the BM25
half of the hybrid retrieval in D3. Ingestion needs a normalisation step before embedding.

Separately, the source manual contains its own typos — `identifcation`, `displaved`, `identifys` —
and some glyphs for warning-light icons extract as `͇`. Neither is fixable at ingest, and both
are an argument for keeping dense retrieval alongside BM25 rather than relying on exact matching.

### Checkpoint

- [x] `backend/.venv` builds from a locked `pyproject.toml`.
- [x] Docling parses without OCR; no `modelscope.cn` download is attempted.
- [x] Full-corpus parse time is known and acceptable.
- [x] Every chunk carries headings and page numbers.
- [x] Tables survive as markdown.
- [x] Text normalisation step written.
- [x] `ingest.py` written.

---

## Slice 2 — merge undersized chunks

### Outcome

Chunks now sit in the size band the retrieval literature identifies as best. The BJ30 manual goes
from 730 fragments at a median of 68 tokens to 208 windows at a median of 393.

### Why

Slice 1 produced chunks far too small to retrieve well: two thirds were under 100 tokens and the
smallest was 5. A 40-token fragment carries almost no context, and embedding it produces a vector
that matches little. Published benchmarks put recursive 512-token splitting first of seven
strategies, so the target is a few hundred tokens rather than a few dozen.

`HybridChunker` merges peers — siblings under one heading — and this manual is built from hundreds
of small callout boxes and list items with nothing to merge against. The fix has to run after it.

### Commands

```bash
# fast check against an already-ingested JSONL, no re-parse
uv run --project backend python playground/check_merge.py

# full re-ingest with merging in the pipeline
uv run --project backend python scripts/ingest.py data/manuals/<file>.pdf
```

### Observed

| | before | after |
| --- | ---: | ---: |
| chunks | 730 | 208 |
| median tokens | 68 | 393 |
| p25 / p75 | 40 / 125 | 320 / 432 |
| p95 | 338 | 543 |
| under 100 tokens | 67% | 1% |
| within 200–512 tokens | 12% | 86% |

`max` stays at 2838 tokens and one chunk still spans four pages. Merging only joins, never splits, so
a pre-existing oversized chunk passes through unchanged. At p95 = 543 these are rare enough to leave
alone until the eval harness says otherwise.

### Two design points

**Page span is capped at three.** This is the same constraint as the client brief's "a citation may
span two or three pages", so the merge window and the citation window are the same thing by
construction rather than by coincidence.

**Heading selection uses document frequency, not a word list.** Merged chunks keep every heading
encountered, ordered by how often each appears across the document, least frequent first. `Attention`
occurs on 121 of 730 chunks and locates nothing, so it sinks below a real section name automatically.
Hardcoding a list of callout words would have worked on this manual and broken on the next one, which
the document-agnostic rule in `AGENTS.md` forbids.

### Known issue

18 of 730 chunks (2.5%) contain mangled table text — the maintenance-schedule checkmark matrix
serialises as `, Primary Maintenance = . ,` fragments. Technical Parameters chunks read cleanly, so
this is specific to matrix-style tables rather than tables in general. Left alone until the eval
harness shows those pages retrieving badly.

### Checkpoint

- [x] Merge step written and wired into `ingest.py`.
- [x] Median chunk size inside the target band.
- [x] Page span capped to match the citation requirement.
- [ ] Corpus re-ingested with merging applied.
- [ ] Second manual ingested.
