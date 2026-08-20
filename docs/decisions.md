# Decisions

Every non-obvious choice, with the reason. Add to this file rather than re-litigating in conversation.

---

## D1 — No agent framework (no LangGraph)

**Decision.** The pipeline is plain Python step classes assembled by `build_pipeline()`.

**Why.** After the routing redesign the flow is linear with one conditional branch; a state-machine
framework to manage one branch is overhead. The previous project ran two competing memory systems —
LangGraph's `MemorySaver` checkpointer *and* a separate session store — which was a direct source of
confusion. This project requires SQLite-persisted sessions with a history panel, so session state is
owned directly. Observed cost in the previous build was latency and reduced prompt control.

**Cost accepted.** No auto-generated graph diagram. Replaced by the mermaid diagram in
`docs/architecture.md`.

---

## D2 — Routing is deterministic, computed after retrieval

**Decision.** Every question goes to the retriever. Routing reads reranker scores. An LLM grader runs
only in the ambiguous score band.

**Why.** The previous build classified intent with an LLM *before* retrieving, then patched the
classifier's unreliability with substring keyword lists. Those lists matched `"eat"` inside *seat*,
`"rice"` inside *price*, and `"where is"` inside legitimate location questions. Ten of twelve
realistic owner questions were routed to "off-topic" and never reached the manual. Routing on
measured retrieval evidence makes that class of failure structurally impossible.

This is the Corrective RAG pattern, which the literature identifies as the most production-tested of
the agentic RAG family. The recommended adoption order is CRAG → Adaptive → Self-RAG. We stop at CRAG.

**Which score the gate reads is not a detail.** It reads cross-encoder output. Fusion scores look
like a relevance signal and are not one — see the measurement in D3. Building the gate before the
reranker exists would reproduce the previous project's failure in a new form: a routing decision made
on a number that does not mean what it appears to mean.

---

## D3 — Hybrid retrieval with RRF, then a cross-encoder reranker

**Decision.** BM25 + dense in parallel, fused with RRF at k=60, top-100 → rerank top-30 → best 6.

**Why.** Published benchmarks show hybrid + RRF lifting recall 0.72 → 0.91 and precision 0.68 → 0.87
over dense-only. Adding a cross-encoder gives a further +17.2pp MRR@3 and +12.1pp Recall@5. Manuals
depend on exact tokens — fault codes, torque values, fuse numbers, warning-light names — which
dense-only retrieval misses; the previous build was dense-only with no reranking.

RRF fuses on rank position rather than score, so incompatible score scales need no normalisation, and
k=60 is the value that generalised across TREC collections and is now the default in Elasticsearch,
OpenSearch, Azure AI Search and Weaviate.

**On CPU cost.** The reranker adds roughly 300 ms against an answer call of 2–5 s — about 7% of total
latency. Use `bge-reranker-base` or a MiniLM cross-encoder via ONNX with `use_fp16=False`.

**Measured — the cross-encoder is required for the gate, not an accuracy bonus.** This decision
presented reranking as a recall improvement worth 300 ms. Slice 4 shows it is load-bearing for D2.

RRF scores rank *position*, not relevance. A chunk ranked first by both retrievers scores
`1/(60+1) × 2 = 0.0328` whatever it actually says, and something is always ranked first. Measured
across the eval set: grounded questions score 0.0302–0.0328, while *"write me a poem about the sea"*
scores 0.0323 and *"where is my nearest service centre"* scores 0.0296. Two of six questions the
manual cannot answer land inside the grounded range. No threshold on this number can separate them,
so a gate reading fusion scores would route a poem request to the manual.

A cross-encoder scores the query and passage together and returns a genuine relevance judgement, so
the gate reads **reranker output only**. Fusion scores order candidates; they never decide a route.
Numbers in `docs/build-log.md`, Slice 4.

---

## D4 — Docling's HybridChunker, not semantic chunking

**Decision.** Docling `DocumentConverter` → `HybridChunker`, with the heading path prefixed onto each
chunk's text before embedding.

**Why.** A February 2026 benchmark of seven strategies ranked recursive 512-token splitting first at
69% accuracy; semantic chunking came last at 54% while running ~14× slower. `HybridChunker` is both
structure-aware and tokenizer-aware — it splits on real document structure, then splits over-long
chunks and merges under-sized ones to fit the embedding model.

The heading prefix is a free approximation of Anthropic's Contextual Retrieval, which cut top-20
retrieval failure from 5.7% to 3.7% by giving each chunk its surrounding context. A chunk reading
*"Press and hold for 3 seconds"* is unfindable without it.

**Corrected after measurement.** Docling headings are present on 100% of chunks but are single-level,
not a path — so they disambiguate far less than assumed here. The LLM-written context sentence below
is load-bearing, not a supplement to it. Numbers in `docs/build-log.md`, Slice 0.

The previous build lost structure entirely: it emitted one Document per page, so hierarchical
chunking could never span a section, and no heading metadata was retained.

**Promoted from deferred.** The context sentence is in v1 rather than held back. It is a one-time
offline pass with zero runtime latency, which makes it the cheapest accuracy gain available under a
"fast at query time" requirement.

Indexing therefore writes two things onto each chunk before embedding: the Docling heading path, and
an LLM-written context sentence. The eval harness measures each separately so we know what each is
worth.

**Corrected on cost — the context window is the chunk's neighbours, not the whole document.**
"Cost is no longer a constraint" was asserted here without arithmetic. Measured: the corpus is
170,559 tokens across 475 chunks, so sending the whole manual with every chunk is 40.7M input tokens
— about **$8.13** on nano uncached, against the **$0.21** D15 records for this same pass. The two
numbers cannot both be right, and D15's is the one that assumed a window.

Each chunk therefore gets its heading, the manual title, and its immediate neighbours — roughly 2–3k
tokens per call, restoring the $0.21 figure. This targets the failure the technique exists to fix: a
chunk reading *"Press and hold for 3 seconds"* is unfindable because it lacks **local** context, not
because it lacks the whole book. Azure prompt caching could make the full-document variant affordable,
but that depends on cache-hit behaviour we would have to spend money to observe.

**Sequenced after a baseline.** The pass is built in Slice 5, not alongside the index. Measuring the
heading path and the context sentence separately — which this decision requires — needs an index
carrying neither to measure against.

---

## D5 — LanceDB for vectors, SQLite for application state

**Decision.** Two embedded stores. No database server.

**Why.** LanceDB runs embedded like SQLite, holds dense vectors and full-text in one place — which is
what makes hybrid search available without a second service — and indexes from disk rather than
requiring the index in RAM. SQLite owns sessions, messages, manuals and escalations; it survives
concurrent tabs, which flat JSON files do not.

---

## D6 — Page offset is detected per manual and both numbers are stored

**Decision.** Store `page_pdf` and `page_printed` on every citation. Navigate by `page_pdf`, display
`page_printed`.

**Why.** Measured on the corpus: in the BJ30 manual the running header reads `Driving and Operation |
137` on PDF page 142 — a constant offset of 5, consistent across 258 of 283 pages with no
disagreement. The X55 manual uses a different template with no such header, and neither PDF carries
embedded bookmarks. Conflating the two numbers shows the user the wrong page, which is a demo-killer.
Because the offset differs per manual and per publisher, it is detected at ingest and stored, never
hardcoded.

---

## D7 — Query rewriting before retrieval on follow-up turns

**Decision.** Rewrite follow-ups into standalone questions, then concatenate the rewrite with the raw
question. Feed the last ~6 user turns; ignore assistant turns.

**Why.** Roughly 60% of follow-up messages contain unresolved coreferences — "how do I do that?", "it
still didn't work" — which retrieve badly as written. Concatenating the rewrite with the last-turn
query is reported to improve retrieval consistently across domains. Context contribution saturates
after 4–6 user turns, and assistant turns add negligible value, so a longer window costs tokens
without gain.

This is also what makes requirement 13 work: the rewriter *sees* history but is not forced to use it,
so an unrelated question in an old conversation is answered on its own merits.

---

## D8 — Escalation is multi-signal, not a confidence threshold

**Decision.** Escalate on any of: explicit request for a person; manual and web both weak; N
unresolved turns; safety-critical topic.

**Why.** Support-AI practice is consistent that a single tuned confidence number is unreliable for
generative systems. Production handoff designs combine explicit, evidence-based, loop-detection and
stake-based triggers. The handoff payload matters as much as the trigger: full transcript, what was
already attempted, pages shown, escalation reason, suggested next step.

---

## D9 — Stream over SSE, and stream the pipeline steps as well as the answer

**Superseded the original decision (plain request/response, no streaming).**

**Decision.** `POST /chat` returns a Server-Sent Events stream carrying two kinds of event: pipeline
step updates, then answer tokens.

```
event: step    {"step": "retrieve", "label": "Searching the manual"}
event: step    {"step": "retrieve", "label": "Found 6 passages in Maintenance > Tyres"}
event: step    {"step": "web",      "label": "Not in the manual - checking the web"}
event: token   {"text": "..."}
event: done    {"citations": [...], "source": "manual", "resolved": true}
```

**Why the reversal.** The original decision traded perceived speed for simplicity, on the assumption
that streaming needed extra infrastructure. It does not: FastAPI `StreamingResponse` gives SSE with no
broker, no WebSocket server and no new dependency, so the local-only constraint is untouched.

