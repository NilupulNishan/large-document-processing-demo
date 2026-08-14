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

### One miss, and one that turned out not to be

`what does the yellow engine warning light mean` returns turn-signal and particulate-filter passages
on BJ30, under the heading `Attention` — a chunk whose heading locates nothing. That is the problem
D4 records and the contextual sentence in Slice 5 exists to fix. It is left as-is deliberately: this
index is the **baseline** that Slice 4 measures and Slice 5 must beat.

`how do I pair a phone over bluetooth` returned navigation and coolant-gauge passages on X55, and was
first recorded here as a second miss. It is not. Grepping the source shows X55 has no pairing
procedure anywhere — only incidental mentions of a Bluetooth module in a fuse table and on the
instrument cluster. Retrieval returned weak matches because the content does not exist, which is the
correct behaviour and a `general` route rather than a `manual` one. Found while labelling Slice 4,
and a good argument for building the eval set from the source text rather than from what retrieval
happens to return.

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
- [x] Recall@10 measured against labelled questions — Slice 4.

---

## Slice 4 — labelled questions and the eval harness

### Outcome

44 labelled questions and `eval/run.py`. Baseline retrieval measured. The run also produced a finding
that changes the design: the gate cannot be built on fusion scores.

### Why

Every claim about retrieval quality so far has been an anecdote from five hand-typed queries. A
proposal needs a number, and Slice 5 needs a baseline to beat.

### How the labels were made

Pages were read out of the source JSONL — the topic map of every chunk's heading, pages and opening
words — and then confirmed with a lexical grep for a distinctive phrase. **Not** from what retrieval
returned. Labelling from search output would have produced 100% recall by construction.

That process immediately caught one error already recorded in Slice 3: the X55 bluetooth "miss" was
not a miss, because X55 has no pairing procedure. It is now `gen-01`, expecting the `general` route.

### Commands

```bash
uv run --project backend python eval/run.py
```

### Observed

```
Retrieval — 38 grounded questions

  overall              n= 38  @1  76% @3  95% @5  97% @10 100%   MRR 0.866

  baic-bj30-e30        n= 22  @1  68% @3  91% @5  95% @10 100%   MRR 0.814
  baic-x55-ii          n= 16  @1  88% @3 100% @5 100% @10 100%   MRR 0.938

  procedure            n= 22  @1  77% @3  95% @5  95% @10 100%   MRR 0.871
  safety               n=  5  @1 100% @3 100% @5 100% @10 100%   MRR 1.000
  spec                 n=  6  @1  33% @3  83% @5 100% @10 100%   MRR 0.625
  symptom              n=  5  @1 100% @3 100% @5 100% @10 100%   MRR 1.000
```

Recall@10 is saturated, so it will not show whether Slice 5 helps. **Recall@1 (76%) and MRR (0.866)
are the numbers to move.**

`spec` is the weakest category by a wide margin — 33% at rank 1 against 100% for symptom and safety.
These are exact-value lookups (oil capacity, vehicle dimensions, fuse ratings) which live in tables,
and the Slice 2 known issue about matrix tables serialising badly sits directly underneath that.

### The finding: RRF scores cannot calibrate the gate

The harness prints the top score for questions the manual should not answer, expecting a usable
threshold. There is none.

| Row | Score | Should route to |
| --- | ---: | --- |
| grounded questions | 0.0302 – 0.0328 | `manual` |
| `dec-02` write me a poem about the sea | 0.0323 | `decline` |
| `gen-01` pair my phone (absent from X55) | 0.0325 | `general` |
| `gen-02` nearest service centre | 0.0296 | `general` |
| `gen-03` open safety recalls | 0.0164 | `general` |

RRF scores rank position, not relevance: `1/(60+1) = 0.0164` is one list ranking a chunk first, and
`0.0328` is both doing so — which is exactly the observed ceiling. Something always ranks first, so a
poem request scores like a grounded question. Two of six ungrounded rows sit inside the grounded
range and no threshold separates them.

D2 and D3 are amended. The gate reads cross-encoder output only; fusion scores order candidates and
never decide a route. This makes the reranker a prerequisite for the gate rather than a later
refinement, and it is the same class of mistake as the previous project's — routing on a number that
does not mean what it appears to mean.

### Caveat on the numbers

