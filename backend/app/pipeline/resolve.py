"""
Follow-up turns. "I parked it, what now" means nothing retrieved on its own, so it is
rewritten into a standalone question before search (D20). No history, no call.
"""

from pydantic import BaseModel

from app.pipeline.base import PipelineContext
from app.providers.azure_openai import complete

# The subject rarely survives further back than this, and every turn costs prompt tokens.
HISTORY_TURNS = 6


class Rewrite(BaseModel):
    standalone_question: str


_SYSTEM = """You rewrite a follow-up message so that it stands on its own.

Someone is working through a product manual with an assistant, often mid-task and typing
quickly. Their latest message may be mistyped, elliptical, a report of progress, or a
reference to something earlier — "what about the rear ones", "done, what now", "it still is
not working".

Rewrite it into a question someone could answer without having seen the conversation. Name
the task or component it concerns, taking that from the earlier questions: a rewrite that
asks "what should I do next" without naming what is being done has failed. Where the latest
message reports progress, the rewrite asks for the next step of that named task.

Keep their intent. Do not answer it, do not add specifics they did not give, and do not
invent a topic. If the message already stands on its own, return it unchanged."""


def resolve(question: str, history: list[dict]) -> str:
    """The standalone form of `question`. Plain function, so the eval harness can call it."""
    earlier = [m["content"] for m in history if m["role"] == "user"][-HISTORY_TURNS:]
    if not earlier:
        return question
    asked = "\n".join(f"- {text}" for text in earlier)
    return complete(
        _SYSTEM, f"Earlier questions:\n{asked}\n\nLatest message: {question}", Rewrite
    ).standalone_question


class ResolveQueryStep:
    name = "resolve_query"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # A first turn needs no rewrite, so no call is made and no event is announced (D9).
        if not ctx.history:
            return ctx

        rewrite = resolve(ctx.question, ctx.history)
        # Concatenated rather than replaced: the user's own wording still feeds BM25.
        ctx.query = f"{rewrite} {ctx.question}"
        ctx.emit(self.name, "Read the conversation so far")
        return ctx
