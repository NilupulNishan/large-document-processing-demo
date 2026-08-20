# Manual Assist

A document-agnostic diagnostic assistant over large manuals. Select a manual, describe a problem,
get an answer in a format suited to the question with the cited page shown beside it. When the manual
cannot resolve it, the system searches the web if the question is in scope. When nothing resolves it,
it hands off to a human with full context.

Questions can be typed or dictated. Runs entirely locally; Azure OpenAI, Azure Speech and Tavily are
the only network calls.

## Documents

| File | What it holds |
|---|---|
| `docs/client-brief.md` | The problem, the user story, and the definition of done |
| `docs/architecture.md` | Boundaries, pipeline steps, data model |
| `docs/decisions.md` | Every non-obvious choice with its reason, plus open questions |
| `docs/azure-setup.md` | Provisioning the one cloud resource, and tearing it down |
| `docs/pricing.md` | What it costs, and the commands to re-check |
| `docs/build-log.md` | One entry per working slice |
| `AGENTS.md` | Boundaries, non-goals and policy for coding agents |

## Layout

Everything here exists. What is still unbuilt is named under Status below.

```
backend/          FastAPI app, pipeline steps, providers
  app/
    api.py        HTTP routes and SSE framing
    db.py         SQLite — manuals, sessions, messages
    pipeline/     resolve_query → retrieve → rerank → gate → web_search → answer → escalate
    providers/    Azure OpenAI, Azure Speech, LanceDB, Docling, Tavily — SDK types stop here
frontend/         Next.js UI: manual picker, chat, PDF pane, session history, operator inbox
  src/lib/        config.ts, api.ts and audio.ts — the only place the wire format is known
  src/types/      the backend contract, mirrored so a change there fails the type check
  src/hooks/      use-chat-stream.ts, use-polled-messages.ts, use-dictation.ts — the stateful pieces
  src/components/ chat/, pdf/, source/, inbox/, layout/ — presentational
eval/             questions.jsonl + run.py — the test suite for this project
playground/       Experiment scripts. Not application code.
scripts/          ingest.py, index.py and dev helpers
data/             Source manuals, LanceDB store, SQLite database (all gitignored)
```

## Running it

Once per machine, from the repo root:

```bash
cd backend && uv sync --locked && cd ..
```

Ingestion is offline and runs once per manual. Parsing is slow (~10 min); embedding is not, and the
two are separate on purpose so re-embedding never forces a re-parse.

```bash
uv run --project backend --locked --no-sync python scripts/ingest.py data/manuals/<file>.pdf
uv run --project backend --locked --no-sync python scripts/index.py data/chunks/<file>.jsonl
```

The title shows in the picker and rides into every web search query, so set it properly. PDF metadata
is no help — these manuals report `'6.24画册'` and `'前言'`.

```bash
uv run --project backend --locked --no-sync python scripts/index.py \
    data/chunks/<file>.jsonl --register-only --title "BAIC BJ30 / E30"
```

`data/` is derived state and gitignored. The same `--register-only` flag recovers the manual registry
if `data/app.db` is lost, without paying for another embedding run.

### The two halves, together

Two terminals. The API first — it loads the cross-encoder at startup, which takes a few seconds and
saves the first question from paying for it.

```bash
# terminal 1 — API on 8000
uv run --project backend --locked --no-sync uvicorn app.api:app --app-dir backend

# terminal 2 — UI on 3000
cd frontend && npm install && npm run dev
```

Then open `http://localhost:3000`, pick a manual, and ask something.

`npm install` runs `scripts/copy-pdf-worker.mjs`, which puts the PDF.js worker in `public/`. Nothing
loads from a CDN. If the viewer ever says *"Could not open this manual"*, check the browser console
for an API/worker version mismatch and re-run `node scripts/copy-pdf-worker.mjs`.

The UI reads `NEXT_PUBLIC_API_BASE_URL`, defaulting to `http://localhost:8000`.

Interactive API docs are at `http://127.0.0.1:8000/docs`. They can drive every endpoint, but Swagger
buffers the whole SSE stream and shows it at the end — use curl to watch `/chat` actually stream.

### Poking it by hand