The questions and their labels were written from the same reading of the corpus, so they share
vocabulary with it more than a real user's phrasing would. Colloquial rows were included
deliberately — *"I hear a squealing noise when I brake"*, *"I accidentally put diesel in"* — and
those scored at rank 1. Treat 100% Recall@10 as a floor established under favourable phrasing, not as
a claim about live traffic.

### Checkpoint

- [x] 44 labelled questions across both manuals, pages verified against source text.
- [x] `eval/run.py` reports Recall@1/3/5/10 and MRR, split by manual and question kind.
- [x] Baseline recorded for Slice 5 to beat.
- [x] Questions carry `expected_route` ready for routing accuracy once the gate exists.
- [ ] Routing accuracy — needs the gate and the cross-encoder.

---

## Slice 5 — cross-encoder reranking, and the gate bands

### Outcome

A local ONNX cross-encoder scores query and passage together. Its scores separate grounded questions
from ones the manual cannot answer — the thing RRF could not do — so the gate has a real input.
`GATE_HIGH = -4.44`, `GATE_LOW = -7.21`, with 8% of grounded questions in the ambiguous band.

### Why

Slice 4 proved fusion scores rank position rather than relevance, so D2's gate had no usable signal.
This is the prerequisite, not the refinement D3 presented it as.

### Commands

```bash
uv add --project backend onnxruntime "optimum[onnxruntime]" transformers
uv run --project backend python playground/check_rerank.py
```

### Observed

| | bge-reranker-base | MiniLM-L6, 30 cand. | MiniLM-L6, 12 cand. |
| --- | ---: | ---: | ---: |
| download | 1.1 GB | 91 MB | 91 MB |
| latency / question | 19,111 ms | 3,242 ms | **1,249 ms** |
| per passage | 637 ms | 108 ms | 104 ms |
| ambiguous band | ~10% | 5% | 8% |

`bge-reranker-base` was the first choice because D3 names it first. At 19 s per question it is
unusable — 63× the ~300 ms D3 claims, and that figure evidently describes the MiniLM option.
MiniLM is 8× less compute and, on this corpus, **separates better as well as running faster**.

Scores order the unanswerable questions sensibly, most vehicle-related first:

```
gen-03  -4.44  safety recalls        gen-04  -7.73  price
gen-02  -4.56  service centre        dec-02  -8.17  poem
gen-01  -5.52  bluetooth (absent)    dec-01 -10.12  weather
```

Compare Slice 4, where the poem scored 0.0323 against a grounded range of 0.0302–0.0328 — inside it.
Here it is 8th of 44, below every grounded question.

### Two corrections to record

**Threading did nothing.** `intra_op_num_threads = 12` was added on the theory that 3.2 s for a
6-layer model on a 12-core machine meant single-threaded execution. Per-passage cost was 108 ms
before and 104 ms after: ONNX Runtime was already using the cores. The setting is harmless and stays,
but it is not what made this faster.

**Cutting candidates 30 → 12 was not free.** The stated justification — Recall@10 is 100%, so the
answer is always in the top 10 — is wrong. That guarantees the expected *page* is in the top 10, not
that the highest-*scoring* passage is. `bj30-16` scored −3.01 over 30 candidates and −4.51 over 12,
moving into the ambiguous band. The trade is 2.6× speed for one extra grader call in 38, which is
worth taking, but it is a trade.

**ONNX export is now persisted** to `data/models/`. Optimum re-converted from PyTorch on every start
because `export=True` ignored the ONNX weights already on the Hub. Cold start: 60.6 s → 6.4 s.

### The ambiguous band is a table problem, not a reranker problem

```
bj30-02  -7.21  spec    What engine oil does it take and how many litres?
x55-10   -5.41  safety  I accidentally put diesel in. What now?
bj30-16  -4.51  spec    How often should the car be serviced?
```

`bj30-02` sets `GATE_LOW` on its own. Its answer, on p276, reads:

```
Oil, = SP/C5 0W-20. Oil, = L. Oil, Filling Amount = 4.7.
```

That is the mangled matrix table recorded as a known issue in Slice 2, and `bj30-16`'s answer is the
maintenance-schedule matrix from the same issue. Both `spec` rows — the category Slice 4 measured
worst at 33%@1. Fixing table serialisation would raise `GATE_LOW` and narrow the band without
touching the reranker. Left open, now with evidence of what it costs.

### Rejected: deriving the safety carve-out from the corpus

D13 originally named brakes, airbags, restraints, towing and jacking — a hardcoded English automotive
list, against the document-agnostic rule. The replacement idea was to let each manual mark its own
hazards, since both use *Danger*, *Warning*, *Caution* and *Attention*.

