"""
The handoff. Writes a real record and shows the user its reference; nothing is transmitted
anywhere (D12). The trigger is the gate's, so no model decides that a question escalates.
"""

from app import db
from app.pipeline.base import PipelineContext

# Only the gate rule from D14 is reachable. The other three triggers — asking for a person, an
# unresolved streak, and manual-weak-and-web-weak — all need resolve_query, which is not built.
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

        if ctx.session_id:
            record = db.create_escalation(
                ctx.session_id, ctx.manual, ctx.question, _REASON, pages
            )
        else:
            record = {"id": "ESC-PREVIEW", "reason": _REASON, "pages": pages}

        text = _CONFIRMATION.format(id=record["id"])
        ctx.token(text)
        ctx.escalation = {**record, "message": text}
        ctx.emit(self.name, f"Handed to a specialist — {record['id']}")
        return ctx
