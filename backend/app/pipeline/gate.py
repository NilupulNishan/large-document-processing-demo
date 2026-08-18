"""
Routing. A pure function over measured numbers; the grader supplies evidence, never a
destination (D2). Bands and their derivation: docs/build-log.md, Slice 5.
"""

import re

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
    # A question demanding a number is the one kind of answerability Python can check, and
    # the quote is what it checks (D22). Empty when the passages do not state one.
    asks_for_a_specific_value: bool
    answer_quote: str


def quoted(verdict: Verdict, passages: list[dict]) -> bool:
    """Whether the grader's quote is really in what it was shown. Whitespace and case are
    ignored so a requoted line still matches; anything else must be verbatim."""
    if not verdict.answer_quote:
        return False
    flat = re.sub(r"\s+", "", "".join(p["excerpt"][:600] for p in passages)).lower()
    return re.sub(r"\s+", "", verdict.answer_quote).lower() in flat


def decide(
    top_score: float,
    verdict: Verdict | None,
    streak: int = 0,
    asks_for_person: bool = False,
    quote_verified: bool = False,
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
        # A high score means the manual discusses the subject, not that it states the number
        # asked for — the two come apart exactly on specification questions (D19). Where a
        # value is wanted, is a safety matter, and cannot be quoted from what was retrieved,
        # the score is overruled. A procedure has no single sentence to quote, so this can
        # only ever fire on a value question (D22).
        if (
            verdict is not None
            and verdict.asks_for_a_specific_value
            and verdict.question_touches_a_safety_topic
            and not quote_verified
        ):
            return "escalate"
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
something costs, where to obtain it, who to contact, or whether an advisory exists.

`asks_for_a_specific_value` — read the question on its own and ignore the passages entirely
when answering this one. Would a complete answer have to state a particular number, rating,
capacity, grade or setting? "What torque", "what pressure", "how much", "how many", "how deep",
"what grade" all require one, and they still require one when the passages happen not to state
it — that the passages are silent is what the other fields are for. A question asking for a
sequence of steps, or for an account of how something works, does not require one.

When it does, copy into `answer_quote` the exact sentence or table row from the passages that
states that value, word for word, so it can be checked against them. If nothing in the passages
states it, leave `answer_quote` empty. Never write a sentence that is not there."""


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
    if ctx.top_score > GATE_HIGH:
        return "The manual covers this subject but does not state the value asked for"
    return "Safety-critical topic the manual does not cover"


class GateStep:
    name = "gate"

    def run(self, ctx: PipelineContext) -> PipelineContext:
        # Graded on every question. The score alone cannot tell a manual that states a value
        # from one that only discusses the subject, and that gap is where a confident wrong
        # answer lives (D22).
        verdict = grade(ctx.query, ctx.passages)
        ctx.emit(self.name, "Checked whether the manual covers this")

        ctx.route = decide(
            ctx.top_score,
            verdict,
            ctx.unresolved_streak,
            ctx.asks_for_person,
            quoted(verdict, ctx.passages),
        )
        if ctx.route == "escalate":
            ctx.escalation_trigger = _trigger(ctx, verdict)
        return ctx
