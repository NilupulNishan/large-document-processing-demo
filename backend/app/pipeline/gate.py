"""
Routing. A pure function over measured numbers; the grader supplies evidence, never a
destination (D2). Bands and their derivation: docs/build-log.md, Slice 5.
"""

from pydantic import BaseModel

from app.config import DOMAIN_DESCRIPTION, GATE_HIGH, GATE_LOW, SAFETY_TOPICS
from app.pipeline.base import PipelineContext, Route
from app.providers.azure_openai import complete


class Verdict(BaseModel):
    """What the grader observes. It does not choose a route."""

    passages_answer_the_question: bool
    question_is_about_the_domain: bool
    question_touches_a_safety_topic: bool


def decide(top_score: float, verdict: Verdict | None) -> Route:
    """Pure. Above HIGH the manual answers; below LOW it does not; between, ask."""
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
decide what happens next. Report only what you observe."""


def grade(question: str, passages: list[dict]) -> Verdict:
    excerpts = "\n\n".join(f"[{i}] {p['text'][:600]}" for i, p in enumerate(passages, 1))
    topics = ", ".join(SAFETY_TOPICS) or "none configured"
    return complete(
        _SYSTEM,
        f"Domain: {DOMAIN_DESCRIPTION}\nSafety topics: {topics}\n\n"
        f"Question: {question}\n\nPassages:\n{excerpts}",
        Verdict,
    )


class GateStep:
    name = "gate"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # Above HIGH no grader has ever been needed, so no call is made or announced.
        verdict = None if ctx.top_score > GATE_HIGH else grade(ctx.question, ctx.passages)
        if verdict is not None:
            ctx.emit(self.name, "Checked whether the manual covers this")

        ctx.route = decide(ctx.top_score, verdict)
        return ctx
