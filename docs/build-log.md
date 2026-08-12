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
- [ ] Text normalisation step written.
- [ ] `ingest.py` written.
