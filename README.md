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
| `docs/build-log.md` | One entry per working slice |
| `AGENTS.md` | Boundaries, non-goals and policy for coding agents |

## Layout

```
backend/          FastAPI app, pipeline steps, providers
  app/
    pipeline/     resolve_query → retrieve → rerank → gate → web_search → answer → escalate
    providers/    Azure, LanceDB, Docling, Tavily adapters — SDK types stop here
frontend/         Next.js UI: manual picker, chat, PDF pane, session history, operator inbox
eval/             questions.jsonl + run.py — the test suite for this project
playground/       Experiment scripts. Not application code.
scripts/          ingest.py and dev helpers
data/             Source manuals, LanceDB store, SQLite database (all gitignored)
```

## Status

Scaffold only. No application code yet.