Headings looked promising on one manual and collapsed on the other. BJ30 carries `Attention` on 91 of
213 chunks, `Warning` on 24, `Danger` on 22. X55 has almost none as headings — `Note:` 2, `Notice` 1,
`Tip` 1. Docling extracts heading structure differently per publisher, so heading-based detection
would have worked on the manual it was built against and silently failed on the next one.

Body text is consistent — BJ30 70/213 chunks (33%), X55 75/262 (29%) — so the second attempt scanned
text instead, discounting `warning lamp` and similar instrument names. Measured against the labelled
set, marker density in the top six passages:

| kind | mean density |
| --- | ---: |
| offtopic | **42%** |
| procedure | 24% |
| safety | **23%** |
| absent | 21% |
| symptom | 20% |
| spec | 17% |

`safety` is indistinguishable from `procedure`, and *"write me a poem about the sea"* scores highest.
That is the corpus base rate showing through: with ~30% of chunks containing hazard language, random
passages land near 30–40%, so the metric measures how random the retrieval was rather than how
dangerous the topic is.

The carve-out moved to `SAFETY_TOPICS` in `backend/.env`. It is corpus knowledge, so it belongs in
configuration next to `DOMAIN_DESCRIPTION`, not in code and not in a decision document.

### Remaining latency lever

1,249 ms sits before the first token, which is the worst place for it (D9). Untried: INT8 dynamic
quantisation, normally 2–4× on CPU for small accuracy loss, and cutting `RERANK_MAX_TOKENS` from 512
to 256. Either would bring this under 500 ms. Not done yet — the demo needs the gate and the answer
step more than it needs 800 ms.

Azure alternative if local proves too slow: Cohere Rerank v3.5 on AI Foundry serverless, ~$1 per
1,000 searches, ~100–300 ms. Azure AI Search's semantic ranker was rejected — it needs a Basic-tier
service at ~$73/month and would replace LanceDB, against D5.

### Checkpoint

- [x] Cross-encoder provider written, ONNX on CPU, export persisted.
- [x] Scores separate grounded from unanswerable questions.
- [x] `GATE_HIGH` and `GATE_LOW` derived from the eval set, not guessed.
- [x] Latency measured and reduced 19,111 → 1,249 ms.
- [x] Reranking wired into `eval/run.py` and measured against the fusion baseline.
- [ ] Latency under 500 ms.

### What reranking is worth

`eval/run.py` now scores fusion order against reranked order over the same 12 candidates, so the
reranker's contribution is isolated rather than confounded with retrieval.

| | Recall@1 | @3 | @10 | MRR |
| --- | ---: | ---: | ---: | ---: |
| fusion only | 76% | 95% | 100% | 0.862 |
| + cross-encoder | **87%** | 97% | 100% | **0.919** |

+11pp Recall@1, close to the +12.1pp Recall@5 D3 cites. Six questions moved up, three down; the worst
regression was `bj30-20` (tailgate emergency release) falling from rank 6 to 10.

`spec` went from **33% to 100%** at rank 1 — the category Slice 4 measured worst. Note the tension
this exposes: `bj30-02` is a `spec` question that now ranks *first* among its candidates while still
scoring −7.21 in absolute terms. Ranking quality and absolute confidence are different signals, and
the design uses each for the right job — order for the answer's top 6, absolute score for the gate.

### Gate bands need margin, not the observed extremes

Set to the exact observed values (`HIGH -4.44`, `LOW -7.21`), `eval/run.py` reported 2 grounded
questions in the ambiguous band where `check_rerank.py` reported 3. The missing one was `bj30-02`,
whose true score is fractionally below the rounded −7.21 — so it fell *under* `GATE_LOW` and would
have been confidently declined despite being answerable from the manual.

Bands moved to `HIGH -4.1`, `LOW -7.5`. No unanswerable question is now routed confidently to the
manual; all six are `grader` or `LOW`. Widening costs a grader call, narrowing misroutes, so the
asymmetry decides the direction.

---

## Slice 6 — the pipeline: retrieve, rerank, gate, answer

### Outcome

`backend/app/pipeline/` — four steps assembled by `build_pipeline()`, answering real questions end to
end with page citations. Four of the five routes work; `escalate` returns no answer yet, and
`resolve_query` and `web_search` are not built.

### Why

