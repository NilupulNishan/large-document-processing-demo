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

Record what you used in `cited`, by number, and only what you actually used. Never write those
numbers into the answer itself — the reader is shown the sources separately, and "[1]" in the
prose is meaningless to them.

Reproduce any safety warning word for word — never paraphrase or soften one. Set resolved to
false if the passages do not really settle the question.

Write as the expert speaking to the user. They see none of what you were given, so never
refer to passages, results, numbering, "above", or what you were "provided" — the knowledge
is simply yours. If something is not covered, say what you do not know, not where you
looked for it."""

_GROUNDED = """Answer from the passages below. If they leave part of the question open, you may
add general knowledge, and mark that part with a short lead-in such as "the manual does not
specify this, but"."""

_WEB = """Their manual does not cover this. The numbered results below came from a web search —
use them where they help, and your own knowledge where they do not. Cite a result only where it
supplied the content. Do not add a disclaimer — one is prepended for you.

Where they do not settle the question, name what you cannot confirm and point to whoever can
settle it — the dealer, the manufacturer's own lookup, the warranty booklet. Describe the
authority to ask, never the searching you did or what you were or were not shown."""

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


def _page(passage: dict) -> Citation:
    printed = passage["pages_printed"] or []
    return Citation(
        type="page",
        page_pdf=passage["pages_pdf"][0],
        page_printed=printed[0] if printed else None,
        section=passage["heading_path"] or None,
    )


def _web(result: dict) -> Citation:
    return Citation(type="web", url=result["url"], title=result["title"])


def _citations(draft: Draft, items: list[dict], kind: str) -> list[Citation]:
    """Indices the model returned, mapped back to real sources. Anything else is dropped."""
    build = _page if kind == "page" else _web
    return [
        build(items[index - 1])
        for index in dict.fromkeys(draft.cited)
        if 1 <= index <= len(items)
    ]


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

        # One index space, whichever source supplied it. Page and web citations are therefore
        # never mixed in one answer, which is what keeps the two pill types meaningful (D13).
        if grounded:
            instruction, kind, items = _GROUNDED, "page", ctx.passages
            context = "What the manual says:\n" + "\n\n".join(
                f"[{i}] {p['text']}" for i, p in enumerate(items, 1)
            )
        elif ctx.web:
            instruction, kind, items = _WEB, "web", ctx.web
            context = "What you know:\n" + "\n\n".join(
                f"[{i}] {r['title']} — {r['url']}\n{r['content']}" for i, r in enumerate(items, 1)
            )
        else:
            instruction, kind, items, context = _UNGROUNDED, "web", [], ""

        # Context rides in the system message, not the user's. Sent as part of the user turn
        # the model kept calling it "the information you provided" — literally true, and
        # meaningless to a user who supplied nothing but a question.
        system = f"{_SYSTEM.format(domain=DOMAIN_DESCRIPTION)}\n\n{instruction}\n\n{context}"
        user = ctx.question

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
            citations=_citations(draft, items, kind),
            resolved=draft.resolved,
        )
        ctx.emit(self.name, "Wrote the answer")
        return ctx