Two requirements now make it worth having. Responses must *feel* fast — and first-token latency, not
total latency, is what a user perceives; the answer call dominates the 3-6 s budget, so streaming
converts a long wait into an immediate one. And the product must *feel* agentic — which is achieved by
showing the work the pipeline is genuinely already doing, not by adding reasoning steps for show.

SSE rather than WebSocket: the stream is one-directional, so a WebSocket buys nothing and costs
connection management. The existing frontend's `useChatSocket` hook is adapted rather than reused.

**Rule.** Step events must describe work that actually happened. No invented stages, no artificial
delays. If a step is skipped, no event is emitted for it.

**Settled at build time: streaming and structured output are not in conflict.** The answer step needs
both — a schema, so `format`, `cited` and `resolved` come back typed, and token streaming, so the
prose appears immediately. `chat.completions.parse()` gives the first and blocks; the concern was that
having both meant two calls or giving one up.

Measured against `openai==3.0.0` rather than assumed: `chat.completions.stream()` accepts the same
`response_format` and emits the raw JSON token by token. `event.parsed` is no help — it populates a
field only once its string literal closes — but the raw deltas are usable. `complete_stream()` finds
the `"answer":"` marker in the accumulated buffer and runs `json.loads` on the partial value, which
unescapes `\n`, `\"` and `\uXXXX` for free and simply fails on a mid-escape buffer until the next
delta completes it. One call, typed result, streamed prose.

---

## D10 — Reuse the existing frontend

**Decision.** Build on `automobile-rag-frontend` rather than starting a new UI.

**Why.** It already contains a PDF viewer (`react-pdf` + `pdfjs-dist`), a resizable split pane,
citation pills, and a chat surface. Rebuilding those produces nothing new.

**The code lands in `frontend/` in this repo.** It is copied in and owned here, not referenced from a
sibling directory. A demo assembled from two disconnected repositories is a demo that does not run.

**Corrected after reading it — reuse saves about three-quarters of a day, not a day.** The
presentational shell transfers: `pdf-viewer.tsx`, `pdf-toolbar.tsx`, the resizable `container.tsx`
(which already wires a citation click to the viewer page), the message components and `chat-input`.

These do not transfer, and were counted as if they did:

- `useChatSocket.ts` is WebSocket, and D9 chose SSE. It also pulls step labels from a
  `/pipeline-status` endpoint, which contradicts D9's rule that events describe work that happened.
- `chat-api.ts` and `types/chat.ts` carry the previous project's contract — `mode`, `confidence`,
  `needs_followup`. Its `Source` is `{page, section}`; ours needs `page_pdf` **and** `page_printed`
  (D6), or the viewer opens the wrong page.
- Session history (requirement 6), the operator inbox (D12), and any visible distinction between
  manual-grounded and general answers are all absent. That last one is the guard in D13 and is the
  most consequential thing the UI does.

Also: `pdfjs` loads its worker from a CDN, which breaks the local-first constraint and must be
self-hosted.

Net: the frontend is 1.5–2 days, and must start before day 4.

**Outcome — reuse saved closer to a third of a day.** Revised twice downward, and the second revision
came from opening files that turned out to be empty. `ui/badge.tsx`, `ui/button.tsx`, `ui/card.tsx`,
`ui/loader.tsx`, `lib/utils.ts` and `lib/constants.ts` were all zero bytes, so the "small UI
primitives" counted as transferring did not exist. They were deleted rather than filled in; Tailwind
classes inline cover what they would have.

Two things genuinely transferred and were worth the copy: the markdown renderer (tables, lists, code
blocks, blockquotes) and the PDF toolbar's page navigation. Everything load-bearing was rewritten —
transport, page windowing, citations, the shell.

The estimate was wrong in a specific way worth naming: it was made from the file tree, not the file
contents. A directory listing looks like reuse. Two of the three revisions would have been unnecessary
had the files been read before the decision was written.

`pdfjs-dist` was also installed at the top level while `react-pdf` pins its own nested copy. The two
versions differed (5.4.296 against 5.7.284) and the viewer failed at runtime with an API/worker
mismatch. The worker is now resolved through `react-pdf` rather than from the hoisted package.

---

## D11 — A conversation is locked to one manual

**Decision.** `manual_id` lives on the session, not on the message. Reopening a conversation reopens
it on its original manual. Changing manual means starting a new conversation.

**Why.** Allowing a mid-conversation switch means history mixes two documents, and a follow-up like
"what about that step?" becomes ambiguous about which manual "that" referred to. Citations within one
conversation would point at different PDFs, so the viewer would swap document mid-scroll, and eval
rows would need to name a manual alongside expected pages. The cost of locking is one extra click for
the user. In practice a person owns one product and does not switch manuals mid-conversation.

---

## D12 — Escalation is a real record with a minimal inbox, not a live-chat integration

> **Superseded by D24 (Slice 16).** The inbox now carries a two-way conversation with a human agent.
> This entry stands as the record of the earlier position and why it was reasonable at the time.

**Decision.** Escalation writes a complete `escalations` row — full transcript, steps already tried,
pages shown, trigger reason, suggested next step. The user sees a confirmation with a reference
number. A small operator screen lists open handoffs and shows the full package for one.

**Why.** The client's helpdesk is unknown, so no integration target exists yet, and live agent
handoff — presence, routing, an agent-side UI — is a separate build well beyond this scope. Writing
a real record keeps the demo honest and makes the strongest moment in the pitch available: the client
sees the pre-filled ticket their team would receive. Going live later becomes one adapter pointed at
their helpdesk API rather than a redesign.

**Cost accepted.** Nothing is transmitted anywhere. This is stated plainly when demonstrating it.

---

## D13 — The assistant does not dead-end; it labels its source instead

**Decision.** A weak manual result changes the *source* of the answer, not whether the question gets
answered. Order of attempt: manual → manual plus general guidance → general expertise and web →
human. `decline` applies only when the question is not about the product at all. Every answer carries
a `source` field that the UI renders differently.

**Why.** The product is a technical expert sitting beside the user, not a manual search box. A user
whose fault is simply absent from the manual — and manuals omit a great deal — must still get help.
Refusing at that point is the behaviour that made the previous build feel useless, and it is a worse
failure than an imperfect answer, because the user is left with nothing.

**The risk this creates, and the guard.** If grounded and unguarded answers look the same, the user
cannot tell what is verified. So `source` is mandatory on every answer, and the two render
differently in the UI.

**Citations are typed, not merely present or absent.** The original rule — citations empty whenever
`source` is `general` — threw away provenance the system has. A web-sourced answer carries a URL, and
hiding it makes the answer *less* checkable than it needs to be.

| Type | Pill shows | Click | Emitted when |
|---|---|---|---|
| `page` | `p. 137` | jumps the PDF pane | the manual was used |
| `web` | the source domain | opens the URL | web search was used |

A `page` citation is never emitted for content the manual did not supply, and the PDF pane never
responds to a `web` citation. The two must be visually distinct — that difference is the guard, not
styling. If the pills look alike we have rebuilt the exact failure this decision exists to prevent.

**How the web query is built, recorded because two prior builds got it wrong.** Both earlier repos
failed at web search in the calling code, not in Tavily. One hardcoded a university domain allowlist
in a `.py` file and pasted `site:` operators into the query text — Tavily takes an `include_domains`
parameter and treats `site:` as ordinary words, so the operators became noise. The other sliced a
model name out of a filename, broke on `"x55"`, and searched for a car that does not exist. So here:
the query is the manual's **stored title** plus the question, domain restriction lives in `.env` as
`WEB_DOMAINS` and is passed as a parameter, and no confidence number is invented.

`WEB_DOMAINS` is empty by default, and deliberately. Measured: a restriction matching nothing returns
zero results silently, identically to a domain that does not exist — so a typo would disable web
search permanently and invisibly. The provider logs a warning when domains are set and nothing comes
back.

**Safety carve-out, defined in configuration rather than code.** Topics where a wrong answer can
injure someone are answered from the manual or escalated, never improvised from general knowledge.
Which topics those are is corpus knowledge, so it lives in `backend/.env` as `SAFETY_TOPICS`,
alongside the `DOMAIN_DESCRIPTION` that is already there. Code stays free of manual-specific strings,
and the client — who knows their own domain — owns the list.

**Rejected: deriving the list from the documents.** The first version of this decision named brakes,
airbags, restraints, towing and jacking directly, which violates the document-agnostic rule in
`AGENTS.md`. The replacement attempt was to detect hazards from the manuals' own markers, since both
use *Danger*, *Warning*, *Caution* and *Attention*. Measured, it carries no signal: mean marker
density across the top six passages is 23% for `safety` questions, 24% for ordinary `procedure`
questions, and 42% for *"write me a poem about the sea"* — which is simply the corpus base rate,
because roughly 30% of all chunks contain hazard language. Numbers in `docs/build-log.md`, Slice 5.

---

## D14 — Escalation fires on a counter, not on a model's judgement

**Decision.** Sessions carry an `unresolved_streak` integer. Escalation triggers on any of:

| Trigger | Mechanic |
|---|---|
| User asks for a person | matched in `resolve_query` |
| Nothing resolves it | `unresolved_streak >= 3` |
| Safety-critical topic, manual silent | gate rule (D13) |
| Manual weak **and** web weak | both retrieval paths returned nothing usable |

