# Manual Assist

A document-agnostic diagnostic assistant over large manuals. Select a manual, describe a problem,
get an answer in a format suited to the question with the cited page shown beside it. When the manual
cannot resolve it, the system searches the web if the question is in scope. When nothing resolves it,
it hands off to a human with full context.

Runs entirely locally. Azure OpenAI and Tavily are the only network calls.

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
    providers/    Azure, LanceDB, Docling, Tavily adapters — SDK types stop here
frontend/         Next.js UI: manual picker, chat, PDF pane, session history, operator inbox
  src/lib/        config.ts and api.ts — the only place the wire format is known
  src/types/      the backend contract, mirrored so a change there fails the type check
  src/hooks/      use-chat-stream.ts and use-polled-messages.ts — the stateful pieces
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
| "Write me a poem about the sea" | `decline`, one short refusal, no model call |

Two step events are worth watching. A `web` event appears only on the `general` route; on a
manual-answered question it means the gate misrouted. A `resolve_query` event appears only on a
follow-up turn — seeing one on the first question of a conversation is a bug, since there is no
history to read. The `gate` event now appears on every question: since D22 the grader runs each time,
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
session persistence; the chat and PDF screens.

Not built: D14's fourth escalation trigger (manual weak **and** web weak), and D4's LLM-written
context sentence at ingest. `docs/architecture.md` marks each `(not built)` and is kept in step with
the code.

Three known gaps, all measured and recorded rather than hidden:

- `x55-08` retrieves nothing that explains hill descent control: the chunk that does say only "HDC"
  and carries a meaningless heading. D4's context sentence is the fix, and is not built.
- The grader disagrees with itself on a minority of the rows it decides, so a question sitting near
  a band can route differently between runs. Every routing number here should be read as ±2 rows.
- `bj30-23` — the trailer weight sits in a table row the grader reads as not answering the question.
  Neither table serialisation fixed it (D16).