Everything before this was measured in isolation: retrieval by Recall@1, reranking by MRR, the gate by
where scores fell against two thresholds. None of it had produced an answer a person could read. This
is the slice where the parts become a product.

### Shape

Plain classes with one `run(ctx)` method, assembled by a `build_pipeline()` function, following the
reference project. `PipelineContext` carries state forward; each step adds to it and returns it.

Two rules are enforced in Python rather than asked of the model:

- **`source` is set from the route**, never by the model. A wrong source label is the worst output
  this system can produce (D13).
- **The model cites by passage index; Python maps those indices back to real pages** and drops
  anything out of range. A hallucinated page number is therefore not expressible.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
uv run --project backend --locked --no-sync python playground/check_pipeline.py
```

### Observed

Seven questions, exit 0. Four routed `manual` with page citations, two `general` with none, one
`decline`:

| Question | Score | Route | Cited |
|---|---:|---|---|
| Bluetooth pairing (BJ30) | +9.29 | `manual` | p89 |
| Engine oil type and capacity | −7.21 | `manual` via grader | p276 |
| Airbag warning light | +4.68 | `manual` | p120, p74 |
| Diesel misfuelling (X55) | −5.41 | `manual` via grader | p174 |
| Bluetooth pairing (X55) | −5.52 | `general` | — |
| Nearest service centre | −4.56 | `general` | — |
| Weather forecast | −10.12 | `decline` | — |

`bj30-02` is the case Slice 5 widened the bands for: at −7.21 it sits below `GATE_HIGH`, the grader
confirms the manual covers it, and it routes to `manual` rather than being declined. The mechanism
works on the question it was designed for.

The X55 diesel answer cites `p174 (pdf)` rather than a printed number — X55 has no detected page
offset, so `pages_printed` is empty and the citation falls back to the PDF index (D6). Correct, and
the first time that path has run outside a test.

### Two prompt defects the run exposed

**The model narrated its own instructions.** Asked to "open with the fact that this is not from their
manual", it wrote *"This guidance is not from your vehicle's owner manual (since you said it doesn't
cover it)"*. The grounded prompt produced *"Part not fully settled by the manual: …"*. Both read as a
system prompt leaking through. Fixed by telling it to write as the expert and never mention passages,
numbering or the instructions.

**Then the fix over-corrected.** "Open with a single sentence saying this is not covered" was read as
"the answer is a single sentence", and both `general` answers collapsed to just the disclaimer with
the actual guidance gone. Caught only because the run was re-read rather than assumed.

**The disclaimer moved into Python.** Rewritten again, the model supplied the disclaimer on one run
and silently dropped it on the next — the X55 bluetooth answer opened straight into general guidance
with nothing marking it. That is precisely the failure rule 2 names as the most damaging, and a prompt
is the wrong instrument for a guarantee. `_NOT_IN_MANUAL` is now prepended in `AnswerStep` whenever
the route is `general`, and the prompt is told not to write one. The UI badge is not sufficient on its
own: it does not survive copy and paste.

### Corrections to the docs

`docs/architecture.md` claimed retrieval returns "top-100 candidates" and reranking scores "the
top-30 … roughly 300 ms". The measured build is one stage of 12 → 12 → 6 at ~1,249 ms. Both corrected,
along with the status header and the `(not built)` markers.

The evaluation section listed `partial` as an `expected_route` value. No such route exists — it is
`manual+general` — and no row uses it. The 44 rows cover only `manual` 38, `general` 4, `decline` 2,
so **`manual+general` and `escalate` are entirely unmeasured**. Recorded rather than quietly fixed,
because closing that gap needs `web_search` and `escalate` to exist first.

`RETRIEVE_LIMIT = 100` was dead config — every caller passes `RERANK_CANDIDATES` explicitly. Removed,
and `search()` now requires `limit` rather than defaulting it.

### Checkpoint

- [x] Four steps, assembled by `build_pipeline()`.
- [x] `source` and citations built in Python, not accepted from the model.
- [x] Grounded, grader-recovered, ungrounded and declined questions all behave.
- [x] Retrieval unchanged by the refactor — Recall@1 87%, MRR 0.919.
- [x] Every `general` answer carries its disclaimer deterministically.
- [ ] `resolve_query`, `web_search`, `escalate`.
- [ ] Streaming, transport, persistence.

---

## Slice 7 — streamed answers, SSE transport, session persistence

### Outcome

`POST /chat` streams step events and answer tokens over SSE, and conversations persist to SQLite and
reopen with their citations intact. `playground/check_api.py` drives the real endpoints end to end.

### Why

The pipeline answered well and nothing could see it. Day 3 of five, and the frontend cannot start
until there is an API to build against — so transport was the bottleneck for everything remaining,
not the most interesting work available.

### Streaming and structured output are not in conflict

D9 promised streamed tokens; the answer step used `chat.completions.parse()`, which blocks. Rather
than assume which had to give, this was measured first: `chat.completions.stream()` takes the same
`response_format` and emits raw JSON token by token — `'The'`, `' front'`, `' tyre'`. `event.parsed`
is useless for it, populating a field only once the string literal closes, but the raw deltas are not.

`complete_stream()` accumulates the buffer, finds `"answer":"`, and hands the partial value to
`json.loads`. That unescapes `\n`, `\"` and `\uXXXX` for free and fails cleanly mid-escape, so the
delta is skipped until the next one completes it. Ten edge cases were checked directly — empty value,
embedded quotes, a value ending in a backslash, a dangling escape, a unicode escape — because the
naive version got two of them wrong: it read `segment[index - 1]` at index 0, which wraps to the end
of the string.