`unresolved_streak` increments when the answer was not grounded in the manual (`source: general`), or
when the user's message reads as a report that a previous suggestion failed. It resets to zero when
the user changes topic or confirms something worked. The "did that work?" reading happens inside
`resolve_query`, which already runs on every follow-up turn, so it costs no extra call.

**Why a counter.** Asking a model "should I escalate?" makes the most consequential decision in the
product non-reproducible and untestable. A counter can be asserted in the eval harness, replayed, and
tuned by changing one number. The threshold of 3 is a starting value, not a finding.

**The handoff payload** is the point of the feature, and is fixed: reference, issue summary, every
step already suggested with the user's report on each, pages already shown, trigger reason, suggested
next step, and the full transcript. A human must never have to ask the user to start again.

---

## D15 — `southeastasia`, `text-embedding-3-large`, and `gpt-5.4-nano` to start

**Region.** `southeastasia`. `centralindia` carries no Azure OpenAI models at all, so the resource
group's own region is irrelevant — a group is a logical container and can hold resources anywhere.
`southeastasia` offers the same model catalogue as `eastus` at roughly a quarter of the network
distance from Colombo, and the project's existing container registry and app services already sit
there.

**Embeddings: `text-embedding-3-large`.** Across the whole corpus the difference against
`-small` is under two cents — $0.023 versus $0.004. It is the cheapest quality improvement available
anywhere in this project, and it lands on retrieval, which D3 identifies as the weakest link. The
3072-dimension vectors cost nothing meaningful at roughly 400 chunks.

This is the one model choice that is **not** cheaply reversible. Changing it later invalidates every
stored vector and forces a full re-ingest, so it is decided before anything is embedded.

**Chat models: start with `gpt-5.4-nano` everywhere.** At $0.20/$1.25 per million it puts a
500-question demo at about $1.00 and the ingest-time contextual pass at $0.21.

Every chat model is a configuration value read through one settings module. Being wrong costs a
one-line edit and no re-ingest, which is why this decision is made cheaply and empirically rather
than argued in advance.

**Where it may need to change.** The answer step carries the most constraints of any call in the
system — choose a format, synthesise a diagnosis from six passages, emit exact citations, reproduce
safety warnings verbatim, and set `resolved`. Nano-class models are the weakest at holding several
instructions at once, and this is the only output a client ever sees. If the eval harness or a
manual walkthrough shows dropped warnings, wrong citations, or ignored formats, the escalation path
is `gpt-5.4-mini` at $3.00 per 500 questions, then `gpt-5.6-terra` at $9.50. Both are rounding errors
against the cost of a demo that does not land.

Numbers and re-verification commands in `docs/pricing.md`.

---

## D16 — Long chunks are reranked by their best window; tables keep Docling's default format

**Decision.** The cross-encoder scores every window of an oversized chunk and keeps the highest.
Table serialisation stays on Docling's default — markdown was built, measured and reverted.

**Why the windowing.** `RERANK_MAX_TOKENS` is 512 because that is the model's window, not a tuning
choice. Chunks are sized for the embedder's 8,191, so the two disagree by an order of magnitude and
the reranker silently read the first 512 tokens of everything. Measured: 11% of BJ30's tokens and 22%
of X55's were unreachable, and the chunk holding the towing capacity was read to 22% — the answer sat
at character 5,196 with the cut at 2,082. The reranker was scoring that chunk on engine cylinder
arrangement.

Rejected: raising the limit, which the model does not support; and shrinking chunks to 512 tokens,
which would triple the chunk count and split procedures across boundaries to fix a reranking problem.
Windowing costs about 31% more reranking latency and touches only the 6–9% of chunks that overflow.

**Why markdown tables were tried.** Docling's default `TripletTableSerializer` writes one sentence
per cell and repeats the row label in each:

```
Total mass of quasi-trailer (T), BJ6470X51MHEV = -.
Total mass of quasi-trailer (T), BJ6470X52MHEV = 1.5.
```

Windowing put that chunk back in the top 5 and the grader still reported that it does not answer the
question. It does; the answer is `1.5`. Markdown looked like the fix.

**Why it was reverted.** Measured against the same eval set with the grader at temperature 0:

| | markdown | triplet |
|---|---|---|
| Overall Recall@1 / MRR | 85% / 0.902 | 85% / 0.902 |
| `spec` Recall@1 / MRR | 71% / 0.821 | **86% / 0.893** |
| `procedure` Recall@1 / MRR | **86% / 0.906** | 82% / 0.883 |
| `bj30-02` engine oil quantities | `manual+general` | **`manual`** |
| `bj30-23` trailer weight | `escalate` | `escalate` |

It trades spec accuracy for procedure accuracy, and **the thing it was built to fix did not move** —
`bj30-23` grades identically under both. The triplet format's verbosity is not waste: every cell
self-describes, so a table split across chunks stays readable and every row carries its own label into
the retrieval index.

One real defect surfaced on the way and is worth keeping in mind if this is revisited: Docling pads
markdown rule rows to the column width, so a wide table's `|---|` line ran to 633 characters. The
reranker tokenises each dash separately, so the rule row alone exceeded the entire 512-token window
and no data row was ever read. That made the first markdown attempt score *worse* than the default.

**What was kept.** Conversion is the expensive half at ~10 minutes a manual, so `parse()` caches the
converted document under `data/parsed/` and re-chunking runs in seconds — 11.3 min to 6 s, measured.
That is what made a chunking experiment affordable enough to run and reject on evidence. `--reparse`
forces the models to run again.

---

## D17 — Model calls run at temperature 0, and the grader's fields say what they mean

**Decision.** `complete()` and `complete_stream()` default to `temperature=0.0`. The grader's system
prompt defines its two judgement fields explicitly.

**Why.** Both calls ran at the API default of 1.0. Measured over five identical runs of every question
that reaches the grader, **4 of 15 changed route between runs** — same question, same passages, same
index. D2 says routing is deterministic Python over model evidence; that holds only if the evidence is
stable. An eval harness over a component that disagrees with itself is not a test suite.

Temperature 0 alone took instability to 2/15. The remainder was ambiguity in the fields themselves:

- `question_is_about_the_domain` was read as *"do the passages cover it"*, so "how much does this car
  cost new" was judged off-domain and **declined** — the worst available outcome for a real question.
- `question_touches_a_safety_topic` fired on "where is my nearest service centre".

The fix names the distinction the eval rows actually show: a question touches a safety topic when it
asks for a **procedure, limit or specification** on a listed topic, and does not when it asks what
something costs, where to get it, who to contact, or whether an advisory exists.

**A first attempt made it worse and is recorded rather than hidden.** Wording it as "a commercial or
administrative question is not a safety topic" fixed two general-route questions and broke three
escalations — the model read any practical question as administrative. On a safety route a missed
escalation is worse than a spurious one, so that trade was rejected.

**Measured after.** Route instability **4/15 → 0/15**, and misroutes across the 52-row set **6 → 3**.
The three that remain are `bj30-23` and `bj30-02` — both table lookups, neither fixed by changing the
table format — and `esc-06`, which scores −2.07 and never reaches the grader at all.

---

## D18 — The gate judges the span its score came from, at the same character budget

**Decision.** `rank()` returns each passage's best-scoring window alongside its score. `RerankStep`
carries it as `excerpt`; `grade()` reads `excerpt[:600]` where it previously read `text[:600]`. The
answer step still reads the full `text`.

**Why.** D16 fixed the *reranker* so a long passage is scored by its best window rather than its first
512 tokens. The grader was left reading the first 600 characters. For the BJ30 towing chunk — 9,543
characters — those two spans describe different subjects: the score came from the window holding
`Total mass of quasi-trailer (T), BJ6470X52MHEV = 1.5` at character 5,202, while the grader was shown
wheel-alignment rows from character 0. The gate was therefore scoring one span and judging another.

**The full window was tried first and is worse.** Handing the grader the whole winning window (~10,000
characters across six passages instead of 3,600) flipped the one question the corpus genuinely cannot
answer — "what torque do I tighten the wheel nuts to?" on the X55, which contains no torque figure
anywhere — from `escalate` to `manual` in **5 of 5 runs**. More text reads as more coverage. Capping
at the original 600 characters keeps that question at `escalate` 5/5.

**Measured after.** Over five runs of seven decisive rows, `excerpt[:600]` against `text[:600]`:
identical on five, `bj30-02` steadier (4/5 → 5/5), `x55-08` wrong either way but failing to `escalate`
rather than `general`. **It did not change the misroute count.** It is kept because the gate now
judges the text its own score was measured on, and because the cost is zero — same budget, same
tokens — not because the numbers improved. `playground/check_evidence.py` reproduces the comparison.

---

## D19 — `esc-06` tested the opposite of its intent; the bypass, not the band, is the safety hole

**Decision.** `esc-06` now asks the X55 for a wheel nut torque. The BJ30 version of the question
became `bj30-24`, expecting `manual` on pages 245–247.

**Why.** `esc-06` was written to represent "a fastener torque the manual does not contain", and Slice
10 recorded that neither manual holds one. That is not true of the BJ30: it states **"all wheel nuts
are tightened to 110±10 N·m"** on printed pages 245–247, and it is the only torque figure in either
corpus. The row expected `escalate` from a manual that answers the question, so the gate routing it to
`manual` was correct and the label was wrong. The grader agrees the passages answer it, 5/5.

The X55 has no torque figure anywhere, so it carries the question the row was meant to ask.

