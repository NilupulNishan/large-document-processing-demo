"""
The handoff. Writes a real record and shows the user its reference; nothing is transmitted
anywhere (D12). The trigger is the gate's, so no model decides that a question escalates.
"""

from pydantic import BaseModel

from app import db
from app.config import DOMAIN_DESCRIPTION
from app.pipeline.base import PipelineContext
from app.providers.azure_openai import complete

# Three of D14's four triggers are reachable; the gate names which one fired. Manual-weak-and-
# web-weak is (not built). This is the fallback when a caller reached the step without one.
_REASON = "Safety-critical topic the manual does not cover"

_CONFIRMATION = (
    "I do not want to guess at this one — it is a safety-critical question and your manual "
    "does not cover it.\n\nI have passed it to a specialist with everything from this "
    "conversation, so you will not have to explain it again. Your reference is **{id}**."
)


class Handoff(BaseModel):
    summary: str
    suggested_next_step: str


_SUMMARY = """You are briefing a support specialist who is about to take over a conversation.

Write `summary` as a few sentences describing what the user is trying to do, what they have
already been told or tried, and precisely where they are stuck. Write it about them, in the
third person. Do not solve the problem, do not guess at causes, and do not repeat the whole
conversation back.

Write `suggested_next_step` as one sentence naming what the specialist should establish or do
first. If the manual simply does not carry the information, say that plainly.

Everything you write is read by a person, never shown to the user as their own words."""


def summarise(ctx: PipelineContext, reason: str) -> Handoff:
    """D14's issue summary and next step. On this route no answer is written, so this call
    replaces the answer call rather than adding one."""
    turns = "\n".join(f"{m['role']}: {m['content']}" for m in ctx.history[-12:])
    return complete(
        _SUMMARY,
        f"Domain: {DOMAIN_DESCRIPTION}\nWhy it reached you: {reason}\n\n"
        f"Conversation so far:\n{turns or '(this is their first message)'}\n\n"
        f"Their latest message: {ctx.question}",
        Handoff,
    )


class EscalateStep:
    name = "escalate"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.route != "escalate":
            return ctx

        # Pages the user was already shown, so nobody sends them back to the same place.
        pages = sorted({page for passage in ctx.passages for page in passage["pages_pdf"]})

        reason = ctx.escalation_trigger or _REASON
        brief = summarise(ctx, reason)
        if ctx.session_id:
            record = db.create_escalation(
                ctx.session_id, ctx.manual, ctx.question, reason, pages
            )
            db.set_handoff_summary(record["id"], brief.summary, brief.suggested_next_step)
        else:
            record = {"id": "ESC-PREVIEW", "reason": reason, "pages": pages}
        record = {**record, "summary": brief.summary, "next_step": brief.suggested_next_step}

        text = _CONFIRMATION.format(id=record["id"])
        ctx.token(text)
        ctx.escalation = {**record, "message": text}
        # A person has it now. Left standing, the counter would escalate every later turn.
        ctx.unresolved_streak = 0
        ctx.emit(self.name, f"Handed to a specialist — {record['id']}")
        return ctx
