"""
The handoff. Writes a real record and shows the user its reference; nothing is transmitted
anywhere (D12). The trigger is the gate's, so no model decides that a question escalates.
"""

from app import db
from app.pipeline.base import PipelineContext

# Three of D14's four triggers are reachable; the gate names which one fired. Manual-weak-and-
# web-weak is (not built). This is the fallback when a caller reached the step without one.
_REASON = "Safety-critical topic the manual does not cover"

_CONFIRMATION = (
    "I do not want to guess at this one — it is a safety-critical question and your manual "
    "does not cover it.\n\nI have passed it to a specialist with everything from this "
    "conversation, so you will not have to explain it again. Your reference is **{id}**."
)


class EscalateStep:
    name = "escalate"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.route != "escalate":
            return ctx

        # Pages the user was already shown, so nobody sends them back to the same place.
        pages = sorted({page for passage in ctx.passages for page in passage["pages_pdf"]})

        reason = ctx.escalation_trigger or _REASON
        if ctx.session_id:
            record = db.create_escalation(
                ctx.session_id, ctx.manual, ctx.question, reason, pages
            )
        else:
            record = {"id": "ESC-PREVIEW", "reason": reason, "pages": pages}

        text = _CONFIRMATION.format(id=record["id"])
        ctx.token(text)
        ctx.escalation = {**record, "message": text}
        # A person has it now. Left standing, the counter would escalate every later turn.
        ctx.unresolved_streak = 0
        ctx.emit(self.name, f"Handed to a specialist — {record['id']}")
        return ctx