**What that exposes.** The intended failure was never being measured. Asked of the X55, the question
scores **+3.29** — above `GATE_HIGH`, so no grader is called and it routes to `manual`. Graded, it
routes to `escalate` 5/5. The grader is right; it is simply never consulted.

**No threshold closes this.** Correct `manual` rows span −7.21 to +9.29, and this question sits at
+3.29 in the middle of them. `GATE_HIGH` cannot be raised past it without sending most of the corpus
to the grader. The cross-encoder measures whether the manual *discusses* a topic, not whether it
*states the value asked for*, and those come apart precisely on specification questions — the class
where a confident wrong answer does the most damage. Recalibrating the band, which Slice 10 proposed,
would not have worked. The remaining options are to call the grader on every question (+1.6 s on the
37 of 53 rows that currently bypass, and `x55-08` regresses) or to accept the gap. **Open.**

---

## D20 — A follow-up is rewritten before retrieval, and the rewrite must name its subject

**Decision.** `ResolveQueryStep` runs first. With no history it returns immediately — no model call,
no step event. With history it rewrites the turn into a standalone question from the last 6 **user**
turns and sets `ctx.query` to `f"{rewrite} {question}"`. Everything downstream reads `ctx.query`:
retrieval, the grader, and the answer.

**Why.** Every turn was being treated as the first. Reported from the browser: "how can I change flat
tire" answered correctly, then "I parked vechile whats now" retrieved as a standalone question, best
match "Displayed", nothing relevant. The grader truthfully reported that the passages did not answer
it, the subject read as a safety topic, and the gate escalated. The user got a handoff reference for a
question the manual answers two pages from where it had just been. **The gate was right; its input was
meaningless.**

**The grader and the answer read the rewrite too, not just retrieval.** Grading the raw turn would
have escalated it again for the same reason, and answering the raw turn produces a reply to "whats
now" with no subject. `RetrieveStep` already did `ctx.query = ctx.query or ctx.question`, so
`ctx.query` is always set by the time either runs.

**The first prompt failed, and how it failed is the point.** Asked only to make the question
standalone, the model returned *"I parked the vehicle—what should I do next?"* — fluent, self-
contained, and stripped of the subject. Retrieval had nothing to match and it escalated anyway; the
score moved −7.04 → −4.82 and the route did not change. The prompt now requires the rewrite to name
the task, taking it from the earlier turns, and says outright that "what should I do next" without
naming what is being done has failed. Same question: −7.04 → **−1.77**, route `manual`.

**Concatenated, not replaced.** The rewrite is a model's paraphrase; the user's own words are the ones
BM25 has term statistics for. Keeping both costs nothing and cannot lose a term the rewrite dropped.

**Measured.** Three of four follow-up pairs route correctly. `and how much do I need?` went `general`
→ `manual` (−8.43 → −5.05). The fourth is the X55 torque follow-up, which fails on D19's `GATE_HIGH`
bypass, not on the rewrite — it is the same open defect as `esc-06`, reached by a different path.

**Two limits, chosen and recorded.** The rewrite reads user turns only, so a reference to something
*the assistant* said — "the second one you mentioned" — cannot be resolved. And the 6-turn window has
no topic-boundary detection, so a subject change further back can still leak in. Neither is hit by the
reported transcript; the first is the more likely to be met in a demo.

**The answer step separately receives the previous assistant turn**, truncated, and it took three
attempts to make that safe rather than merely different.

1. Placed before the passages, it was ignored: the model replayed the procedure from "park on a firm,
   level surface" to someone who had just said they parked. The passage block is large and came last.
2. Moved after the passages and worded as "begin from the first step they have not yet done", it
   over-corrected into the **dangerous** direction — it announced "you're at the wheel change is done
   point" and gave post-change torque figures to a user who had not jacked the car or removed a wheel.
   On a procedure, replaying a step is an annoyance and skipping one is an injury.
3. Worded as "continue from the point they have actually told you they reached, and no further; never
   assume they have done anything they have not said they have done", it opens by acknowledging what
   they reported and carries on from there.

**Residual, and open.** The answer can only use the passages it is given, and "what should I do next"
retrieves the *tail* of a procedure. The reply therefore offers the closing branches — repair kit
versus wheel change — rather than the precise next step of jacking and removal. Better than the
escalation it replaced and better than a full replay, but it is not yet a procedure the assistant
walks someone through position by position. That needs retrieval to know where in a procedure the
question sits, which nothing in the pipeline models today.

---

## D21 — The escalation counter lives in Python and the session, never in a model

**Decision.** `sessions.unresolved_streak` is an integer. `resolve_query` reports two observations on
the call it already makes — `asks_for_a_person`, and `progress` as one of `reports_failure`,
`confirms_success`, `new_topic`, `unclear`. `next_streak()` turns the second into a count;
`decide()` reads the count. The API carries the value in and writes it back. Three of D14's four
triggers are now reachable; `escalation_trigger` records which one fired.

**Why here.** D14 says the counter exists so the most consequential decision in the product is
reproducible: a model asked "should I escalate?" cannot be replayed or asserted. Keeping the arithmetic
in `next_streak()` and the threshold in one config value means the eval harness can set a starting
streak on a row and assert the outcome, which is exactly how `esc-09` is tested.

**Persistence sits at the boundary, not in a step**, the same choice D20 made for `history`.
`ResolveQueryStep` adds to `ctx.unresolved_streak`; `api.py` writes it back only if it changed. A step
that opened SQLite could not be run by the harness, which has no sessions.

**The first version checked the streak after the score band, and was wrong.** The reasoning was that
if the manual confidently answers *this* turn, something did resolve it, so the streak should not
override. `esc-09` — "it is still not working", arriving with a streak of 2 — scored **+3.78** and
answered from the manual. But a streak only reaches the threshold through turns the user reported as
failures, or answers that were not grounded in their manual. A confident score on the next turn is the
fourth attempt at what has already failed three times, and the reranker matching "not working" against
some passage is not evidence to the contrary. Both new triggers are now checked **before** the band.

**The handoff resets the counter.** Left standing at 3, every later turn in the session would escalate
again, and the user would never get another answer.

**Reset on success or a change of subject** comes from the same field. Confirming something worked, or
moving to a new topic, sets the count to zero — measured working, along with the increment.

**What is still a model's word.** Whether a message *reports a failure* is a judgement, and a wrong
`reports_failure` inflates the count. The blast radius is bounded: it takes three to escalate, an
escalation is recoverable, and the threshold is one number. That is the trade D14 chose deliberately —
a model supplies evidence, Python counts and decides.

---

## D22 — The gate grades every question, and a missing value is checked, not judged

**Decision.** `GateStep` calls the grader on every question. Above `GATE_HIGH` the score still
decides, with one exception: where the question **asks for a specific value**, the subject **is a
safety topic**, and the grader **cannot quote that value from the passages it was shown**, the route
becomes `escalate`. `Verdict` gains `asks_for_a_specific_value: bool` and `answer_quote: str`, and
`quoted()` checks the quote really appears in the excerpts, ignoring whitespace and case.

**Why.** D19 left this open: the X55 scores **+3.29** for "what torque do I tighten the wheel nuts to?"
and contains no torque figure anywhere. Above the band no grader ran, so it answered from the manual
with page citations — the exact failure the product exists to prevent. No threshold closes it;
correct `manual` rows span −7.21 to +9.29 with that question at +3.29 among them.

**Three simpler policies were measured first and rejected**, over 3 runs of all 59 rows:

| policy | fully right |
|---|---|
| today (bypass intact) | 54/59 |
| grade everywhere, verdict decides outright | 46/59 |
| grade everywhere, the two booleans veto above the band | 51/59 |
| **grade everywhere, a value-scoped quote vetoes** | **57/59** |

The two middle rows fail for the same reason: the veto is the product of two unreliable booleans.
`question_touches_a_safety_topic` is true of most vehicle questions, and
`passages_answer_the_question` false-negatives often enough that together they escalate questions the
manual answers — `x55-16` (parking assist), and `fu-01`, the follow-up D20 had just fixed.

**Why a quote works where a judgement does not.** "Does this answer the question" is the model's
opinion and cannot be checked. "Copy the sentence stating the value" is an extraction, and Python can
verify the result against the passages. A fabricated or hedged quote fails a substring test, so the
routing depends on a fact rather than on trust — which serves D2 better than a boolean does.

**Scoping it to value questions is what makes it safe, and that took two attempts.** Requiring a quote
of *every* question broke procedures: a procedure has no single sentence carrying its answer, so an
absent quote proves nothing, and `fu-01` and `x55-16` escalated. Scoped to value questions it broke
nothing — but the first wording of `asks_for_a_specific_value` returned **False** for "what torque do
I tighten the wheel nuts to?" on 2 of 3 runs, because the model read it as *"do the passages contain
a value"*. That is the same confusion D17 had to fix for `question_is_about_the_domain`. Rewording it
to judge the question alone, and saying outright that it still requires a value when the passages are
silent, fixed it: `value=True` on all three runs.

**Two rows changed label rather than being counted as regressions, on corpus evidence.** `x55-12`
("how deep can I drive through water?") and `bj30-17` ("can I drive through water, and how deep?")
both expected `manual`. Neither manual states a fording depth: the X55's page 168 says *"correctly
estimate or find out the wading depth"* and gives no figure, and the BJ30 has a wading mode and depth
**detection** but no maximum. A confident depth here is how an engine gets flooded, so `escalate` is
the correct route and the labels were wrong — the same mistake `esc-06` carried, found the same way.
`bj30-17` is a compound question whose "can I" half the manual does answer; that nuance is lost by
routing the whole turn, and is recorded rather than resolved.

