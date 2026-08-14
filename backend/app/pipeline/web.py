"""Web search, for questions the manual does not cover at all (D13, brief item 16)."""

import logging

from app import db
from app.pipeline.base import PipelineContext
from app.providers.tavily_search import search

logger = logging.getLogger(__name__)


class WebSearchStep:
    name = "web"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # `manual+general` keeps to the manual plus general guidance; only a total miss
        # earns a network call. A skipped step emits no event (D9).
        if ctx.route != "general":
            return ctx

        manual = db.get_manual(ctx.manual) or {}
        query = f"{manual.get('title', '')} {ctx.question}".strip()

        try:
            ctx.web = search(query)
        except Exception:
            # A missing key or a dead network must not cost the user their answer; the step
            # falls through and AnswerStep replies from general knowledge instead.
            logger.exception("web search failed")
            return ctx

        if ctx.web:
            ctx.emit(self.name, f"Not in the manual — searched the web, {len(ctx.web)} results")
        return ctx
