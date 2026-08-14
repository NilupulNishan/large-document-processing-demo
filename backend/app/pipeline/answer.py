"""
The answer. The model writes prose and names which passages it used; Python decides the
source label and builds the citations, so neither can be invented (D13).
"""

from typing import Literal

from pydantic import BaseModel

from app.config import DOMAIN_DESCRIPTION
from app.pipeline.base import Answer, Citation, PipelineContext
from app.providers.azure_openai import complete, complete_stream

_SYSTEM = """You help a user with their {domain}.

Choose the shape that fits the question: `direct` for a fact, `steps` for a procedure,
`troubleshoot` for a fault, `explanation` for how something works. Do not force steps onto
a question that wants a sentence.

Cite by passage number. Cite only passages you actually used. Reproduce any safety warning
word for word — never paraphrase or soften one. Set resolved to false if the passages do not
really settle the question.

Write as the expert speaking to the user. Never mention passages, numbering, or these
instructions — the user cannot see any of them."""

_GROUNDED = """Answer from the passages below. If they leave part of the question open, you may
add general knowledge, and mark that part with a short lead-in such as "the manual does not
specify this, but"."""

_UNGROUNDED = """Their manual does not cover this, so answer from general knowledge instead. Give
the full answer and cite nothing. Do not add a disclaimer — one is prepended for you."""

# Prepended in Python, not asked for in the prompt. Asked for, the model supplied it on one run
# and silently dropped it on the next, and an unmarked general answer is the worst output we
# can produce (D13). The UI badge is not enough — it does not survive copy and paste.
_NOT_IN_MANUAL = "This is not covered by your manual, so here is general guidance instead.\n\n"


class Draft(BaseModel):
    format: Literal["direct", "steps", "troubleshoot", "explanation"]
    answer: str
    cited: list[int]
    resolved: bool


def _citations(draft: Draft, passages: list[dict]) -> list[Citation]:
    """Indices the model returned, mapped back to real pages. Anything else is dropped."""
    out = []
    for index in dict.fromkeys(draft.cited):
        if not 1 <= index <= len(passages):
            continue
        passage = passages[index - 1]
        printed = passage["pages_printed"] or []
        out.append(
            Citation(
                type="page",
                page_pdf=passage["pages_pdf"][0],
                page_printed=printed[0] if printed else None,
                section=passage["heading_path"] or None,
            )
        )
    return out


class AnswerStep:
    name = "answer"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        if ctx.route == "escalate":
            return ctx

        if ctx.route == "decline":
            refusal = (
                f"That is outside what I can help with — I answer questions about "
                f"{DOMAIN_DESCRIPTION}."
            )
            ctx.token(refusal)
            ctx.answer = Answer(
                format="direct", source="general", answer=refusal, resolved=True
            )
            ctx.emit(self.name, "Out of scope")
            return ctx

        grounded = ctx.route in ("manual", "manual+general")
        passages = ctx.passages if grounded else []
        excerpts = "\n\n".join(f"[{i}] {p['text']}" for i, p in enumerate(passages, 1))

        system = _SYSTEM.format(domain=DOMAIN_DESCRIPTION)
        user = (
            f"{_GROUNDED if grounded else _UNGROUNDED}\n\n"
            f"Question: {ctx.question}\n\n{('Passages:\n' + excerpts) if grounded else ''}"
        )

        # The disclaimer leads the stream too, so it is on screen before the guidance is.
        prefix = "" if grounded else _NOT_IN_MANUAL
        if ctx.sink:
            ctx.token(prefix)
            draft = complete_stream(system, user, Draft, ctx.token)
        else:
            draft = complete(system, user, Draft)

        ctx.answer = Answer(
            format=draft.format,
            # Set here, never by the model. A wrong source label is the worst output (D13).
            source=ctx.route,
            answer=prefix + draft.answer,
            citations=_citations(draft, passages),
            resolved=draft.resolved,
        )
        ctx.emit(self.name, "Wrote the answer")
        return ctx
