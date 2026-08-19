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

---

## Slice 8 — web search for the `general` route

### Outcome

`web_search` runs on questions the manual does not cover, and the `web` citation type emits for the
first time. Asked about warranty terms, the assistant now returns 7 years / unlimited km with a link
to the source, rather than explaining that it cannot know.

### Why

The gate has routed to `general` since Slice 6, but the answer step had only the model's own
knowledge behind it. Brief item 16 is explicit that a question the manual omits — a recall, a service
centre, current pricing — must **still propose a solution**. D13 places web between general guidance
and a human handoff. Without it the honest answer was a useless one.

### Measured before building, and it changed two decisions

**`search_depth` stays `basic`.** The first probe showed ~150-character snippets and suggested
`advanced` was needed. Comparing them directly: advanced roughly doubled the content (3,742 → 6,501
chars) but also the latency (2.10 s → 4.77 s), for two API credits instead of one. The short snippets
in the first probe were a property of the *results* — Facebook and Instagram posts — not of the depth.
On real questions `basic` returns 1,100–1,400 characters per useful result.

**`WEB_DOMAINS` defaults to empty.** A restriction matching nothing returns an empty list, silently
and identically to a domain that does not exist:

| `include_domains` | Results |
|---|---:|
| `["baicinternational.com"]` | 0 |
| `["baicglobal.com"]` | 3 |
| `["example-does-not-exist-xyz.com"]` | 0 |

A typo would therefore disable web search permanently and invisibly — which is close to what happened
in the prior build, where every automotive question was restricted to `ruh.ac.lk`. The provider logs a
warning when domains are configured and nothing comes back.

### What the prior repos got wrong

| Prior mistake | Here |
|---|---|
| Domain allowlist hardcoded in a `.py` file | `WEB_DOMAINS` in `.env`, empty by default |
| `site:` pasted into the query text | passed as the `include_domains` parameter |
| Model name sliced out of a filename, breaking on `"x55"` | query built from the manual's stored title |
| A fabricated confidence number on results | none invented |

### Titles became real data

The query is the manual's stored title plus the question, so the auto-generated
`Baic Bj30 E30 Owner Manual En` would have ridden into every search as dead tokens. PDF metadata was
checked first and is useless here — the two manuals report `'6.24画册'` and `'前言'`. So `index.py`
gained `--title`, and the titles are now `BAIC BJ30 / E30` and `BAIC X55 II`. They stay database rows,
never product names in code (rule 3).

### Commands

```bash
uv add --project backend tavily-python
uv run --project backend --locked --no-sync python scripts/index.py \
    data/chunks/<file>.jsonl --register-only --title "BAIC BJ30 / E30"
uv run --project backend --locked --no-sync python playground/check_pipeline.py
```

### Observed

| Question | Score | Route | Web | Cited |
|---|---:|---|---:|---|
| Bluetooth pairing (X55) | −5.52 | `general` | 4 | 1–3 web |
| Is there a recall on this vehicle? | −6.74 | `general` | 4 | 0–2 web |
| What does the warranty cover? | −5.44 | `general` | 4 | baicnz.com |
| Weather forecast | −10.12 | `decline` | — | — |

The four manual-answered questions were unaffected: no `web` step event, page citations unchanged.
Retrieval unchanged — Recall@1 87%, MRR 0.919.

### Prompt leakage, four attempts and an honest residual

