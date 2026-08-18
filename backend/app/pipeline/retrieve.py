"""Hybrid search scoped to one manual, then cross-encoder reranking (D3)."""

from app.config import RERANK_CANDIDATES, RERANK_KEEP
from app.pipeline.base import PipelineContext
from app.providers.azure_openai import embed_query
from app.providers.lancedb_store import search
from app.providers.reranker import rank


class RetrieveStep:
    name = "retrieve"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        ctx.query = ctx.query or ctx.question
        ctx.candidates = search(
            ctx.manual, ctx.query, embed_query(ctx.query), limit=RERANK_CANDIDATES
        )
        ctx.emit(self.name, f"Searched the manual — {len(ctx.candidates)} passages")
        return ctx


class RerankStep:
    name = "rerank"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if not ctx.candidates:
            return ctx

        scored = rank(ctx.query, [c["text"] for c in ctx.candidates])
        ranked = sorted(zip(scored, ctx.candidates, strict=True), key=lambda pair: -pair[0][0])
        # The window the score was measured on. A long table is scored on one span; the gate
        # must judge that same span, not the passage's opening rows.
        ctx.passages = [c | {"excerpt": excerpt} for (_, excerpt), c in ranked[:RERANK_KEEP]]
        ctx.top_score = ranked[0][0][0]

        where = ranked[0][1]["heading_path"].split(" > ")[0]
        ctx.emit(self.name, f"Best match in {where}" if where else "Ranked the passages")
        return ctx