**Cost.** Every question now pays a grader call. End-to-end average across two runs each side:
2,805 and 2,494 ms before, 3,323 and 4,189 ms after — roughly **+1.1 s**, with enough variance between
runs that it should be read as "about a second", not a figure to quote. It lands before the answer
starts streaming, so a user feels all of it. Accepted for removing a class of confidently wrong safety
answers.

**Measured after, twice.** Routing **92% (54/59) → 97% (57/59)**, `escalate` **12/12** in both runs.
The two remaining misroutes are `bj30-02`, the flaky row near the band, and `bj30-23`, the table
serialisation D16 already ruled on. Neither is touched by this change.

---

## D23 — The operator inbox is a route in the same app, and read-only

**Decision.** `/inbox` in the existing Next.js app, not a second deployment. It lists handoffs and
opens one in full. Status is displayed and never changed, though `PATCH /escalations/{id}` exists.

**Why one app.** `AGENTS.md` rules out authentication and user accounts, so a separate operator
deployment guards nothing — it would be a boundary with no check behind it. `frontend/src/lib/config.ts`
is the only place settings are read, and a second app duplicates it along with `API_BASE`. One
`tsc` / `lint` / `build` pass stays one rather than two. And in a demo, following a reference from the
chat to the operator view in the same browser is the moment that sells the handoff; two processes on
two ports is a thing to fail live. D12 asks for an operator *screen*, not a system.

What belongs in the pitch instead of the build: in production this sits behind the client's own
helpdesk auth, or becomes a queue integration — which `AGENTS.md` lists as a non-goal.

**Why read-only.** The screen exists to show that the handoff carries everything a human needs. Adding
status controls makes it a workflow tool, which is a different product, and leaves a live demo in a
mutated state. The endpoint stays for whoever integrates a real helpdesk.

**The transcript is rendered by the chat's own `MessageItem`.** `StoredMessage` maps onto `Message`
with `steps: []` and nothing else missing. That is worth more than the code it saves: the operator sees
the conversation *exactly as the user saw it*, including the source badge on every answer, so "this
part came from the manual and this part did not" is visible rather than described. D13's whole point is
that the distinction is rendered, and it holds on this screen for free.

**A React rule caught a real bug.** ESLint's `react-hooks/set-state-in-effect` rejected a `loading`
flag set in the effect body. Deriving it from a `loadedId` instead removed the cascading render *and* a
race that was already there in the first version — a slow response for an earlier selection could land
last and overwrite a newer one. The fix carries a `cancelled` guard.

**One type was wrong and the payload proved it.** `EscalationPackage.session` was typed as
`SessionSummary`, which has a `messages` count. `get_escalation` returns the raw `sessions` row, which
has no such field — the count only exists in `list_sessions`. Checked against a real record rather
than assumed, and narrowed to what the endpoint actually sends.

---

## D24 — Live handoff to a human agent, superseding D12

**Decision.** An escalation carries a written summary of the user's struggle and a suggested first
step. An agent opens it in `/inbox` as a conversation and replies; the reply is written into the
user's own session as `role="agent"` and appears in their chat. The user can answer back. **While an
escalation on that session is not closed, `POST /chat` stores the message and runs no pipeline step
at all.** Both sides poll `GET /sessions/{id}` every two seconds.

**This supersedes D12**, which said escalation was "a minimal inbox, not a live-chat integration" and
placed agent-side UI "well beyond this scope". That was correct when no inbox existed. It is changed
deliberately rather than quietly contradicted, and D12 stands as the record of the earlier position.

**Two parts were never new scope.** D14 fixed the handoff payload as "reference, **issue summary**,
... trigger reason, **suggested next step**, and the full transcript". Both were unbuilt. This slice
builds them.

**No net model calls.** An escalating turn writes no answer — `AnswerStep` returns early on that
route — so the summary call replaces the answer call rather than adding one, and only on escalation.

**Polling, not SSE, and the reasoning matters more than the choice.** The existing SSE is
request-scoped: `POST /chat` opens a stream, a worker thread pushes into a `queue.Queue`, and the
stream ends with the answer. A live agent channel is a different lifecycle — a persistent
subscription waiting on someone else's message. That needs a per-session subscriber registry, fan-out
on write, disconnect detection or leaked queues, reconnect with `Last-Event-ID` or dropped messages,
and heartbeats. All of it lives in process memory and is **lost on a dev-server reload**, silently,
while connections stay open. `AGENTS.md` also rules out queues and workers. Polling is one
`setInterval` against an endpoint that already existed, holds no server state, and survives a reload.
Two seconds is well inside the time a person takes to type. If the transport itself ever becomes a
selling point, the upgrade is one hook and one endpoint.

**The summary is labelled, never presented as the user's words.** It appears as "Issue summary" above
the real transcript. Attributing generated text to the user is precisely the mislabelling D13 exists
to prevent, and an agent acting on a fabricated "quote" from a customer is a real harm, not a
cosmetic one.

**Handover is derived, not a second flag.** `open_escalation_for_session()` reads the `escalations`
table rather than adding a boolean to `sessions`, so there is one source of truth about whether a
person has the conversation. Reopening a session later re-derives it from the transcript.

**Still deliberately absent**, and to be said plainly when demonstrating it: no presence, no routing,
no multiple agents, no agent authentication, no typing indicators, no notifications, and nothing is
transmitted anywhere. One agent, one thread, local only. A handed-over session stays with the human;
handing it back to the assistant is not built.

**A trap this slice walked into and fixed.** `create_escalation` inserted positionally
(`INSERT INTO escalations VALUES (...)`), so adding the two summary columns broke it — the same trap
`create_session` had in D21. Both now name their columns.

---

## D25 — Deleting a conversation deletes its handoff with it

**Decision.** `DELETE /sessions/{id}` removes the session's messages, then its escalations, then the
session — in that order, in one connection. There is no soft delete and no undo.

**Why that order.** `messages.session_id` and `escalations.session_id` both reference `sessions(id)`,
`connect()` enables `PRAGMA foreign_keys = ON`, and neither declares `ON DELETE CASCADE`. Deleting the
session first raises `sqlite3.IntegrityError` the moment it has a single message. Ordering is the whole
implementation; getting it wrong fails loudly, which is the good case.

**Why the handoff goes too.** `get_escalation` builds its package from `list_messages(session_id)`, so
an escalation that outlives its transcript is a card an operator cannot act on — an empty package is a
worse outcome than a missing one, and it breaks the promise D14 exists to make. Keeping the record
would mean copying the transcript into the escalation at write time, which D12 explicitly decided
against. So the record is removed and the card disappears from `/inbox`.

**The cost, accepted.** A user can delete a conversation a human agent is part-way through answering.
For a demo that is the right trade — it is the user's own conversation. A product with real agents
would either block deletion while a handoff is open or archive instead, and that belongs with the
helpdesk integration `AGENTS.md` keeps out of scope.

**No undo.** A soft-delete flag would touch every session query for a feature whose only job is tidying
a demo. The confirm is a two-step in the sidebar rather than a browser dialog, which is protection
enough for the risk.

---

## D26 — A turn that asks nothing is answered without searching anything

**Decision.** `Rewrite` gains `carries_a_question`. When a follow-up asks nothing — "thanks", "ok",
"got it" — `ResolveQueryStep` sets `ctx.route = "acknowledge"` and the turn ends there.
`RetrieveStep`, `RerankStep` and `GateStep` return immediately when `ctx.route` is already set.
`AnswerStep` writes a fixed line, as it already does for `decline`. A question about the assistant
itself is now out of domain, and the `decline` copy introduces the assistant rather than only
refusing.

**Why.** Typed into the running demo: **"what can you do" was handed to a human as safety-critical**,
and **"thanks!" was rewritten into "What should I do next after changing the flat tyre?" and answered
from the manual** — a question the user never asked, answered confidently with citations.

**The invented question is D20's prompt working exactly as written.** It says a rewrite that asks
"what should I do next" without naming what is being done has failed. That was the right correction
for a follow-up that dropped its subject, and it is the wrong instruction for a message that has no
subject because it is not asking anything. The prompt now decides *whether* something is being asked
before deciding *what*.

**One field fixed the escalation.** The grader marked "what can you do" as `domain=True` and
`safety=True`. The safety value came from the passages retrieval happened to land on — "Parking
brake:" — not from the question. But `decide()` checks `question_is_about_the_domain` before the
safety branch, so making that field correct removes the escalation without touching anything else.
The wording keeps costs, where-to-obtain and who-to-contact in domain, because `gen-02` and the
`decline` rows depend on that clause.

**Both replies are fixed strings in Python.** A model asked to describe its own capabilities will
invent some, and an assistant overstating what it can do is the unverifiable claim D13 exists to
stop. The `decline` text serves a greeting, a question about the assistant and a genuinely off-topic
question, so it leads with what the assistant does and closes with the boundary.

**A new `Route`, not a new orchestrator.** `acknowledge` is set by a step and honoured by guards in
the three steps that would otherwise do work. `build_pipeline()` is untouched, as `AGENTS.md`
requires. The turn costs no search, no grader call and no answer call.