The model kept narrating its own context: *"None of the listed results mention…"*, *"the web results
you provided"*. Three prompt revisions each reduced it and none removed it, and one made things worse
— an illustrative sentence in the prompt (*"I can't confirm whether this vehicle has an open recall;
your dealer can check by VIN"*) was reproduced verbatim as the opening line of an unrelated warranty
answer. Few-shot contamination from a single quoted example.

What helped most was structural, not persuasive: **the retrieved context moved from the user message
into the system message**. Sent as part of the user turn it genuinely *was* "information you
provided", and the model said so. Blocks are now headed `What the manual says:` and `What you know:`
rather than `Passages:` and `Results:`.

**This is reduced, not solved.** Across two runs afterwards: one run clean, one containing *"the
manuals content you're using here doesn't include recall data"*. It recurs specifically where the
model must explain why it cannot answer, which is inherently self-referential. Recorded rather than
claimed fixed. The parts that must never fail — the `source` label, the prepended disclaimer, citation
construction — are Python-owned and were correct in every run.

### Checkpoint

- [x] `web_search` runs on `general` only, never on a manual-answered question.
- [x] Web citations carry real URLs; page and web citations never mix in one answer.
- [x] A Tavily failure degrades to general knowledge instead of raising.
- [x] `include_domains` passed as a parameter, never as query text.
- [x] Manual titles set as data.
- [x] Retrieval unchanged — Recall@1 87%, MRR 0.919.
- [ ] Prompt leakage fully eliminated — reduced only.
- [ ] `escalate`, so the safety route stops dead-ending.

---

## Slice 9 — the frontend: chat beside the cited page

### Outcome

A question typed in a browser streams its answer beside the manual page it came from. Citation pills
move the PDF pane; web pills open a tab. Past conversations reopen with their citations intact. The
whole system is now visible without a terminal.

### Why

Everything worked and nothing could be seen. The deliverable is a client proposal and three previous
attempts failed, so credibility is the product — and a demo that cannot be looked at is not a
proposal.

### Shape

Next.js 16, React 19, Tailwind 4, in `frontend/`. The backend's conventions translate directly: one
boundary for the wire (`lib/api.ts`), settings read once (`lib/config.ts`), types mirroring the
backend contract so a change there fails the type check here, and one stateful hook with everything
else presentational.

`automobile-rag-frontend` was copied in and owned here rather than referenced (D10). What did and did
not transfer is recorded in D10's outcome — briefly, less than expected.

### Two things the previous build got wrong that were rebuilt, not carried

**Transport.** `useChatSocket.ts` is WebSocket where D9 chose SSE, and it fetched its step labels from
a `/pipeline-status` endpoint returning a node → icon-and-label map. That is the invented-stages
pattern D9 forbids: labels there described a diagram, not work. Ours come from `ctx.emit` at the
moment the step ran.

**Page mounting.** Jumping to page 249 set the render count to 249 and mounted every page from 1.
PDF.js guidance is roughly 25 at once — a 10× overshoot, and the reported slowness. Replaced with a
window of `PAGE_WINDOW` pages around the current one, with sized spacers standing in for the rest.

### The spacer bug worth recording

With windowing in place, scrolling from page 16 to 17 made 17 vanish. The spacers were sized from an
assumed A4 ratio (1.414) and ignored the per-page `Page N` labels, so every page added a small error
to the estimated scroll position. By page 17 the accumulated drift exceeded one page height and the
window computed from `scrollTop` no longer contained the page being looked at.

Fixed by measuring the real ratio from `page.getViewport({scale: 1})` on first load and removing the
labels, so a row is exactly one page plus a fixed gap. Window widened 6 → 10 for headroom.

The general lesson: virtualised scrolling is only correct while the estimated row height equals the
real one. Any per-row chrome outside that estimate accumulates.

### A dependency trap

`pdfjs-dist` was installed at the top level, but `react-pdf` pins its own nested copy. The install
script copied the hoisted worker, and the viewer failed with *"The API version 5.4.296 does not match
the Worker version 5.7.284"* — surfaced to the user as "Could not open this manual". The worker is now
resolved through `react-pdf`, and the top-level `pdfjs-dist` should be uninstalled.

### pnpm → npm

The commands in `CLAUDE.md` specified pnpm. It is not installed and neither is corepack, and the
source repo shipped `package-lock.json` anyway. Switched to npm rather than adding a package manager
to the setup a client would have to reproduce.

### Commands

```bash
cd frontend && npm install          # runs copy-pdf-worker.mjs via postinstall
npm run dev                          # port 3000; the API on 8000
npm exec tsc -b --pretty false
npm run lint
npm run build
```

### Observed

| Check | Result |
|---|---|
| `tsc -b` | clean |
| `npm run lint` | clean, after ignoring `public/**` — eslint was linting the minified worker, 1,584 warnings |
| `npm run build` | clean |
| Manual answer → citation moves the pane | works |
| Multi-page citation, all pages reachable by scrolling | works |
| Repeated page appears once | works |
| Web-routed question → dashed pills, opens a tab, pane untouched | works |
| Out-of-scope question declines without stalling | works |
| Reopening a past conversation | works, citations intact |
| Jumping to a late page | responsive |

Four `react-hooks/set-state-in-effect` errors, new in React 19, were each a real ordering bug rather
than a lint nuisance — one of them was losing the first message of every conversation, because `send`
captured `sessionId: null` from the render before the session existed.

### Checkpoint

- [x] The pipeline is drivable from a browser end to end.
- [x] Page and web citations are visibly distinct (D13).
- [x] Session history exists and reopens with citations.
- [x] A conversation stays locked to its manual (D11).
- [x] The PDF worker, cmaps and fonts are served locally — no CDN.
- [x] Step labels come from the pipeline, never from a static map (D9).
- [ ] `escalate` still returns an `error` frame, so safety questions dead-end in the UI.
- [ ] `manual+general` and `escalate` still have no labelled eval rows.
- [ ] `resolve_query` unbuilt — follow-ups are retrieved as standalone questions.

---

## Slice 10 — the gate made trustworthy, and the handoff built

### Outcome

`escalate` writes a real record and shows the user its reference, so a safety question no longer
dead-ends in an error frame. Getting there meant fixing the gate first: routing was non-deterministic,
and the reranker could not read a third of the corpus.

### Why the order

The plan was escalation. The eval rows added for it exposed something worse — `esc-06`, "what is the
wheel nut torque specification", scored **−2.07**, above `GATE_HIGH`, so no grader ran and it routed
confidently to `manual`. Neither manual contains a fastener torque anywhere. Building the handoff
would not have helped: the question never reaches the branch. A confidently wrong answer to a
plausible safety question does more damage in a demo than a missing feature.

### The reranker was reading 512 tokens of everything

`RERANK_MAX_TOKENS` is the model's window; chunks are sized for the embedder's 8,191. Measured: **11%
of BJ30's tokens and 22% of X55's were unreachable**, and the chunk holding the towing capacity was
read to 22% — the answer at character 5,196, the cut at 2,082. It was scoring that chunk on engine
cylinder arrangement.

Fixed by scoring every window and keeping the best. A chunk that fits produces one window and scores
exactly as before, so only the 6–9% that overflow change. `spec` Recall@5 and @10 went 86% → 100%.

### Markdown tables: built, measured, reverted

Docling's default writes one sentence per cell, repeating the row label in each. Windowing put the
towing chunk back in the top 5 and the grader still said it does not answer the question — it does,
the answer is `1.5`. Markdown looked like the fix, and was not:

| | markdown | triplet |
|---|---|---|
| `spec` Recall@1 / MRR | 71% / 0.821 | **86% / 0.893** |
| `procedure` Recall@1 / MRR | **86% / 0.906** | 82% / 0.883 |
| `bj30-02` engine oil | `manual+general` | **`manual`** |
| `bj30-23` trailer weight | `escalate` | `escalate` |

It trades one kind of accuracy for another and does not fix what it was built for. Reverted, with the
reasoning in D16 so it is not retried blindly.

**One defect found on the way is worth carrying forward.** Docling pads markdown rule rows to the
column width, so a wide table's `|---|` line ran to 633 characters. The tokeniser splits each dash
separately, so the rule row alone exceeded the whole 512-token window and no data row was ever read.
That made the first markdown attempt score *worse* than the default, which nearly buried the real
result under a formatting artefact.

### The gate disagreed with itself

Both model calls ran at the API default temperature of 1.0. Over five identical runs of every question
reaching the grader, **4 of 15 changed route** — same question, same passages, same index. D2 says
routing is deterministic; that holds only if the evidence is stable, and an eval harness over a
component that disagrees with itself is not a test suite.

Temperature 0 took it to 2/15. The rest was ambiguity in the fields:

- `question_is_about_the_domain` was read as *"do the passages cover it"*, so "how much does this car
  cost new" was judged off-domain and **declined**.
- `question_touches_a_safety_topic` fired on "where is my nearest service centre".

**The first prompt fix made things worse and is recorded rather than quietly replaced.** Wording it as
"a commercial or administrative question is not a safety topic" fixed two general questions and broke
three escalations — the model read any practical question as administrative. On a safety route a
missed escalation is worse than a spurious one, so it was rejected and rewritten around the
distinction the rows actually show: a **procedure, limit or specification** on a listed topic is a
safety topic; what something costs, where to get it, or who to contact is not.

Result: route instability **4/15 → 0/15**, misroutes across 52 rows **6 → 2**.

### The same PDF ingested to a different index each run

Found while verifying the revert. `merge.py` sorted a set of headings by frequency with no tiebreak,
so ties resolved on set iteration order, which varies with string hash randomisation. `index.py`
prepends `heading_path` into the embedded text — so re-ingesting the same PDF produced different
vectors. 90 of 213 chunks differed between two runs of identical code. One-line fix; verified by
ingesting twice and comparing checksums.

### Escalation

`EscalateStep` sets `ctx.escalation`, not `ctx.answer`. A handoff is not an answer, and forcing it
into the `Answer` model would mean a fourth `Source` value, blurring the manual/general distinction
the UI renders — the one D13 exists to protect. The API emits `escalated` instead of `done`.

`escalations` does not copy the transcript; it is the session's `messages`, joined when the package is
read. `messages` gains a nullable `escalation_id` so a reopened conversation still renders the handoff
as a handoff.

Only D14's gate-rule trigger is reachable. The other three all need `resolve_query`, and are marked
`(not built)` rather than approximated.

### Commands

```bash
uv run --project backend --locked --no-sync python playground/check_truncation.py
uv run --project backend --locked --no-sync python playground/check_grader_stability.py
uv run --project backend --locked --no-sync python scripts/ingest.py data/manuals/<file>.pdf
uv run --project backend --locked --no-sync python scripts/index.py data/chunks/<file>.jsonl --title "..."
```

Conversion is the expensive half, so `parse()` now caches the converted document under `data/parsed/`.
Re-chunking went **11.3 min → 6 s**, which is what made it affordable to try the table change and
reject it on evidence rather than argument. `--reparse` forces the models to run again.

### Observed

| | before | after |
|---|---|---|
| Overall Recall@1 / MRR | 85% / 0.902 | 85% / 0.902 |
| Recall@10 | 97% | **100%** |
| `spec` Recall@5 / @10 | 86% / 86% | **100% / 100%** |
| Route instability | 4/15 | **0/15** |
| Misroutes (52 rows) | 6 | **2** |
| Re-chunk a manual | 11.3 min | **6 s** |

### Checkpoint

- [x] The reranker can read every chunk it scores.
- [x] The same question routes the same way twice.
- [x] The same PDF ingests to the same index.
- [x] A safety question produces a handoff with a reference, not an error frame.
- [x] The handoff package carries the transcript, pages already shown and the trigger reason.
- [ ] `bj30-23` still misroutes to `escalate` — the trailer weight is in a table the grader reads as
      not answering the question. Neither table format fixed it.
- [ ] `esc-06` scores −2.07 and never reaches the grader. `GATE_HIGH` was calibrated on positives only.
- [ ] Operator inbox — the record exists and the endpoints serve it; nothing renders it yet.

---

## Slice 11 — what the gate is shown, and what the eval was measuring

### Outcome

Routing accuracy is now part of `eval/run.py` rather than a claim in `AGENTS.md`, the grader judges
the span its own score was measured on, and the eval's one safety-specification row was found to be
testing the opposite of what it intended. Routing accuracy is **94% (50/53)**.

### Why the order

Slice 10 closed with two open misroutes and a plan to recalibrate `GATE_HIGH`. Both turned out to be
different problems than recorded, and neither is fixed by moving the band. Verifying that first was
only possible because the harness could not measure routing at all — `AGENTS.md` said `eval/run.py`
reported routing accuracy; `eval/run.py`'s own docstring said the gate did not exist yet. Neither was
true. That went in first, because every claim below depends on it.

### Corrections to Slice 10

**"Neither manual contains a fastener torque anywhere" is wrong.** The BJ30 states *"all wheel nuts
are tightened to 110±10 N·m"* on printed pages 245–247 — the only torque figure in either corpus, and
exactly the one `esc-06` asked for. The row expected `escalate` from a manual that answers the
question. The gate was right and the label was wrong, so `esc-06` was never a misroute.

It is now the X55 form of the same question, which the corpus genuinely cannot answer; the BJ30 form
became `bj30-24`, expecting `manual`. Slice 10's "misroutes 6 → 2" was really 6 → 1 plus a bad label.

**`bj30-23` is not a truncation problem.** The grader was reading character 0–600 of a 9,543-character
table while the answer sat at character 5,202, which looked like the whole explanation. Fixing that
did not move the row: with the correct span in front of it, the grader still judges `Total mass of
quasi-trailer (T), BJ6470X52MHEV = 1.5` as not answering "what is the maximum trailer weight I can
tow", 5 runs out of 5. The serialisation is the obstacle, and D16 already measured that neither table
format fixes it. Still open, and now open for the right reason.

### The gate was scoring one span and judging another

D16 fixed the reranker to score a long passage by its best window. The grader kept reading the head of
the passage. For the towing chunk those are different subjects entirely — the score came from the
trailer rows, the verdict from wheel-alignment rows.

Handing the grader the full winning window was the obvious fix and is the wrong one. At ~10,000
characters over six passages it flipped the X55 torque question from `escalate` to `manual` 5/5 —
more text reads as more coverage, and that is the one question the corpus cannot answer. Capped back
to the original 600 characters it holds `escalate` 5/5. Kept at `excerpt[:600]`: same budget, same
tokens, and the gate now judges the text its score came from. It did not change the misroute count,
which is recorded in D18 rather than dressed up as a win.

### The bypass, not the band, is the safety hole

Asked of the X55, "what torque do I tighten the wheel nuts to?" scores **+3.29**. Above `GATE_HIGH`,
so no grader runs and it answers from the manual — the confidently wrong safety answer this system is
built to avoid. Graded, it escalates 5/5. The grader is right and is never consulted.

Slice 10 proposed recalibrating `GATE_HIGH`. That cannot work. Correct `manual` rows run from −7.21 to
+9.29 and this question sits at +3.29 among them; no threshold separates them, because the
cross-encoder measures whether the manual *discusses* a topic, not whether it *states the value
asked for*. Those come apart exactly on specification questions.

Always calling the grader does fix it, and costs: **+1.6 s** on the 37 of 53 rows that currently
bypass, and `x55-08` regresses from `manual` to `general`. Those two misroutes are not equal in cost —
one is a wrong torque figure, the other is a covered question answered without citations — so this is
a product call, not an accuracy-count call. Left open in D19 rather than decided quietly.

### The harness is not as stable as the numbers suggest

`bj30-16` appeared as a new misroute and is not one — it scores −4.51, just under `GATE_HIGH`, and
routes `manual` 5/5 when measured directly. It flips between runs. Slice 10 took instability from
4/15 to 0/15 on the rows it sampled; it is not 0 across the whole set. A single `eval/run.py` routing
number should not be read to the row.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
uv run --project backend --locked --no-sync python playground/check_evidence.py
```

### Observed

| | before | after |
|---|---|---|
| Routing accuracy | not measured | **94% (50/53)** |
| Recall@1 / MRR | 85% / 0.902 | 85% / 0.905 |
| `spec` Recall@1 | 86% (n=7) | 88% (n=8) |
| Real misroutes | 2 claimed | **2** (`esc-06` X55, `bj30-23`) + 1 flaky |
| X55 torque question | `manual`, unmeasured | `manual`, **measured and labelled** |

### Checkpoint

- [x] The eval harness measures routing, as `AGENTS.md` always claimed it did.
- [x] The gate judges the span its score was measured on.
- [x] The one question the corpus cannot answer is in the eval set, with the right label.
- [x] `esc-06`'s original label corrected; `bj30-24` added for the answerable form.
- [ ] `bj30-23` — the grader reads the trailer row and still says it does not answer. Serialisation,
      not truncation; D16 already ruled out both table formats.
- [ ] The `GATE_HIGH` bypass lets an unanswerable specification question through as `manual`. No
      threshold closes it; always grading costs 1.6 s and one regression. Decision open (D19).
- [ ] Operator inbox — the record exists and the endpoints serve it; nothing renders it yet.

---

## Slice 12 — `resolve_query`: a conversation that remembers the turn before

### Outcome

Follow-up turns work. `resolve_query` was the last unbuilt step of the online pipeline; with it, all
seven are built. Routing accuracy **93% (53/57)** over a set that now includes four follow-up rows.

### The report

Two turns in the browser. "how can I change flat tire" answered correctly from pages 244, 245 and
253. Then "I parked vechile whats now" — best match "Displayed", and a handoff reference.

Nothing in the gate was wrong. Retrieved on its own, that sentence has no subject; the grader reported
truthfully that the passages did not answer it; the topic read as safety-critical; the gate escalated,
which is what D13 says to do when the manual is silent on a safety topic. **The escalation was correct
behaviour on a meaningless input.** Every turn was being treated as the first, because
`build_pipeline()` began at `retrieve` and said so in its own docstring.

### The rewrite that reads well and retrieves nothing

The first prompt asked for a standalone question and got one: *"I parked the vehicle—what should I do
next?"* It is fluent, it stands alone, and it has thrown away the flat tyre. Score −7.04 → −4.82, and
still `escalate` — a change that looks like progress in the numbers and fixes nothing.

Requiring the rewrite to **name the task**, and saying plainly that "what should I do next" without
naming what is being done has failed, took the same turn to −7.04 → **−1.77** and route `manual`.
Recorded in D20, because the failure is the instructive half.

### What reads the rewrite

Retrieval, the grader and the answer, all through `ctx.query`. Grading the raw turn would have
escalated it again for exactly the original reason.

The answer step additionally receives the previous assistant turn, and that took three attempts.
Placed before the passage block it was ignored outright — the model replayed the procedure from "park
on a firm, level surface". Moved after the passages and told to "begin from the first step they have
not yet done", it swung the other way and announced the wheel change was done, handing over torque
figures to someone who had not jacked the car. **Replaying a step is an annoyance; skipping one is an
injury**, and the second version was the worse failure despite reading better. What holds is pinning
it to reported progress only: continue from where they said they are, and assume nothing further.

It is still not a procedure walk-through. "What should I do next" retrieves the tail of the procedure,
so the reply offers the closing branches rather than jacking and removal. Recorded as open in D20.

### The harness measures it now

Four rows carry a `history` array and are rewritten through `resolve()` before searching, the same
call the pipeline makes. A follow-up feature verified only by a playground script is not covered by
the test suite, and rule 4 says the harness is the test suite.

Recall@1 fell 85% → 81% and MRR 0.905 → 0.881. **That is not a regression.** Three harder grounded
rows entered the denominator; the existing rows' rerank positions are unchanged, which the "moved
down" list confirms — the same three rows as Slice 11, plus the new `fu-01`.

### Two open defects met again from a new direction

`fu-03` — the X55 asked for a wheel nut torque as a *follow-up* — misroutes to `manual` at −1.00,
above `GATE_HIGH`, never reaching the grader. Identical to `esc-06`, reached by a different path.
D19's bypass is now visible in two shapes in the eval, which is the argument for closing it.

`bj30-02` and `bj30-16` continue to trade places as the flaky row near the band. Slice 11 recorded
that instability is not zero across the whole set; this run is the second observation of it.

### Rejected on the way: a richer verdict for the gate

Before building any of this, the gate's three booleans were replaced with `needs` / `coverage` /
`evidence_quote` / `finding`, on the theory that one bit cannot separate "the manual is silent" from
"the manual discusses this without stating the number". Measured over five runs of eight rows:
**one fixed, four broken.** `partial` proved a magnet — `bj30-02`, whose answer is present and
quotable, was called partial 5/5 and demoted to `manual+general` — and `dec-01` destabilised to 3/5.

It fixed `esc-06`. So does calling the existing grader, which routes that question correctly 5/5
already. The redesign was solving a problem the bypass creates. Kept in
`playground/check_verdict.py` so it is not retried blindly.

### While proving that, the reason `x55-08` misroutes turned up

The grader is right about it. "descent" appears in **none** of the six retrieved passages and nowhere
in the X55 corpus. The chunk that does explain the feature — pdf 127–128, *"touch the HDC switch, and
the HDC enters the standby state"* — says only "HDC", and its `heading_path` is `1. Wear > ON/OFF`.
The neighbouring chunk got the heading `Automatic release > HDC` while its body is about AVH.

`index.py` prepends `heading_path` into the embedded text, so a wrong heading actively pollutes the
vector. **10 of 213 BJ30 chunks and 26 of 262 X55 chunks** carry a page header or a list number as
their leading heading.

This matters beyond one row: `x55-08` is the only measured obstacle to always calling the grader, and
it is a *retrieval* fault, not a grader fault. D4's LLM-written context sentence — documented, and
marked `(not built)` in `architecture.md` — is the mechanism designed for exactly this. `AGENTS.md`
claimed it was built; corrected.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
uv run --project backend --locked --no-sync python playground/check_followup.py
uv run --project backend --locked --no-sync python playground/check_verdict.py
```

### Observed

| | before | after |
|---|---|---|
| "I parked vechile whats now" | `escalate`, −7.04 | **`manual`, −1.77** |
| "and how much do I need?" | `general`, −8.43 | **`manual`, −5.05** |
| Routing accuracy | 94% (50/53) | 93% (53/57) |
| Follow-up rows in the harness | 0 | **4** |
| Online pipeline steps built | 6 of 7 | **7 of 7** |

### Checkpoint

- [x] A follow-up turn is rewritten before anything searches.
- [x] The grader and the answer read the resolved question, not the raw turn.
- [x] The answer continues from reported progress instead of replaying from step one.
- [x] A first turn makes no rewrite call and emits no `resolve_query` event (D9).
- [x] Follow-up behaviour is measured by the harness, not only by a playground script.
- [ ] `fu-03` and `esc-06` — the `GATE_HIGH` bypass, unchanged and open (D19).
- [ ] `bj30-23` — table serialisation, unchanged and open (D16).
- [ ] A follow-up mid-procedure gets the closing branches, not the next step. Retrieval does not
      know where in a procedure a question sits (D20).
- [ ] D14's `unresolved_streak`: no column, no triggers. Two of them are now unblocked.
- [ ] D4's context sentence — the fix for `x55-08`, and the precondition for closing the bypass.
- [ ] Operator inbox — the record exists and the endpoints serve it; nothing renders it yet.

---

## Slice 13 — the escalation counter, and three of D14's four triggers

### Outcome

`unresolved_streak` exists as a column, a pure function and one config value. Asking for a person and
the unresolved streak both escalate, and the handoff now records *which* rule fired instead of a
constant. Routing accuracy **92% (54/59)** over a set that gained two rows for the new triggers.

### It cost no extra model call, as D14 said it would

`resolve_query` was already calling the model on every follow-up. The two observations D14 needs ride
on that call: `asks_for_a_person`, and `progress` as one of `reports_failure`, `confirms_success`,
`new_topic`, `unclear`. `next_streak()` turns the second into a count. Neither the model nor the
prompt knows the threshold, the current count, or what escalation is.

### The check was in the wrong place, and one row proved it

The streak check first sat *below* the score band, on the reasoning that a manual answering this turn
means something did resolve it. Then `esc-09` — "it is still not working", arriving with a streak of
2 — scored **+3.78** and answered from the manual.

That reasoning was wrong. A streak only reaches the threshold through turns the user reported as
failures, or answers that were not grounded in their manual. A confident score on the next turn is the
fourth attempt at what has already failed three times, and a cross-encoder matching "not working"
against some passage is not evidence otherwise. Both new triggers now run before the band. Recorded in
D21 rather than quietly moved.

Two resets matter as much as the trigger. The handoff sets the count to zero — left at 3, every later
turn in the session escalates and the user never gets another answer. And confirming something worked,
or changing subject, resets it, so a solved problem does not carry a debt into the next question.

### Verified end to end

| in | turn | route | streak out |
|---|---|---|---|
| 0 | "can I speak to a person about this?" | `escalate` — *The user asked to speak to a person* | 0 |
| 2 | "it is still not working" | `escalate` — *Nothing resolved it across 3 turns* | 0 |
| 1 | "it is still not working" | `manual` | 2 |
| 2 | "great that fixed it, thanks" | `manual` | 0 |

### The grader's instability is now the largest source of misroutes

Three consecutive full eval runs produced three different misroute sets among rows whose code path
never changed — `bj30-16`, then `bj30-02`, then `esc-03`. Measured over 5 identical runs of every row
a grader decides: **2 of 16 changed route** — `bj30-02` on `passages_answer_the_question`, `esc-03` on
`question_touches_a_safety_topic`, which decides `escalate` against `general`. A third row, `dec-02`,
flips the safety-topic field on some runs without its route moving, so the field-level instability is
wider than the route count shows.

Slice 10 recorded instability at 0/15 and that number has been quoted since. It was true of the rows
sampled then and is not true of the set now. **Any single routing number in this log should be read as
±2 rows.**

`check_grader_stability.py` was itself measuring the wrong thing once follow-ups existed — it graded
the raw question, so `fu-01` looked like a stable `general` when the pipeline routes it `manual`. Run
in that state it reported **3 of 20**, and that figure was written into this log before the script was
corrected. It now mirrors `ResolveQueryStep` and skips rows a D14 trigger decides before the grader is
consulted: 16 rows reach the grader, not 20, because the resolved follow-ups score above `GATE_HIGH`
and never get there. The corrected figure is 2 of 16.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
uv run --project backend --locked --no-sync python playground/check_grader_stability.py
```

### Observed

| | before | after |
|---|---|---|
| D14 triggers reachable | 1 of 4 | **3 of 4** |
| Escalation reason | one hardcoded constant | the rule that fired |
| Routing accuracy | 93% (53/57) | 92% (54/59) |
| Grader route instability | "0/15" (Slice 10) | **2/16, measured** |
| Extra model calls added | — | **none** |

### Checkpoint

- [x] `unresolved_streak` persists on the session and survives a reopened conversation.
- [x] Asking for a person hands off, without the manual being consulted first.
- [x] Three unresolved turns hand off, checked before the score band.
- [x] The handoff resets the counter; so do success and a change of subject.
- [x] The operator reads which rule fired, not a constant.
- [x] Both triggers are asserted by the harness, not only by a playground script.
- [ ] 2 of 16 graded rows change route across identical runs, on two different grader fields. This
      is now the biggest single source of misroutes and nothing in this slice addressed it.
- [ ] Manual-weak-and-web-weak — D14's fourth trigger, still `(not built)`.
- [ ] `esc-06` and `fu-03` — the `GATE_HIGH` bypass (D19), unchanged.
- [ ] `bj30-23` — table serialisation (D16), unchanged.
- [ ] Operator inbox — the record exists and the endpoints serve it; nothing renders it yet.

---

## Slice 14 — the bypass closed with a checkable fact

### Outcome

The X55 no longer invents a wheel nut torque. Routing **92% (54/59) → 97% (57/59)**, twice, with
`escalate` at **12/12** in both runs. The grader now runs on every question, and above `GATE_HIGH` it
may overrule the score in exactly one situation: the question wants a specific value, the subject is a
safety topic, and the value cannot be quoted from what was retrieved.

### Three simpler policies were measured and rejected first

D19 left this open with a plan to recalibrate `GATE_HIGH`, which D19 itself had already shown to be
impossible. So each candidate was run 3 times over all 59 rows before any production code changed:

| policy | fully right |
|---|---|
| today, bypass intact | 54/59 |
| grade everywhere, the verdict decides outright | 46/59 |
| grade everywhere, the two booleans veto above the band | 51/59 |
| **grade everywhere, a value-scoped quote vetoes** | **57/59** |

**Both middle policies are worse than doing nothing**, and for one reason: the veto is the product of
two unreliable booleans. `question_touches_a_safety_topic` is true of most vehicle questions, and
`passages_answer_the_question` false-negatives often enough that together they escalate questions the
manual answers — `x55-16` (parking assist), `x55-12`, and `fu-01`, the follow-up Slice 12 had just
fixed. Shipping either would have traded two rare dangerous misroutes for several common ones.

### Why a quote succeeds where a judgement fails

"Do these passages answer the question" is an opinion and cannot be checked. "Copy the sentence that
states the value" is an extraction, and `quoted()` checks the result against the excerpts the grader
was shown. A hedged or invented quote fails a substring test. The route then rests on a fact rather
than on trust, which serves D2 better than a boolean does.

### Two attempts to get there, both worth recording

Requiring a quote of **every** question broke procedures — a procedure has no single sentence carrying
its answer, so an absent quote proves nothing, and `fu-01` and `x55-16` escalated. Scoping it to value
questions fixed that and broke nothing, but then fixed nothing either: the first wording of
`asks_for_a_specific_value` returned **False** for "what torque do I tighten the wheel nuts to?" on 2
of 3 runs. The model was reading it as *"do the passages contain a value"* — the same confusion D17
had to correct for `question_is_about_the_domain`, met a third time. Rewording it to judge the
question alone, and stating outright that it still wants a value when the passages are silent, took it
to `value=True` 3/3.

### Two more labels were wrong, found the same way as `esc-06`

`x55-12` and `bj30-17` both ask how deep the vehicle can ford, and both expected `manual`. **Neither
manual states a depth.** The X55's page 168 says *"correctly estimate or find out the wading depth"*
and gives no figure; the BJ30 has a wading mode and depth **detection** but no maximum, and the quote
it offered — *"the water depth detection system measures the water level"* — describes the feature,
not a limit. A confident depth is how an engine gets flooded. Relabelled to `escalate` on that
evidence rather than counted as regressions.

That is now three labels corrected by reading the corpus instead of trusting the eval set. The pattern
each time: the manual discusses a subject at length and never states the number, and a relevance
score cannot tell the difference.

`bj30-17` is a compound question — the manual does answer its "can I" half. Routing acts on the whole
turn, so that nuance is lost; recorded in D22, not solved.

### Cost

Every question now pays a grader call. End to end: 2,805 and 2,494 ms before, 3,323 and 4,189 ms
after — about **+1.1 s**, with enough run-to-run variance that it should be read as "about a second".
It lands before the first token, so the user feels all of it. Accepted.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python playground/check_grader.py
uv run --project backend --locked --no-sync python playground/check_quote_gate.py
uv run --project backend --locked --no-sync python eval/run.py
```

### Observed

| | before | after |
|---|---|---|
| Routing accuracy | 92% (54/59) | **97% (57/59)**, twice |
| `escalate` | 7/10 | **12/12** |
| X55 "what torque for the wheel nuts" | `manual`, a fabricated figure | **`escalate`, with the reason** |
| BJ30 "wheel nut torque specification" | `manual`, 110±10 N·m | unchanged |
| Questions graded | 16/59 | 59/59 |
| End to end | ~2.6 s | ~3.8 s |

### Checkpoint

- [x] A specification question the manual cannot answer hands off instead of inventing a number.
- [x] The same question against the manual that *does* state it still answers, with the figure.
- [x] The override cannot fire on a procedure, where an absent quote would prove nothing.
- [x] The operator is told *which* rule fired, including this one.
- [x] Measured twice; both runs 97% with the same two misroutes.
- [ ] `bj30-23` — table serialisation (D16), unchanged and open.
- [ ] `bj30-02` — flips near the band between runs. Grader instability, unchanged.
- [ ] Compound questions are routed whole, so "can I, and how deep" loses its answerable half.
- [ ] D4's context sentence — still the fix for `x55-08`'s retrieval, still `(not built)`.
- [ ] Operator inbox — next.

---

## Slice 15 — the operator inbox

### Outcome

`/inbox` renders the handoffs the backend has been writing since Slice 10. The escalation story can now
be shown end to end: a question the gate will not answer, the reference the user is given, and the
package a person picks up. Nothing on the screen is new backend work — all three endpoints already
existed and are unchanged.

### One app, not two

`AGENTS.md` rules out authentication, so a separate operator deployment would be a boundary with no
check behind it. It would also duplicate `config.ts` and `API_BASE`, and double the frontend
verification pass for the same demo. The deciding argument is the demo itself: following a reference
from the chat into the operator view in one browser is the moment that sells the handoff, and two
processes on two ports is a thing to fail live. Reasoning in D23.

### What makes the screen worth showing

Two things that only became true in the last two slices. `escalation_trigger` names *which* of D14's
rules fired, so the reason reads "The manual covers this subject but does not state the value asked
for" rather than one constant for every handoff. And `get_escalation` already returned the whole
transcript, which is D14's actual promise — a human never makes the user start again.

The transcript is rendered through the chat's own `MessageItem`. `StoredMessage` maps onto `Message`
by supplying `steps: []`. The saving in code is minor; what matters is that the operator sees the
conversation **exactly as the user saw it**, source badges included, so "this answer was not from your
manual" is visible on the screen rather than described in prose.

### The linter caught a real bug, not a style point

ESLint rejected a `loading` flag set synchronously in an effect body
(`react-hooks/set-state-in-effect`). Deriving it from a `loadedId` removed the cascading render and,
in doing so, exposed a race the first version already had: a slow response for an earlier selection
could land last and overwrite a newer one. The rewrite carries a `cancelled` guard.

### A type that agreed with itself and not with the payload

`EscalationPackage.session` was typed as `SessionSummary`, which carries a `messages` count.
`get_escalation` returns the raw `sessions` row and has no such field — the count exists only in
`list_sessions`. `tsc` cannot catch a wire format that lies, so the record was read out of SQLite and
the type narrowed to what is actually sent. Same class of error as the doc claims corrected earlier in
this log: a description that was true once, of something else.

### Commands

```bash
npm exec tsc -b --pretty false
npm run lint
npm run build
```

### Observed

| | |
|---|---|
| Routes | `/` and `/inbox`, both static |
| tsc, ESLint, production build | clean |
| Backend changes | none — the endpoints already existed |
| Escalations in the store | 1, from an earlier session |

### Checkpoint

- [x] `/inbox` lists handoffs, newest first, with the rule that fired.
- [x] Opening one shows the question, the reason, the pages already shown and the whole transcript.
- [x] The transcript renders as the user saw it, source badges included.
- [x] Read-only: status is shown, never changed.
- [x] `?id=ESC-XXXXXX` opens straight to a reference.
- [ ] **Not yet walked in a browser.** tsc, lint and build pass and the payload shapes were checked
      against a real record, but nobody has clicked it.
- [ ] The reference inside a chat message is not a link. That is the strongest demo path and it needs
      `message-item.tsx`, which this slice deliberately left alone.
- [ ] Only one escalation exists locally, carrying the old generic reason. The per-rule reasons appear
      on handoffs created from here on.

---

## Slice 16 — the handoff becomes a conversation

### Outcome

An escalation now carries a written summary of what the user was struggling with, an agent replies to
it from `/inbox`, and the reply lands in the user's chat badged as a person. The user can answer back,
and **no pipeline step runs for that session while a human has it**. Both sides update without a
refresh.

### It supersedes a decision rather than contradicting one

D12 said escalation was "a minimal inbox, not a live-chat integration", and put agent-side UI "well
beyond this scope". That was right when there was no inbox. D24 replaces it and D12 keeps its place in
the log with a pointer, because a decision doc that quietly stops being true is the failure `AGENTS.md`
rule 5 exists to prevent.

Two of the four pieces were never new scope. D14 fixed the payload as "reference, **issue summary**,
... trigger reason, **suggested next step**, and the full transcript", and neither had been built.

### The summary is worth the call, and the call is free

An escalating turn writes no answer — `AnswerStep` returns on that route — so the summary replaces the
answer call instead of adding one. What it produces is the point:

> The user is trying to find the correct torque specification for tightening wheel nuts on their
> vehicle. They have consulted the vehicle owner manual, but it does not provide the specific torque
> value they are asking for. They are currently stuck because the manual lacks the exact wheel-nut
> tightening torque.

That is what an agent needs before saying anything. It is labelled **Issue summary** above the real
transcript and never rendered as the user's own words — attributing generated text to a customer is
the mislabelling D13 exists to prevent, and an agent acting on a fabricated quote is a real harm.

### Polling, and why not SSE

The transport question was asked directly and the answer was polling. The existing SSE is
request-scoped: the stream opens on `POST /chat` and ends with the answer. A live agent channel is a
persistent subscription waiting on another person's message, which needs a subscriber registry,
fan-out on write, disconnect detection, reconnect with `Last-Event-ID`, and heartbeats — all in
process memory, **all lost on a dev-server reload while connections stay open**. In a two-day window
ending in a live demo, that is the most likely thing to fail on stage. Polling is one `setInterval`
against `GET /sessions/{id}`, which already existed. Reasoning in D24.

### The rule the feature rests on

`open_escalation_for_session()` reads the `escalations` table rather than adding a flag to `sessions`,
so there is one source of truth about who has the conversation. `POST /chat` checks it, stores the
message, emits a single `handover` frame and returns. Verified directly: with an open escalation the
transcript grows and not one pipeline step is logged.

```
[user ] What torque do I tighten the wheel nuts to?
[bot  ] I do not want to guess at this one — it is a safety-critical question…
[AGENT] Hi, I can help with that. Which variant do you have?
[user ] the 1.5T one
[AGENT] Checked with the workshop: 110 N·m for your variant.
```

### The same trap, twice

`create_escalation` inserted positionally, so adding the two summary columns broke it — exactly what
`create_session` did in Slice 13 when the streak column arrived. Both now name their columns. Worth
recording as a pattern rather than two incidents: a positional `INSERT` in this codebase is a latent
break waiting on the next migration.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
npm exec tsc -b --pretty false && npm run lint && npm run build
```

### Observed

| | before | after |
|---|---|---|
| Handoff payload | reference, reason, pages, transcript | + issue summary, + suggested next step |
| Agent → user | nothing | `role="agent"` in the user's own session |
| User → agent | nothing | stored, pipeline suppressed |
| Model calls per escalating turn | grade (+ resolve) | unchanged — summary replaces answer |
| Routes | `/`, `/inbox` | unchanged |

### Checkpoint

- [x] The card carries a summary that describes the struggle, not the answer.
- [x] The summary is labelled as written for the agent, never as the user's words.
- [x] An agent reply reaches the user's chat, badged as a person.
- [x] A handed-over session runs no pipeline step; verified against the store.
- [x] Reopening a handed-over session keeps it handed over.
- [x] `tsc`, ESLint and the production build are clean.
- [ ] **Not walked in two browser windows yet.** Every layer is verified against the database and
      the build passes, but the live two-way loop has not been clicked.
- [ ] Handing a session back to the assistant is not built; a handed-over session stays with the human.
- [ ] The `suggested_next_step` wording drifts toward advice the transcript already rules out — it
      suggested checking the manual for a value the summary had just said is absent.
- [ ] No presence, routing, multiple agents or agent auth. Say so when demonstrating it.

---

## Slice 17 — deleting a conversation

### Outcome

A conversation can be removed from the sidebar, taking its messages and any handoff raised from it.
The store had accumulated **65 sessions** across demo runs with no way to clear one.

### Two things in the schema pushed back

`messages.session_id` and `escalations.session_id` both reference `sessions(id)`, foreign keys are
enforced in `connect()`, and neither declares `ON DELETE CASCADE`. Deleting the session row first
raises `IntegrityError` as soon as it has a message, so `delete_session()` goes messages → escalations
→ session in one connection.

The handoff goes with the conversation because `get_escalation` builds its package from
`list_messages(session_id)`. An escalation outliving its transcript is a card the operator cannot act
on — an empty package is worse than a missing one. Recorded in D25 with the cost: a user can delete a
conversation an agent is part-way through.

### A UI constraint worth noting

The history row was a single `<button>` wrapping the title, and a delete control cannot be nested
inside it — a button inside a button is invalid HTML and React warns about it. The row is now a `div`
holding the select button and a trash button, revealed on hover and focus. Clicking the trash arms
that row into a `Delete? Yes / No` state held in one piece of local state, so only one row is ever
armed and no browser modal appears.

### Where the view lands afterwards

Deleting the **open** conversation cannot leave a blank pane. `removeSession` re-reads the list and
moves to the most recently updated remaining session, or starts a fresh one on the same manual when
that was the last. `startSession` and `refreshSessions` already existed and do both halves.

### Verified against the constraint, not just the happy path

A throwaway session with two messages and an escalation deleted cleanly — `{'messages': 2,
'escalations': 1}` — with the session, its transcript and its handoff all gone afterwards and the
other sessions untouched. Wrong ordering would have raised rather than failed quietly, which is why
this was worth running before touching the UI.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
npm exec tsc -b --pretty false && npm run lint && npm run build
```

### Observed

| | |
|---|---|
| Sessions in the store | 65, none removable |
| `DELETE /sessions/{id}` | returns what it removed: messages and escalations |
| Retrieval, routing, gate | untouched — `eval/run.py` not affected |
| tsc, ESLint, production build | clean |

### Checkpoint

- [x] A conversation, its messages and its handoff are removed together.
- [x] Foreign-key order verified against a session that had both.
- [x] Deleting the open conversation moves to another rather than blanking.
- [x] Deleting the last one starts a fresh conversation on the same manual.
- [x] Two-step confirm, no browser dialog, only one row armed at a time.
- [ ] **Not clicked in a browser yet** — the backend path is verified against the store and the build
      passes, but the sidebar interaction has not been used.
- [ ] No undo and no soft delete (D25).
- [ ] An agent with that thread open sees their next poll 404; the hook swallows it and the view
      simply stops updating rather than saying the conversation is gone.

---

## Slice 18 — a conversation stops being treated as one long question about the vehicle

### Outcome

"What can you do" no longer hands the user to a human, "thanks" no longer invents a question and
answers it, and a greeting gets an introduction instead of a refusal. Routing **97% (59/61)** with
two new rows covering the behaviour.

### What was typed into the running demo

```
'what can you do'   score -4.10  ROUTE=escalate   domain=True  safety=True
'thanks!'           rewritten to "What should I do next after changing the flat tyre?"  ROUTE=manual
'Hi who are you'    score -8.27  ROUTE=decline    "That is outside what I can help with."
```

The reported symptom was the first. The second is worse and had not been noticed: the user typed
**"thanks!"** and the system answered a question they never asked, from the manual, with citations.

### The invented question was this log's own instruction

D20 says a rewrite that asks "what should I do next" without naming what is being done has failed.
That was the right correction for a follow-up that dropped its subject — Slice 12 measured it moving
the reported case from `escalate` to `manual`. It is the wrong instruction for a message with no
subject, because it is not asking anything. The prompt now decides **whether** something is being
asked before deciding **what**, and `carries_a_question` ends the turn when nothing is.

Worth stating plainly: a fix that measured well six slices ago caused a worse bug in a case its
measurements never covered. The eval set had no conversational turns in it at all.

### One field removed the escalation

The grader called "what can you do" `domain=True` and `safety=True`. The safety value came from the
passages retrieval happened to land on — "Parking brake:" — rather than from the question. But
`decide()` tests `question_is_about_the_domain` before the safety branch, so correcting that one
field was the entire fix. The wording keeps costs, where-to-obtain and who-to-contact in domain,
because `gen-02` and the decline rows turn on that same clause.

**That was the regression risk, and it held: `general` 4/4, `decline` 3/3.**

### A route that ends a turn before anything is searched

`acknowledge` is set by `resolve_query` and honoured by one-line guards in `retrieve`, `rerank` and
`gate`. `web_search` already guarded on the route and needed nothing, and `build_pipeline()` is
untouched. Measured on the turn itself:

```
'thanks!'   route=acknowledge   steps=['resolve_query', 'answer']
```

No search, no grader call, no answer call — the cheapest turn the system has.

### Two replies that a model never writes

Both are fixed strings. A model asked to describe its own capabilities invents some, and an assistant
overstating what it can do is exactly the unverifiable claim D13 exists to stop. The decline copy has
to serve a greeting, a question about the assistant and a genuinely off-topic question, so it leads
with what the assistant does and closes with the boundary.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
npm exec tsc -b --pretty false && npm run lint && npm run build
```

### Observed

| | before | after |
|---|---|---|
| "what can you do" | `escalate`, with a reference number | **`decline`**, with an introduction |
| "thanks!" | a fabricated question answered from the manual | **`acknowledge`**, nothing searched |
| "Hi who are you" | "That is outside what I can help with." | the same introduction |
| Routing accuracy | 97% (57/59) | **97% (59/61)** |
| `general` / `decline` | 4/4 · 2/2 | **4/4 · 3/3** |
| Conversational rows in the harness | 0 | 2 |

### Checkpoint

- [x] A question about the assistant routes to `decline`, never to a human.
- [x] A turn that asks nothing is acknowledged without searching, grading or answering.
- [x] "thanks" resets the escalation streak instead of reading as `unclear`.
- [x] Both replies are fixed strings, never model output.
- [x] The domain rewording left `general` and `decline` intact — the stated regression risk.
- [ ] `question_touches_a_safety_topic` still takes its value partly from the retrieved passages
      rather than the question. Masked here because the domain check runs first; it is the same
      field that flips between identical runs, and it belongs with the grader instability.
- [ ] A bare "hi" as the **first** message still reaches retrieval, because `resolve_query` only
      runs when there is history.
- [ ] `bj30-17` and `bj30-23` unchanged and open. The misroute set moved again between runs — every
      figure here is ±2 rows.

---

## Slice 19 — the harness measures the turns the demo actually receives

### Outcome

Thirteen labelled rows for greetings, acknowledgements and transcription noise, 61 → 74. Routing
falls **97% (59/61) → 93% (69/74)**, and the drop is the point: three of the five misroutes are new
rows exposing behaviour that was previously unmeasured. No code changed.

### Why the number going down is the deliverable

Two conversational rows were the entire coverage of a demo's most common input. That blind spot is
why D20, measured carefully in Slice 12, produced a worse bug six slices later and nothing caught it
until it was typed into a live browser. A harness that only asks about the vehicle cannot fail on a
greeting, so it reports 97% and says nothing useful.

It is also the gate on voice input. Transcription noise reaches `resolve_query` looking exactly like
the turns that broke routing on 2026-08-18.

### A bare "hi" is worse than the open item said

The previous checkpoint recorded that a first-turn greeting "still reaches retrieval". Measured, it
does more than that:

```
meta-03  'hi'       -0.40  HIGH    got manual    want acknowledge
meta-04  'hello?'   -8.70  grader  got decline   want acknowledge
```

`-0.40` is not a marginal score. It sits far **above** `GATE_HIGH` (`-4.10`) — near the top of the
range the whole corpus produces — so the cross-encoder judged some passage highly relevant to the
word "hi", and `decide()` correctly trusted it. **The first thing a client types in the demo gets
answered from the manual, confidently, with citations, to a question nobody asked.** That is the
D13 failure mode reached through a door D26 closed only for follow-ups.

`hello?` lands in the grader band and gets `decline` — wrong label, survivable reply.

### Noise breaks the gate, not retrieval

Each noise row is a degraded paraphrase of an existing row, reusing its `expected_pages`, so the
degradation is the only variable.

```
noisy   n=5  @1 100% @3 100% @5 100% @10 100%   MRR 1.000
```

Hybrid BM25 + dense with RRF handles `presure`, `refule`, `whel` and a stray `um ... uh` without
losing a single page — better than the clean corpus average (`@1 83%`, MRR 0.889). D3's argument for
hybrid retrieval holds up under exactly the input it was never tested on.

The gate does not:

```
noise-05  'wat torqe for the whel nuts'  -10.51  got manual+general  want manual
bj30-24   'What is the wheel nut torque specification?'    manual
```

Same page, ranked first, and the reranker scores it `-10.51` — below `GATE_LOW` (`-7.50`). Retrieval
found the answer; the cross-encoder would not vouch for it against the misspelled query, so the route
fell through to `manual+general`, which until now had **zero** labelled rows. A safety value the
manual answers gets padded with web search because the question was typed badly.

### The new rows are stable; the old instability is unchanged

Two consecutive runs, same corpus, same rows:

| | run 1 | run 2 |
|---|---|---|
| `meta-03`, `meta-04`, `noise-05` | identical scores, identical routes | identical scores, identical routes |
| the fifth misroute | `bj30-17` | `esc-02` |
| routing accuracy | 93% (69/74) | 93% (69/74) |

The three new failures are deterministic, not wobble — they are bugs, and re-running will not make
them go away. The ±2 movement stays confined to genuinely ambiguous safety rows, which is consistent
with `question_touches_a_safety_topic` being the unstable field.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py   # run twice
```

### Observed

| | before | after |
|---|---|---|
| Rows | 61 | **74** |
| Conversational rows | 2 | **10** |
| Transcription-noise rows | 0 | **5** |
| Routing accuracy | 97% (59/61) | **93% (69/74)** |
| `acknowledge` | 1/1 | **5/7** |
| `decline` | 3/3 | **5/5** |
| `manual` | — | **44/46** |
| Recall@1, noisy input | not measured | **100%, MRR 1.000** |
| `manual+general` rows ever produced | 0 | **1** |

### Checkpoint

- [x] Greetings, acknowledgements and typos are labelled and scored.
- [x] Noise rows reuse a base row's expected pages, so retrieval and gate effects are separable.
- [x] Two runs agree on every new row.
- [x] The first-turn greeting gap is now a measured failure with a score, not a note in a checkpoint.
- [ ] **`meta-03` is the highest-priority open bug in the system.** "hi" scoring `-0.40` means the
      fix is not only running `resolve_query` on the first turn — it is that a content-free query can
      score at the top of the band at all.
- [ ] `noise-05` — the gate distrusts a correctly retrieved safety value when the query is misspelled.
      Voice input will produce this input shape constantly.
- [ ] No coverage of politeness wrapped around a real question ("hi, how do I change a flat tyre?").
      Deliberately excluded from this slice; it is the direction where a wrong `acknowledge` swallows
      a genuine question.
- [ ] `bj30-23` unchanged and open. `bj30-17` and `esc-02` alternate between runs.

---

## Slice 20 — every turn is read, not only the ones with history

### Outcome

A greeting as the opening message ends the turn without searching anything. Routing
**93% (69/74) → 95–96% (70–71/74)** over two runs, `acknowledge` **5/7 → 7/7**, and retrieval is
byte-identical. One model call moved from "follow-ups only" to "every turn".

### The reranker was right, which rules out both obvious fixes

`meta-03` scored `-0.40` and I assumed the reranker was inflating a degenerate query. It is not.
Probed directly:

```
'hi'        -0.40  p177  'HI: wipe steadily at high speed  LO: wipe steadily at low speed  AUTO: ...'
'thanks'    -1.18  p-2   'Thanks for your choice.........., 1 = 1. Preface......'
'asdfghjkl' -7.74        (table of contents)
'zzzz'      -7.82        (table of contents)
'the'       -4.95
```

**This manual documents a wiper speed setting named `HI`.** The cross-encoder scored a real lexical
match. Meaningless input already scores where it should, so there is nothing wrong with the scorer.

That kills the two fixes worth reaching for first. Raising `GATE_HIGH` above `-0.40` would strand
every genuine question. A greeting word list or a minimum query length would depend on *this*
corpus — the document-agnostic rule — and would still miss `thanks` at `-1.18`.

### The check was behind the wrong condition

Whether a message asks anything is a property of the message. `resolve.py` decided it only when there
was history, so `carries_a_question` was never evaluated on turn one and `acknowledge` was
unreachable there. The prompt already handled it — it names "a bare greeting" as not asking anything,
and `read()` already renders empty history as `(none)`. **No prompt change was needed.**

The rewrite genuinely does need history and stayed behind it. Leaving `ctx.query` unset on a first
turn lets `RetrieveStep` fall back to the raw question, which is what kept retrieval identical.

### Two content-filter failures, found by running the thing

Exposing the resolve call to first-turn input broke it in a way the plan half-predicted:

```
x55-12  'How deep can I drive through water?'
        → 400 BadRequestError before the model runs, self_harm: medium

bj30-08 'The battery is dead. How do I jump start it from another car?'
        → 200, finish_reason=content_filter   (intermittent: 3/3 once, 0/1 later)
```

The first is a **prompt**-side rejection and the second a **response**-side one; they raise different
exception types and the first fix caught only the second, which is how the eval found it. Swept all
74 rows: 1 trips the prompt filter. `complete_or_none` returns `None` for both and **re-raises any
other `BadRequestError`**, so a real fault is still a fault. The fallback is the old code path — the
turn carries on unread, exactly as every first turn did before this slice.

### Two runs, and what moved between them

```
run 1   95% (70/74)   esc-02      bj30-23  meta-06  noise-05
run 2   96% (71/74)   bj30-17     bj30-23           noise-05
```

`bj30-23` and `noise-05` fail in both — real and open. The rest is the known wobble, now with one
addition: **`meta-06` "Hi who are you" is a greeting *and* a question, and the classifier splits on
it — 4 `True` / 2 `False` over 6 runs at temperature 0.** `hi` and `hello?` are 6/6 stable. That flap
is new exposure from this slice and is logged, not fixed.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py   # run twice
```

### Observed

| | before | after |
|---|---|---|
| `'hi'` as the opening message | `manual`, answered with citations | **`acknowledge`, nothing searched** |
| Routing accuracy | 93% (69/74) | **95–96% (70–71/74)** |
| `acknowledge` | 5/7 | **7/7** |
| `decline` | 5/5 | 5/5 · 4/5 (`meta-06` flaps) |
| `manual` | 44/46 | **44/46 — unchanged** |
| Recall@1 / MRR, reranked | 83% / 0.889 | **83% / 0.889 — identical** |
| First-turn model call | none | **+1592 ms median** |
| Eval end to end | 3.6 s/question | 4.9 s/question |
| Rows that crash on the content filter | 0 (call was skipped) | **0 (call degrades)** |

### Checkpoint

- [x] A greeting as the first message routes to `acknowledge` without searching, grading or answering.
- [x] Retrieval is byte-identical — the rewrite stayed behind the history check.
- [x] `manual` held at 44/46 across both runs, the stated regression risk.
- [x] Both content-filter failure modes degrade instead of raising; other 400s still raise.
- [ ] **`_ACKNOWLEDGED` is the wrong copy for a greeting.** "Glad that helped." is now what `hi` gets,
      and nothing helped yet. The route is right and the reply is not. One string, next slice.
- [ ] `meta-06` flaps 4:2 on `carries_a_question`. The prompt says "a bare greeting"; this is a
      greeting that also asks something.
- [ ] `answer.py`, `escalate.py` and `gate.py` still raise on a content filter trip. Unmeasured, and
      their exposure did not change here — but `x55-12` proves the filter fires on this corpus.
- [ ] `bj30-23` and `noise-05` unchanged and open.

---

## Slice 21 — the opening greeting gets an introduction, not "Glad that helped"

### Outcome

The reply to a bare `hi` now says what the assistant does and invites a question. One file,
`answer.py`. No route, prompt or threshold changed.

### The bug D28 created

D28 got the route right and left the reply wrong:

```
'hi'  →  acknowledge  →  "Glad that helped. Ask me anything else about your manual whenever you need to."
```

Nothing had helped. The user had not asked for anything yet. And `decline`'s copy is no better on a
greeting — it closes with *"That particular question is outside what I can help with"*, answering a
question nobody asked. Two routes, neither with a sensible reply to the most common opening message
a demo receives.

### The signal was already on the context

Two different situations reach `acknowledge`: an opening greeting, and a "thanks" after being helped.
What separates them is whether anything came before — `ctx.history`, which D28 already keys the
rewrite on.

```python
reply = _ACKNOWLEDGED if ctx.history else _GREETING.format(domain=DOMAIN_DESCRIPTION)
```

`_WHAT_I_DO` is now shared between `_GREETING` and the `decline` copy rather than duplicated, so the
description of the assistant cannot drift between the two places it appears.

**No new route.** A third `Route` would have to be threaded through `decide()`, the guards in
`retrieve`, `rerank` and `gate`, and the frontend, to choose between two constants. **No model call**
— a model asked to greet someone invents capabilities, which is what D13 exists to stop.

### Commands

```bash
uv run --project backend --locked --no-sync ruff check .
```

**The eval was not run, deliberately.** This touches neither ingestion, retrieval, reranking nor the
gate, and `eval/run.py` never invokes `AnswerStep` — it scores routes and retrieval only. Running it
would burn ~6 minutes to reprint 96%.

### Observed

Rendered from the code, with `DOMAIN_DESCRIPTION="vehicle owner manuals"`:

| turn | before | after |
|---|---|---|
| `hi`, first message | "Glad that helped." | **"I answer questions about vehicle owner manuals… What would you like to know?"** |
| `thanks`, after help | "Glad that helped." | unchanged |
| off-topic question | "…outside what I can help with." | unchanged |

### Checkpoint

- [x] An opening greeting is introduced to rather than thanked.
- [x] Mid-conversation "thanks" is unchanged.
- [x] `decline` copy unchanged, and now shares one description of the assistant with the greeting.
- [x] Still two fixed strings; no model writes either.
- [ ] A greeting on turn 5 gets "Glad that helped", and a "thanks" as the opening message gets the
      introduction. Both are the wrong half of the pair and both are harmless. Telling them apart
      needs the classifier to report *which kind* of nothing was asked.
- [ ] Reply text is not scored by anything. The harness measures routes and retrieval; copy is
      verified by reading it.
