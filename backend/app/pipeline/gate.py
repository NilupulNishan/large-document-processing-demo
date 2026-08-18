"""
Routing. A pure function over measured numbers; the grader supplies evidence, never a
destination (D2). Bands and their derivation: docs/build-log.md, Slice 5.
"""

from pydantic import BaseModel

from app.config import (
    DOMAIN_DESCRIPTION,
    GATE_HIGH,
    GATE_LOW,
    SAFETY_TOPICS,
    UNRESOLVED_ESCALATE,
)
from app.pipeline.base import PipelineContext, Route
from app.providers.azure_openai import complete


class Verdict(BaseModel):
    """What the grader observes. It does not choose a route."""

    passages_answer_the_question: bool
    question_is_about_the_domain: bool
    question_touches_a_safety_topic: bool


def decide(
    top_score: float,
    verdict: Verdict | None,
    streak: int = 0,
    asks_for_person: bool = False,
) -> Route:
    """Pure. Above HIGH the manual answers; below LOW it does not; between, ask."""
    # Asking for a human is a request to honour, not one to talk someone out of (D14).
    if asks_for_person:
        return "escalate"
    # Three turns that resolved nothing is a handoff, not a fourth attempt. Checked before the
    # band, not after: the streak only reaches this by the user reporting failure or by answers
    # that were not grounded, so a confident score here is the fourth try at what already failed.
    if streak >= UNRESOLVED_ESCALATE:
        return "escalate"

    if top_score > GATE_HIGH:
        return "manual"

    if verdict is None:
        return "general"

    if not verdict.question_is_about_the_domain:
        return "decline"
    if verdict.passages_answer_the_question:
        return "manual" if top_score > GATE_LOW else "manual+general"
    # The manual is silent. Improvising on a safety topic is worse than a handoff (D13).
    return "escalate" if verdict.question_touches_a_safety_topic else "general"


_SYSTEM = """You judge retrieved passages. You do not answer the question and you do not
decide what happens next. Report only what you observe.

Whether the question is about the domain is about its subject, not about whether the passages
cover it. What something costs, where to obtain it, who to contact and whether an advisory
exists are all about the product.

A question touches a safety topic when it is about one of the listed topics and someone could
be hurt by acting on a wrong answer — including any request for a procedure, a limit or a
specification used when working on one. It does not, when the question only asks what
something costs, where to obtain it, who to contact, or whether an advisory exists."""


def grade(question: str, passages: list[dict]) -> Verdict:
    excerpts = "\n\n".join(f"[{i}] {p['excerpt'][:600]}" for i, p in enumerate(passages, 1))
    topics = ", ".join(SAFETY_TOPICS) or "none configured"
    return complete(
        _SYSTEM,
        f"Domain: {DOMAIN_DESCRIPTION}\nSafety topics: {topics}\n\n"
        f"Question: {question}\n\nPassages:\n{excerpts}",
        Verdict,
    )


# The operator needs to know which rule fired, not just that one did (D12).
def _trigger(ctx: PipelineContext, verdict: Verdict | None) -> str:
    if ctx.asks_for_person:
        return "The user asked to speak to a person"
    if ctx.unresolved_streak >= UNRESOLVED_ESCALATE:
        return f"Nothing resolved it across {ctx.unresolved_streak} turns"
    return "Safety-critical topic the manual does not cover"


class GateStep:
    name = "gate"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # Above HIGH no grader has ever been needed, so no call is made or announced.
        verdict = None if ctx.top_score > GATE_HIGH else grade(ctx.query, ctx.passages)
        if verdict is not None:
            ctx.emit(self.name, "Checked whether the manual covers this")

        ctx.route = decide(ctx.top_score, verdict, ctx.unresolved_streak, ctx.asks_for_person)
        if ctx.route == "escalate":
            ctx.escalation_trigger = _trigger(ctx, verdict)
        return ctx