**Still open, and masked rather than fixed.** `question_touches_a_safety_topic` is influenced by the
retrieved passages instead of the question alone. Here the domain check runs first so it does not
matter, but it is the same field that flips between identical runs. It belongs with the grader
instability, which remains the largest open correctness risk.

---

## D27 — The eval set labels the behaviour we want, not the behaviour we have

**Decision.** `meta-03` ("hi") and `meta-04` ("hello?") are labelled `acknowledge` although no code
path can produce that route for a first turn — `ResolveQueryStep` returns early with no history, so
`carries_a_question` is never read. They fail, and the reported figure drops from 97% to 93%.
Transcription noise gets its own `kind`, `noisy`, and each noise row is a degraded paraphrase of an
existing row reusing that row's `expected_pages`.

**Why label a route the code cannot reach.** The alternative is labelling `meta-03` with whatever
production does today, which makes the row pass and deletes the defect from the report. A harness
that scores the current behaviour as correct by definition measures nothing. D26 already states the
rule — a turn that asks nothing is acknowledged — and `resolve.py`'s prompt names "a bare greeting"
as one such turn, so `acknowledge` is the specified behaviour and the row is a conformance test
against the spec, not against the implementation.

**It immediately paid for itself.** The open item said a first-turn greeting "still reaches
retrieval". The row shows "hi" scoring **-0.40**, far above `GATE_HIGH` (-4.10), routed to `manual` —
so the opening message of a demo is answered from the manual with citations. Running `resolve_query`
on the first turn would hide that; it would not explain why a content-free query outscores most of
the corpus.

**Why noise rows are paraphrases rather than new questions.** A new question needs its expected pages
established, which makes the row's own labelling a variable. Reusing `bj30-24`'s pages for
`noise-05` means any difference between them is the misspelling and nothing else. That isolation is
what made the finding readable: retrieval ranked the page first (`noisy` recall@1 100%, MRR 1.000)
while the reranker scored it -10.51 and the route fell to `manual+general`. **Noise degrades the
gate's confidence, not the retriever's ranking** — which is the opposite of what we assumed, and the
number the voice workstream needs.

**Cost accepted.** The headline figure is lower and cannot be compared directly to any number logged
before Slice 19. That is correct: the two figures measure different question sets, and the earlier
one was measuring a set the demo does not receive.

---

## D28 — Whether a turn asks anything is a property of the message, not of the conversation

**Decision.** `ResolveQueryStep` runs on every turn. The **rewrite** still requires history and stays
behind that check; a first turn is searched with the words the user typed. `read()` returns
`Rewrite | None`, and a turn Azure's content filter rejects carries on unread rather than raising.

