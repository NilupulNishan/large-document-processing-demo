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

Chunks now sit in the size band the retrieval literature identifies as best. Both manuals are
ingested: 1,314 fragments at a median of 68 tokens become 475 windows at a median of 337.

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
uv run --project backend python scripts/ingest.py data/manuals/baic-bj30-e30-owner-manual-en.pdf
uv run --project backend python scripts/ingest.py data/manuals/baic-x55-ii-owner-manual-en.pdf
```

### Observed

Both manuals, measured from the written JSONL rather than in flight. The token counts the ingest
prints are taken before normalisation; these are after it, so they are the sizes that get embedded.

| | BJ30 | X55 |
| --- | ---: | ---: |
| pages | 283 | 263 |
| parse | 10.5 min (2.22 s/page) | 10.7 min (2.43 s/page) |
| chunks before / after merge | 730 → 213 | 584 → 262 |
| median tokens | 384 | 314 |
| p25 / p75 | 308 / 420 | 238 / 351 |
| p95 | 553 | 643 |
| under 100 tokens | 2% | 4% |
| within 200–512 tokens | 85% | 76% |
| headings present | 213/213 | 261/262 |
| printed page numbers | 213/213 | none — no offset detected |

X55 sits a little lower and wider than BJ30 on every measure. It has no running header, so
`detect_page_offset` returned `None` rather than guessing — the behaviour D6 was written for, now
confirmed on a manual that lacks the feature entirely.

Three chunks exceed the three-page cap: BJ30's maintenance schedule (p216–219) and technical
parameters table (p277–280), and X55's table of contents (p5–11, 3,042 tokens). All three are single
Docling chunks that were already oversized. Merging only joins, never splits, so they pass through
untouched. At p95 = 553 and 643 they are rare enough to leave alone until the eval harness says
otherwise.

### Two design points

**Page span is capped at three.** This is the same constraint as the client brief's "a citation may
span two or three pages", so the merge window and the citation window are the same thing by
construction rather than by coincidence.

**Heading selection uses document frequency, not a word list.** Merged chunks keep every heading
encountered, ordered by how often each appears across the document, least frequent first. `Attention`
occurs on 121 of 730 chunks and locates nothing, so it sinks below a real section name automatically.
Hardcoding a list of callout words would have worked on this manual and broken on the next one, which
the document-agnostic rule in `AGENTS.md` forbids.

### Known issues

**Matrix tables serialise badly.** 18 of BJ30's 730 pre-merge chunks (2.5%) contain mangled table
text — the maintenance-schedule checkmark matrix comes out as `, Primary Maintenance = . ,`
fragments. Technical Parameters chunks read cleanly, so this is specific to matrix-style tables
rather than tables in general.

**X55's table of contents is one 3,042-token chunk.** It lists every section name in the manual, so
it is lexically close to a great many queries while answering none of them. If it starts winning
retrieval slots, the fix is to drop front-matter at ingest, not to special-case the text.

Both are left alone until the eval harness shows those pages retrieving badly.

### Checkpoint

- [x] Merge step written and wired into `ingest.py`.
- [x] Median chunk size inside the target band.
- [x] Page span capped to match the citation requirement.
- [x] Corpus re-ingested with merging applied.
- [x] Second manual ingested — 475 chunks across 546 pages.

---

## Slice 3 — embed the corpus and make it searchable

### Outcome

Both manuals are in a LanceDB table with dense vectors and a full-text index, searchable by hybrid
query fused with RRF. This is the first slice that calls Azure and the first that can be judged on
retrieval quality rather than on counts.

### Why

Nothing could search the corpus. Everything downstream — the gate, the eval harness, the answer step
— reads retrieval output, so this is the gate on all of it.

Indexing is a **separate script** from ingestion. Parsing costs ~10 minutes per manual; embedding
costs ~60 seconds. Keeping JSONL as the boundary means changing what gets embedded never costs
another parse — which matters directly, because Slice 5 changes exactly that.

### Commands

```bash
uv add --project backend openai lancedb python-dotenv

uv run --project backend python scripts/index.py data/chunks/baic-bj30-e30-owner-manual-en.jsonl
uv run --project backend python scripts/index.py data/chunks/baic-x55-ii-owner-manual-en.jsonl
uv run --project backend python playground/check_search.py
```

### Observed

| | BJ30 | X55 |
| --- | ---: | ---: |
| chunks | 213 | 262 |
| tokens embedded | 84,689 | 92,104 |
| embed time | 63.7 s | 64.5 s |

475 rows total, so indexing the second manual replaced only its own rows and left the first intact.
176,793 tokens at `text-embedding-3-large` is about **$0.023** — matching D15's estimate.

Retrieval was checked against five hand-written queries per manual. Clear hits:

| Query | Result |
| --- | --- |
| pair a phone over bluetooth (BJ30) | p89–90, *"To pair a mobile phone, follow these steps"* |
| engine oil specification (BJ30) | p276, *"Oil = SP/C5 0W-20 … Filling Amount = 4.7"* |
| engine oil specification (X55) | p263, *"Specification = SP/C50 W/20"* |
| change a flat tyre (X55) | p230–231, *"Accidental flat tire handling"* |

Printed page numbers are shown for BJ30 and PDF indices for X55, correctly reflecting that only one
of the two has a detected offset. No query returned a row from the other manual.

### Two misses, both the same cause

`what does the yellow engine warning light mean` returns turn-signal and particulate-filter passages
on BJ30, under the heading `Attention`. `how do I pair a phone over bluetooth` on X55 returns
navigation, USB and coolant-gauge passages.

Both are chunks whose heading locates nothing — the problem D4 records and the contextual sentence in
Slice 5 exists to fix. They are left as-is deliberately: this index is the **baseline** that Slice 4
measures and Slice 5 must beat. Fixing them now would leave nothing to compare against.

Worth noting the heading paths seen here (`Tire Exchange > Replacement`) are produced by the Slice 2
merge joining several headings by document frequency, not by a Docling hierarchy. Docling's own
headings remain single-level, as Slice 0 found.

### Checkpoint

- [x] `openai`, `lancedb` and `python-dotenv` declared.
- [x] `config.py` reads `backend/.env`; no module raises at import without it.
- [x] Azure embeddings return 3,072 dimensions, matching `EMBEDDING_DIMENSIONS`.
- [x] Both manuals indexed; re-indexing one leaves the other intact.
- [x] Hybrid search returns correct pages for spec-table and procedure queries.
- [x] Search scoped to one manual never returns another's rows.
- [ ] Recall@10 measured against labelled questions — Slice 4.