```bash
# create a session on one manual — a conversation is locked to it (D11)
SID=$(curl -s -X POST http://127.0.0.1:8000/sessions \
  -H 'Content-Type: application/json' \
  -d '{"manual":"baic-bj30-e30-owner-manual-en"}' | python -c 'import sys,json;print(json.load(sys.stdin)["id"])')
echo "session $SID"

# ask something — frames arrive as the work happens
curl -N -X POST http://127.0.0.1:8000/chat \
  -H 'Content-Type: application/json' \
  -d "{\"session_id\":\"$SID\",\"question\":\"How do I change a flat tyre?\"}"

# read the conversation back, with citations
curl -s "http://127.0.0.1:8000/sessions/$SID" | python -m json.tool
```

`-N` matters. Without it curl buffers the response and everything appears at once, which looks
exactly like streaming being broken.

Questions that exercise each route:

| Ask | Expect |
|---|---|
| "How do I change a flat tyre?" | `source=manual`, page citations |
| "What engine oil does it take?" | `source=manual`, an oil grade and a volume |
| "What torque do I tighten the wheel nuts to?" (X55) | `escalate` — that manual states no torque |
| then "I parked it, what now?" | a `resolve_query` event, then `source=manual` — not a new topic |
| "What does the warranty cover?" | `source=general`, a `web` event, `[web]` citations |
| "Write me a poem about the sea" | `decline`, one short refusal, no answer call |
| "hi" as the opening message | `acknowledge` — nothing searched, graded or answered (D28) |
| the mic button, then talk | words appear as you speak and stay in the box; nothing is sent (D36) |

Two step events are worth watching. A `web` event appears only on the `general` route; on a
manual-answered question it means the gate misrouted. A `resolve_query` event appears on every turn,
but it says different things: "Read the conversation so far" on a follow-up, "Read the message" on a
first turn, where there is no history to rewrite against and only the question itself is read (D28).
The `gate` event now appears on every question: since D22 the grader runs each time,
because a high retrieval score means the manual discusses the subject, not that it states the number
asked for.

Safety-critical questions the manual does not cover route to `escalate`: the stream ends with an
`escalated` frame carrying a reference, and the handoff record holds the transcript, a written summary
of what the user was stuck on, and the rule that fired.

Open `/inbox` in a second window to see it from the other side. An agent replies there and the reply
appears in the user's chat within two seconds, badged as a person. **While a handoff is open that
session runs no pipeline step at all** — the assistant stays out of a conversation a human has taken
over (D24). Nothing is transmitted anywhere; there is no presence, routing, or agent authentication.

The scripted equivalent, with per-frame timing:

```bash
uv run --project backend --locked --no-sync python playground/check_api.py
```

## Verification

`eval/` is the test suite. There is no `tests/` directory, by decision.

```bash
uv run --project backend --locked --no-sync ruff check .
uv run --project backend --locked --no-sync python eval/run.py
```

The frontend has its own three:

```bash
cd frontend
npm exec tsc -b --pretty false
npm run lint
npm run build
```

## Status

Built: ingestion, embedding and indexing; the full
`resolve_query → retrieve → rerank → gate → web_search → answer → escalate` pipeline; SSE transport;
session persistence; the chat, PDF and operator inbox screens; voice input, live and streamed.

Not built: D14's fourth escalation trigger (manual weak **and** web weak), and D4's LLM-written
context sentence at ingest. `docs/architecture.md` marks each `(not built)` and is kept in step with
the code.

Three known gaps, all measured and recorded rather than hidden:

- D4's LLM-written context sentence is not built, and the row that justified it no longer
  demonstrates the problem. The X55 chunk explaining hill descent control never writes the words
  "hill descent" — only "HDC" — under the heading `Automatic release > HDC`, most of which is about
  the parking brake. That was expected to make it unfindable. Measured, it is not: fusion ranks it
  first, reranking third, and `x55-08` routes `manual` with correct citations. Dense retrieval
  bridges the acronym on its own. The chunk is still poorly labelled, so the concern is real for
  chunks nobody has queried — but it is no longer evidenced by this row, and D4 should be re-argued
  on measurement rather than on this example.
- Model calls are not deterministic even at temperature 0, and this deployment ignores the API's
  `seed` parameter, so a question sitting near a band routes differently between runs. Five rows are
  known to move. Three runs of identical code gave 99%, 95% and 95% — read every routing number as a
  range of ±3 rows, never as a single figure.
- `bj30-23` — the trailer weight sits in a table row the grader reads as not answering the question.
  Neither table serialisation fixed it (D16).
