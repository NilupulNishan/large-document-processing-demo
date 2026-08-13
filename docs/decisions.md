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

---

## D10 — Reuse the existing frontend

**Decision.** Build on `automobile-rag-frontend` rather than starting a new UI.

**Why.** It already contains the four things this product needs: a PDF viewer (`react-pdf` +
`pdfjs-dist`), a resizable split pane, citation pills, and a chat surface. Rebuilding costs roughly a
day and produces nothing new. That day goes to retrieval quality and the eval harness instead.

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
cannot tell what is verified. So `source` is mandatory on every answer, citations are empty whenever
`source` is `general`, and the two render differently in the UI.

**Safety carve-out.** Brakes, airbags, restraints, towing and jacking are answered from the manual or
escalated — never from general knowledge. Improvising on these is the one place where a helpful
guess is worse than a handoff. Reversible if the client wants it otherwise.

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
