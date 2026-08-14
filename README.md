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

The intended shape. Parts not yet built are marked; see Status below.

```
backend/          FastAPI app, pipeline steps, providers
  app/
    api.py        HTTP routes and SSE framing
    db.py         SQLite — manuals, sessions, messages
    pipeline/     resolve_query* → retrieve → rerank → gate → web_search → answer → escalate*
    providers/    Azure, LanceDB, Docling, Tavily adapters — SDK types stop here
frontend/*        Next.js UI: manual picker, chat, PDF pane, session history, operator inbox
eval/             questions.jsonl + run.py — the test suite for this project
playground/       Experiment scripts. Not application code.
scripts/          ingest.py, index.py and dev helpers
data/             Source manuals, LanceDB store, SQLite database (all gitignored)

* not built yet
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

Then start the API:

```bash
uv run --project backend --locked --no-sync uvicorn app.api:app --app-dir backend
```

Interactive docs are at `http://127.0.0.1:8000/docs`. They can drive every endpoint, but Swagger
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
| "How do I change a flat tyre?" | `source=manual`, page citations, no `gate` event |
| "What engine oil does it take?" | `source=manual`, preceded by a `gate` event |
| "What does the warranty cover?" | `source=general`, a `web` event, `[web]` citations |
| "Write me a poem about the sea" | `decline`, one short refusal, no model call |

Two step events are worth watching. A `gate` event appears only when the top score fell below
`GATE_HIGH` and a grader call actually ran — seeing one on a question that answered confidently is a
bug. A `web` event appears only on the `general` route; on a manual-answered question it means the
gate misrouted.

Safety-critical questions the manual does not cover route to `escalate`, which is **not built** — the
stream returns an `error` frame rather than an answer. That is deliberate, not a crash.

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

## Status

Built: ingestion, embedding and indexing; the `retrieve → rerank → gate → web_search → answer`
pipeline; SSE transport; session persistence.

Not built: `resolve_query`, `escalate` and the operator inbox, and the frontend.
`docs/architecture.md` marks each of these `(not built)` and is kept in step with the code.