**Why.** `meta-03` — a bare `hi` as the opening message — scored **-0.40**, far above `GATE_HIGH`
(-4.10), and was answered from the manual with citations. `decide()` was not wrong and neither was
the reranker: **this manual documents a wiper speed setting named `HI`** (p177, "HI: wipe steadily at
high speed"), so "hi" genuinely is relevant to that passage. `thanks` scores -1.18 against "Thanks
for your choice" in the preface.

**Two obvious fixes are both wrong, and measuring said so.** Raising `GATE_HIGH` cannot work: the
score is honest, and no threshold above -0.40 leaves any real question on the manual route. A
greeting word list or a minimum query length cannot work either — the collision is a property of
*this* corpus, which the document-agnostic rule forbids depending on, and a length rule would not
catch "thanks" or "ok that worked" anyway. Genuinely meaningless input already scores where it should
(`asdfghjkl` -7.74, `zzzz` -7.82), so there is nothing wrong with the scorer to fix.

The defect was that the pipeline asked "does this carry a question" only when there was a previous
turn. The prompt already answered it correctly with no history at all — it names "a bare greeting" as
not asking anything, and `read()` already renders empty history as `(none)`. **No prompt change was
needed; the check was simply behind the wrong condition.**

**The rewrite stays history-only, deliberately.** On a first turn the rewrite has nothing to resolve
against, and concatenating it would change the query for all 46 grounded rows. Leaving `ctx.query`
unset lets `RetrieveStep` fall back to the raw question, and retrieval came back **byte-identical** —
Recall@1 83%, MRR 0.889, unchanged. That is what kept the blast radius on the conversational rows.

**`complete_or_none`, because the filter has two failure modes and both are reachable.** Running the
step on every turn exposed the resolve call to input it had never seen. Azure rejects
`x55-12` — *"How deep can I drive through water?"* — with a **400 before the model runs**
(`self_harm: medium`), and separately returns **200 with `finish_reason=content_filter`** on the
jump-start question, intermittently. Uncaught, either one 500s the turn. The wrapper returns `None`
for both and re-raises any other `BadRequestError`, so a real fault is still a fault. Degrading to
"the turn was not read" is exactly the behaviour every first turn had before this decision, so the
fallback is the old code path rather than a new one.

**Cost accepted, measured.** A first turn gains one model call, median **1592 ms**. A greeting gets
*faster* — the call replaces retrieval, reranking and grading. End-to-end eval time went 3.6 s → 4.9 s
per question.

**Known unstable.** `Hi who are you` is a greeting *and* a question, and the classifier splits on it —
**4 `True` / 2 `False` over 6 runs at temperature 0**, so `meta-06` flaps between `decline` and
`acknowledge`. `hi` and `hello?` are 6/6 stable. Sharpening the prompt for the mixed case needs its
own before/after and is not done here.

---

## D29 — `acknowledge` has two replies, chosen on history

**Decision.** The `acknowledge` route writes `_GREETING` when `ctx.history` is empty and
`_ACKNOWLEDGED` otherwise. Both are fixed strings. `_WHAT_I_DO` is now shared between `_GREETING` and
the `decline` copy instead of being duplicated.

**Why.** D28 made a bare `hi` reach `acknowledge`, whose reply is *"Glad that helped."* — nothing had
helped yet, because the user had not asked for anything. The route was right and the reply was not.
`decline`'s copy is no better on an opening greeting: it ends *"That particular question is outside
what I can help with"*, which answers a question nobody asked.

The two situations that reach `acknowledge` are genuinely different — an opening greeting, and a
"thanks" or "ok" after being helped — and the thing that separates them is whether anything came
before. That is `ctx.history`, already on the context and already the signal D28 keys the rewrite on.

**Not a new route, and not a model call.** A third `Route` would have to be threaded through
`decide()`, the guards in `retrieve`, `rerank` and `gate`, and the frontend's route handling, to pick
between two constants. A model asked to greet someone would invent capabilities, which is the
unverifiable claim D13 exists to stop and the reason both strings are fixed in the first place (D26).

**A greeting mid-conversation gets "Glad that helped", and a "thanks" as the very first message gets
the introduction.** Both are the wrong half of the pair, both are harmless, and distinguishing them
needs the classifier to report *which kind* of nothing was asked — a prompt change measured against
an eval set that does not score reply text. Not worth it.

**Not measured by the harness, and it cannot be.** `eval/run.py` never invokes `AnswerStep`; it scores
routes and retrieval only. Nothing here touches ingestion, retrieval, reranking or the gate, so the
eval was not re-run — it would report identical numbers. Verified by rendering all three strings and
by walking it in the browser.

---

## D30 — A follow-up's rewrite is added to the question; a first turn's replaces it

**Decision.** `ctx.query = f"{standalone} {question}"` when there is history, `ctx.query = standalone`
when there is not.

**Why.** `noise-05` — `"wat torqe for the whel nuts"` — retrieved the right page **first** and was then
scored `-10.51` by the cross-encoder, below `GATE_LOW`, so a torque figure the manual states was
routed to `manual+general` and padded with a web search. Its clean twin `bj30-24` scores `-2.07`.
**Noise degrades the gate's confidence, not the retriever's ranking**, which is the opposite of what
we assumed: the `noisy` rows score Recall@1 100%, MRR 1.000, better than the clean corpus average.

The correction was already being computed and thrown away. Since D28 the resolve call runs on every
turn, so a cleaned-up form of a first-turn question exists before anything searches. D28 deliberately
did not use it — that was blast-radius containment for a slice about greetings, and this is the
measurement it deferred.

**Concatenation is right for a follow-up and wrong for a first turn, measured three ways:**

| row | raw | rewrite alone | rewrite + raw |
|---|---|---|---|
| `noise-05` | -10.51 below LOW | **-1.02 HIGH** | -4.30 mid |
| `noise-01` | -6.85 mid | **+3.19 HIGH** | -1.27 HIGH |
| `bj30-24` clean | -2.07 | **-2.07 identical** | -3.65 |
| `bj30-03` clean | -2.05 | -2.18 | **-3.93** |

D20 concatenates because an elliptical follow-up's rewrite *restores a missing subject* and the user's
own words still feed BM25. A first turn is already complete, so its rewrite *corrects* rather than
restores — keeping the original re-adds the very noise that was removed (`-4.30` against `-1.02`) and
penalises clean rows by duplicating them, pushing `bj30-03` to `-3.93` against a `-4.10` threshold.

**Cheap, because the call already happens.** No new model call, no new context field, no latency
change. For 41 of 62 first-turn rows the rewrite is byte-identical to the question.

**Cost accepted.** 18 of 62 first-turn rows change, most cosmetically. Two gain words that were not
there — `bj30-11` becomes "Where can I find the VIN **on this product**?" and `bj30-17` gains "is it
safe". Neither changed a route. Retrieval improved: Recall@1 **83% → 85%**, MRR **0.889 → 0.900**, and
the `safety` kind went **@1 80% → 100%**.

---

## D31 — `GATE_LOW` re-derived from the distribution D30 created, not tuned to rescue a row

**Decision.** `GATE_LOW` moves `-7.50 → -7.85`.

**Why.** D30 changed what a first turn is searched with, so it changed the score distribution the
bands were read off. `bj30-02` — *"What engine oil does it take and how many litres?"* — is the row the
original band was calibrated against: `config.py` recorded "grounded min -7.21… set outside those, not
on them", and `-7.50` was that value plus 0.29 of headroom. Its rewrite scores `-7.65` and consumed
the headroom, dropping it to `manual+general`.

**This is the rule being applied, not bent.** The grounded minimum moved `-7.21 → -7.65`; the band
moves with it and keeps the same kind of margin. The alternative — leaving `-7.50` — pins the band to
a number the distribution no longer contains, which is precisely what the original comment warns
against.

**It is not the same as tuning a threshold to fix "hi".** There the score was *honest and high*
(the manual documents a wiper setting named `HI`), so no threshold could separate it from a real
question and D28 rejected that fix. Here the distribution genuinely moved and the band is derived
from it.

**Measured margin, and why it is wider than it looks.** After D30, `bj30-02` at `-7.65` is the **only**
grounded row below `-7.50`. The next rows down are `esc-05` (-8.03), `dec-02` (-8.17) and `esc-03`
(-8.40), all ungrounded — and `GATE_LOW` cannot affect them, because it is only read when the grader
has already said the passages answer the question. `manual` went **44/46 → 45/46** and held there
across three runs.

**What this exposed, and it matters more than the fix.** Three runs of identical code returned
**99%, 95%, 95%**. Four rows flap between runs — `bj30-17`, `esc-02`, `meta-01`, `meta-06`. The
instability is ±3 rows, not the ±2 previously logged, and a single run cannot support a headline
number. Quote the range.

---

## D32 — "Grader instability" is four sources, and the obvious fix made routing worse

**Decision.** Keep a rebuilt stability census in `playground/`. Change no production code. The
prompt fix this slice was built to try was measured and **reverted**.

**Why the name was wrong.** Three runs of identical code returned 99%, 95%, 95%. Measured over 5 runs
× 74 rows, attributing each flip to the stage that produced it:

| source | evidence |
|---|---|
| the grader's booleans | 3/74 rows route-unstable with query, passages and score held fixed |
| the **turn classifier** | `meta-06` is unstable end to end but not in the grader pass |
| the **rewrite** | 8 rows produced more than one standalone question at temperature 0 |
| the **content filter** | trips intermittently on `bj30-17` and `bj30-08`, so `read()` sometimes returns `None` and the raw question is searched |

Only the first is the grader. The label had been carried since Slice 12 and pointed at the last model
call in the chain rather than at what was measured.

**`seed` is unavailable.** Eight runs with and without `seed`, on a row known to flip, gave identical
variance (`{True: 1, False: 7}` both ways) and `system_fingerprint` came back `None` — the deployment
ignores it. **Temperature-0 calls flip a boolean roughly 1 in 8 and there is no API setting that
stops it.** Majority-voting the grader would cut that, and is rejected: `AGENTS.md` caps query-time
model calls at the four the architecture documents, and three grader calls adds ~3 s to every
question.

**The fix that looked certain, and the numbers that killed it.** The prompt defines every `Verdict`
field except `passages_answer_the_question`, and two fields carry an explicit "read the question, not
the passages" instruction. Those two were the stable ones — `question_is_about_the_domain` flipped on
**0** rows, `asks_for_a_specific_value` on 1 — while `question_touches_a_safety_topic`, which carries
no such instruction, flipped on **9**. That is the hypothesis logged since Slice 18, with a control
group. Giving the safety field the same instruction did exactly what it was supposed to:

```
safety flips        9 rows -> 5        route-unstable rows   3/74 -> 2/74
passages_answer     4 rows -> 0        total field flips     14 -> 11
```

And routing got **worse**: headline 99/95/95 → 95/95/92, `escalate` 12/12→9/12 at worst,
`general` 4/4→3/4, and two rows that had never failed — `esc-03` and `x55-12` — began to.

**The lesson is the deliverable.** `bj30-17` did stabilise: stably `manual`, which is the wrong
answer. **A flapping error became a consistent one, and the stability metric scored that as
progress.** Stability is not correctness, the census measures only the former, and no stability
number may be used as a proxy for the latter. This is why the revert criteria were written before the
numbers were seen.

**Cost accepted.** The instability stands, now bounded and attributed rather than guessed at. The
next attempt has to be judged on `eval/run.py` across three runs, with the census as a secondary
signal only.

---

## D35 — Voice input writes into the box; it never sends

**Decision.** A mic control records the question, `POST /transcribe` returns the words, and the words
are appended to whatever is in the composer. The user reads them and presses send. Voice **output** —
read-aloud answers — stays a non-goal; `AGENTS.md` was narrowed from a blanket ban on "voice" to that.

**Why the transcript is not auto-sent.** `noise-05` measured a misspelled question retrieving the
right page first and then being scored `-10.51`, below the band, so a torque figure the manual states
was padded with a web search. D30 mitigates that and does not remove it. Auto-sending removes the
human check at exactly the point the input is least reliable, on a corpus where the answers are
torque figures and wading depths. Appending rather than replacing means dictation can add to a typed
question instead of destroying it.

**No new dependency.** Azure Speech's short-audio REST endpoint is one POST with two headers, so it
is written with stdlib `urllib.request` in `providers/azure_speech.py`. `httpx` is already installed
transitively by the `openai` SDK, but declaring it would still mean a lockfile change and an install
command; `AGENTS.md` asks for a local function when only a small one is needed.

**No audio through the pipeline.** The endpoint hands bytes to the provider on a worker thread and
returns a string. `resolve_query`, `decide()` and the gate never learn a question was spoken — voice
produces the same `question` string the chat box does, which is the property that keeps this small.

**The browser re-encodes to WAV, because the service decodes two formats and WebM is not one.**
The REST API for short audio documents exactly two: WAV/PCM 16 kHz mono, and OGG/OPUS. Every
Chromium browser records WebM and nothing else, so posting the recording as it came off the
microphone could never have worked.

**How that failure presents is the trap.** Audio the service cannot decode is not rejected — it
returns HTTP 200, `RecognitionStatus: Success`, `DisplayText: ""`, which is byte-for-byte what
silence returns. Measured against the live resource: a valid silent WAV, bytes labelled
`audio/webm`, and bytes labelled `audio/wav` that are not audio all answer identically. A wrong
`Content-Type` therefore looks exactly like a user who said nothing, and the first version of this
was shipped believing WebM was supported because that was written from memory rather than from the
specification.

So `lib/audio.ts` decodes whatever the browser recorded with `decodeAudioData`, resamples through an
`OfflineAudioContext` to 16 kHz mono, and encodes PCM WAV — no dependency. Two consequences worth
having: Safari works, because `decodeAudioData` reads the MP4/AAC it records, and the provider
**refuses** any `Content-Type` outside `audio/wav`/`audio/ogg` with a 415 rather than letting the
next such mistake hide as silence.

**Translation stays out** even though the resource offers it: multilingual responses are a non-goal.

---

## D36 — Live dictation streams to Azure from the browser, with the batch path kept as a fallback

**Decision.** The mic runs Azure's continuous recognition over a WebSocket opened **by the browser**,
authenticated with a ten-minute token from `GET /speech/token`. Interim results render below the
composer; only finalised phrases enter the textarea. If the stream cannot start, the turn falls back
to the recorded-then-posted path of D35. `microsoft-cognitiveservices-speech-sdk@1.51.0` (MIT) is
added, imported dynamically.

**Why the REST path cannot do it.** The documentation is explicit: *"The REST API for short audio
returns only final results. It doesn't provide partial results."* Words-as-you-speak is a different
API, not a parameter.

**The key never reaches the browser.** `AZURE_SPEECH_KEY` stays in `backend/.env`; the browser gets a
token from the documented `issueToken` exchange, scoped and expiring in ten minutes. Shipping the
subscription key to the client would have been the shortest path and is the one thing here that would
have been unrecoverable.

**Interim and final are different kinds of text, so they render differently.** `recognizing` fires
every few hundred ms and is *revised* — words change as context arrives. Written straight into the
textarea it rewrites itself mid-word and reads as a bug. So interim sits under the box, greyed and
italic, replaced wholesale on each event; `recognized` commits into the value. What the user edits and
sends is therefore always finalised text, never a half-formed guess.

**Still never auto-sent**, for the reason D35 gives: `noise-05` measured a misspelled question scoring
-10.51 and being padded with a web search, and on a corpus of torque figures the human check belongs
at the least reliable point in the chain.

**A new dependency, justified rather than assumed.** 7.2 MB unpacked and seven transitive packages is
not small. It is imported with `await import(...)` inside `start()`, so it is code-split: verified in
the production build that the 378 KB SDK chunk is absent from the page HTML and downloads only on the
first mic click. Hand-rolling Azure's WebSocket protocol — framed audio messages, `speech.hypothesis`
and `speech.phrase` handling — was the alternative and is not a sensible thing to own.

**The fallback is real, not decorative.** A client site that blocks outbound WebSockets would
otherwise lose the microphone entirely. `start()` tries streaming, and on any failure records with
`MediaRecorder` and posts to `/transcribe` instead, telling the user which mode it is in. Both paths
already existed, so this cost about fifteen lines.

**On the WebSocket non-goal.** `AGENTS.md` rules out WebSocket *transport*: this app runs no
WebSocket server, and `POST /chat` remains SSE and one-directional. The dictation socket is opened by
the browser directly to Azure — no audio and no socket touches this backend. Adjacent to the rule
rather than inside it, and taken as an explicit decision rather than an oversight.

---

## D37 — The UI follows Cloudscape's system, not AWS's identity

**Decision.** Open Sans on Cloudscape's type scale, tokens in Tailwind v4's `@theme`, four semantic
hues with exactly one meaning each, and a global header carrying the app's only `h1`.

**Why a reference at all.** The UI was Arial with ad-hoc sizes — `text-[15px]`, `text-[13px]`,
`text-[11px]`, `text-[10px]` plus five Tailwind steps — and no tokens anywhere. Every polish pass
meant editing every component.

**Why Cloudscape and not `aws.amazon.com`.** They are two design languages. The marketing site is
hero-led and sells; Cloudscape is what the AWS console runs on, is open source, and is documented
down to the numbers, so it could be read rather than guessed at. This app is a working tool with a
split pane, which is the problem Cloudscape is for. Body type moves 15px → **14px** as a result.

**Amazon Ember is not available.** Commissioned from Dalton Maag for Amazon's exclusive use and not
licensable by third parties, so it cannot ship in a client deliverable. Open Sans is what Cloudscape
itself specifies, and `next/font` self-hosts it at build — no CDN, consistent with the PDF worker
already being copied into `public/`.

**The identity is deliberately not taken.** No AWS orange, no console chrome. If the demo looks like
an AWS product the first question is whether it *is* one, which undermines the whole pitch.

**Four hues, one meaning each.** Blue is the primary action and the user's own voice; indigo is from
the manual; amber is not from the manual; green is a person being involved. Previously five hues
competed and green carried two jobs. Cloudscape's rule — blue only for the primary action, red and
green only for status, colour never the sole signal — is what makes provenance readable, and it is
also why the citation pills keep **solid versus dashed borders**: that distinction survives greyscale
and is D13 made visible.

**The header exists for a structural reason, not a decorative one.** The sidebar is `hidden lg:flex`,
so below 1024px the app had no navigation and no `h1` at all. The header carries both and survives
that width. On `/inbox` it reads "Agent portal" in green — green already means a person is involved,
so the operator side wears a colour the palette already owns rather than gaining a sixth.

**The manual appears twice, on purpose.** The header names the scope, the sidebar switches it. Both
read one selection in `container.tsx`. If they could disagree the screen would misreport which
document an answer came from, which is the single thing this product cannot get wrong.

---

## D38 — The transcript follows the reader, and a long answer is not a chat bubble

**Decision.** The message list follows a stream only while the reader is within 80px of the bottom; a
new message always re-pins; token growth scrolls with `auto` and a new message with `smooth`. Assistant
answers render full-width without a bubble; typed turns keep one. Citation pills are 32px.

**Why the scroll rule.** The old effect called `scrollIntoView({behavior:"smooth"})` on every change to
`messages`, and a streamed answer changes it on every token. Scrolling up to re-read pulled you back
within milliseconds. The fix has to distinguish two intents that look identical to the effect: *the
answer grew* (follow only if they were already following) and *I just asked something* (follow
regardless, because sending is a request to be at the bottom). Message count separates them.

**Easing differs by cause deliberately.** A smooth scroll retriggered every few milliseconds animates
against itself, so token growth jumps and only a new message animates.

**Freeing the reader creates a second problem**, so "Jump to latest" appears whenever they have
scrolled away while an answer is still arriving. Without it, the fix silently hides that the assistant
is mid-sentence.

**The scroll listener sets state only on change.** Setting it per event would re-render the whole
transcript on every scroll frame during streaming, which is a worse defect than the one being fixed.

**Why the assistant leaves the bubble.** Assistant turns carry full markdown — tables, code blocks,
ordered lists. `max-w-[85%]` inside a 55% pane is roughly 46% of the window, and `markdownComponents`
already needed `overflow-x-auto` on tables to survive it. A bubble is right for a typed sentence and
wrong for a document fragment. Typed turns keep theirs, which also keeps the human/assistant
distinction D24 depends on.

**On target size, correcting the audit that prompted this.** The audit called 24px pills "well under
the 44px floor". There is no 44px floor: WCAG 2.2 SC 2.5.8 Target Size (Minimum) is **AA at 24×24**,
and 44×44 is SC 2.5.5, **AAA**. The pills already met AA. 32px is chosen because it is the most
important click in the product and the density suits a three-pane tool — not to fix a violation that
did not exist.

---

## D39 — The composer computes one state, and the stop button really stops

**Decision.** `ChatInput` derives a single `status` from an ordered set of conditions, and both the
control and the line beneath it read from it. `ready` and `busy` arrive as separate props,
`useDictation` reports a `mode`, and `handedOver` is threaded through at last. The send button
becomes a stop button while answering, and `useChatStream` exposes `stop()`.

**Why one derived value.** The old composer read `disabled`, `dictation.state` and `dictation.error`
independently in three places — the button styling, the textarea, and the footer sentence. Nothing
stopped them disagreeing, and a control that says one thing while the line under it says another is
worse than either alone. One value, first match wins, both read it.

**Three inputs had to be repaired before any of that was expressible.**

- `chat-panel.tsx` passed `disabled={!ready || busy}`, collapsing "no manual selected" and "the
  assistant is answering" into one boolean. They are different states and now arrive separately.
- `useDictation` reported a fallback to recording only by putting a sentence in `error`, so the
  caller had to string-match an error message to know which path it was on. It now reports
  `mode: "live" | "recording" | null`.
- `handedOver` had been computed by `useChatStream` since Slice 16 and **consumed by nothing**, so
  nothing on screen said who the user was now talking to. It now marks the composer and names the
  recipient.

**The stop button is a real capability, not a redraw.** The artboard showed send becoming stop while
answering. `useChatStream` already held an `AbortController` and already finalised a part-written
message in its `catch`/`finally`; it simply never exposed a trigger. Shipping a button labelled stop
that did not stop would have been worse than shipping no button, so `stop()` is exported and wired.

**What it does not do:** it stops this client reading the stream and finalises the message. The
server-side pipeline is not cancelled. Saying so is better than implying the work halts.

**Send is disabled for the whole of listening**, not merely while an interim guess is outstanding as
first planned. Mid-dictation the instruction on screen is "press stop when you are done", and a send
that fires before that contradicts it. Stricter than the plan, and deliberately.

**The composer is NOT disabled during a handoff, and the first attempt at this was wrong.** State 9
was implemented as a hard lock, which broke a shipped feature: D24 made the handoff a two-way
conversation, and `api.py:186` stores the user's turn *before* the handover check precisely so the
agent can read it. "The assistant writes nothing" and "the user cannot write" are different claims,
and conflating them turned a conversation into a dead end. The handoff now shows as a green composer
border and a line naming who the reply reaches; the input stays fully usable.

**Starting dictation is a visible state, because it is slow.** D36's lazy import means the first
mic click waits on a token fetch, a 7 MB download and a socket. Leaving that looking idle invited a
second click, which opened a second recogniser on the same microphone and inserted every phrase
twice. `start()` is now idempotent, the wait is shown, and a live start that fails closes its
recogniser rather than leaving it connected beside the fallback recorder.

**Elapsed time is client-measured.** `Message.elapsedMs` is stamped in the browser and marked as such
in `types/chat.ts`, which otherwise mirrors the backend contract. A restored conversation has no
timing, so the collapsed trace reads `5 steps` rather than inventing a duration.

---

## D40 — The document pane says where you are, and the page a citation named announces itself

**Decision.** The PDF toolbar no longer shows the manual's title or page count — only `Page N of M`
and icon controls. When a citation changes the page, the page it lands on rings in indigo for about a
second.

**Why the title went.** With the global header (D37) naming the manual and its page count, the title
appeared three times on one screen: header, chat panel header, PDF toolbar. The pane a document is
already visible in does not need to be told which document it is; it needs to say *where in it you
are*. That removed `title` and `subtitle` from `PdfViewer` entirely.

**Why the page announces itself.** Clicking a citation is the interaction the whole product argument
rests on — "this answer came from *that* page". It previously changed the scroll position and nothing
else, so the two panes read as unrelated: an answer on the left, an unexplained jump on the right.
A one-second ring in the manual colour (`--color-manual`, the same hue the citation pill uses) makes
the right pane visibly answer the click.

**A lint rule is suppressed here, deliberately.** `react-hooks/set-state-in-effect` fires on the
effect that reacts to the `page` prop, because it moves the scroll position and marks the located
page — both state. Reacting to an external change with transient UI that decays on a timer is the
case that rule's own documentation carves out. The alternatives were a ref-and-DOM hack, or a token
prop that moves the same problem one level up. The suppression carries its reasoning in the code
rather than a bare disable comment.

Worth knowing for anyone who meets it: the rule traces *into* `jump()`, so the effect was always
setting state this way. Adding the ring is what made it visible to the linter, not what introduced it.