### The pipeline stayed synchronous

`PipelineContext` gained an optional `sink`, and `Pipeline.run()` an optional argument. The API runs
the pipeline on a worker thread whose sink pushes to a `queue.Queue` and drains that queue into the
response. That, not async, is what makes a step event reach the browser mid-run — and `eval/run.py`
and the playground scripts pass no sink and are untouched. Retrieval after the change: Recall@1 87%,
MRR 0.919, identical.

### Commands

```bash
uv add --project backend fastapi uvicorn pydantic
uv run --project backend --locked --no-sync python scripts/index.py data/chunks/<file>.jsonl
uv run --project backend --locked --no-sync uvicorn app.api:app --app-dir backend
uv run --project backend --locked --no-sync python playground/check_api.py
```

### Observed

Four questions over one session, then reopened. Times are from request start.

| Question | Retrieve | Rerank | Gate | First token | Done | Tokens |
|---|---:|---:|---:|---:|---:|---:|
| Bluetooth pairing | 2.09 s | 0.81 s | — | 2.89 s | 5.44 s | 137 |
| Engine oil | 0.36 s | 1.06 s | 0.96 s | 2.38 s | 3.88 s | 52 |
| Service centre | 0.49 s | 0.89 s | 1.16 s | 2.55 s | 5.16 s | 163 |
| Weather | 0.49 s | 0.78 s | 0.93 s | 2.19 s | 2.20 s | 1 |

No `gate` event on the first question — it scored above `GATE_HIGH`, so no grader ran and none was
announced. That is the D9 rule holding in the transport, not just in the pipeline.

Reopening returned all eight messages with `source` and page citations intact.

### The cold start was landing on the first question

The first run showed 8.66 s to first token against ~2.4 s for the rest, all of it a 6.64 s rerank —
the ONNX model loading lazily on first use. In a demo that penalty lands on the first question anyone
asks, which is the worst possible place for it. The cross-encoder is now loaded in FastAPI's
`lifespan` startup; first-question rerank fell to 0.81 s and first token to 2.89 s.

### A fragility the work exposed

`data/app.db` was deleted mid-testing, which also destroyed the `manuals` rows. Recovering them meant
re-running `index.py` — which re-embeds, at real cost — to rewrite three columns derivable from the
JSONL and the PDF. Derived state should not be expensive to rebuild, so `index.py --register-only`
now rewrites the row in seconds without embedding.

### Corrections to the docs

`docs/architecture.md` described a layering that was never built — `routes.py`, `service.py`,
`repository.py`. What exists is `api.py` for HTTP and SSE, `db.py` for SQLite, and the pipeline for
orchestration; a service module would forward calls and hold nothing. It also listed
`unresolved_streak` on `sessions`, which arrives with `escalate` (D14), not now.

### Checkpoint

- [x] Prose streams token by token from a structured call, in one request.
- [x] Step events reach the client while later steps are still running.
- [x] A skipped grader emits no event.
- [x] Sessions and messages persist; reopening restores citations.
- [x] The reranker is warm before the first question.
- [x] Retrieval unchanged — Recall@1 87%, MRR 0.919.
- [ ] `resolve_query`, `web_search`, `escalate`.
- [ ] Frontend.
