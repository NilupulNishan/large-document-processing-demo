"""
Follow-up turns. "I parked it, what now" means nothing retrieved on its own, so it is
rewritten into a standalone question before search (D20). No history, no call.
"""

from typing import Literal

from pydantic import BaseModel

from app.pipeline.base import PipelineContext
from app.providers.azure_openai import complete

# The subject rarely survives further back than this, and every turn costs prompt tokens.
HISTORY_TURNS = 6


class Rewrite(BaseModel):
    """Observations about the turn. Nothing here chooses a route or an escalation (D14)."""

    standalone_question: str
    asks_for_a_person: bool
    progress: Literal["reports_failure", "confirms_success", "new_topic", "unclear"]


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
invent a topic. If the message already stands on its own, return it unchanged.

Also report two things about the message, and only what you observe:

`asks_for_a_person` — whether they are asking to be put in touch with a human: a person, an
adviser, the dealer, support, someone who can help. Asking what a dealer would charge, or
where one is, is not asking for a person.

`progress` — how their message relates to what they were last told:
  reports_failure   they tried it and it did not work, or the problem is still there
  confirms_success  they say it worked, or that the problem is resolved
  new_topic         they have moved on to a different subject
  unclear           none of these, including a plain next question on the same subject"""


def read(question: str, history: list[dict]) -> Rewrite:
    """What the turn is, and what it reports. One call; D14's fields ride along free."""
    earlier = [m["content"] for m in history if m["role"] == "user"][-HISTORY_TURNS:]
    asked = "\n".join(f"- {text}" for text in earlier) or "(none)"
    return complete(
        _SYSTEM, f"Earlier questions:\n{asked}\n\nLatest message: {question}", Rewrite
    )


def next_streak(streak: int, progress: str) -> int:
    """Pure. A model said what it saw; this counts (D14)."""
    if progress == "reports_failure":
        return streak + 1
    if progress in ("confirms_success", "new_topic"):
        return 0
    return streak


def resolve(question: str, history: list[dict]) -> str:
    """The standalone form of `question`. Plain function, so the eval harness can call it."""
    if not history:
        return question
    return read(question, history).standalone_question


class ResolveQueryStep:
    name = "resolve_query"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # A first turn needs no rewrite, so no call is made and no event is announced (D9).
        if not ctx.history:
            return ctx

        turn = read(ctx.question, ctx.history)
        # Concatenated rather than replaced: the user's own wording still feeds BM25.
        ctx.query = f"{turn.standalone_question} {ctx.question}"
        ctx.asks_for_person = turn.asks_for_a_person

        ctx.unresolved_streak = next_streak(ctx.unresolved_streak, turn.progress)

        ctx.emit(self.name, "Read the conversation so far")
        return ctx
