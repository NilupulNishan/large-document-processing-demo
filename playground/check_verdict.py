"""
Does a richer verdict route better than three booleans? Nothing here is wired into the app.

Today the grader reports `passages_answer_the_question` as one bit, so the gate cannot tell a
manual that is silent on a subject from one that discusses it at length without ever stating
the number asked for. This asks instead what kind of thing would answer the question, what the
passages supply, and for a quote Python can verify against the passages.

    uv run --project backend python playground/check_verdict.py
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import (  # noqa: E402
    DOMAIN_DESCRIPTION,
    RERANK_CANDIDATES,
    RERANK_KEEP,
    SAFETY_TOPICS,
)
from app.pipeline.base import Route  # noqa: E402
from app.providers.azure_openai import complete, embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

RUNS = 5

# Measured today with the shipped gate, for comparison. See build-log Slice 11.
TODAY = {
    "bj30-24": "manual",
    "bj30-23": "escalate",
    "x55-08": "manual",
    "esc-06": "manual",
    "esc-01": "escalate",
    "bj30-02": "manual",
    "gen-01": "general",
    "dec-01": "decline",
}


class Verdict(BaseModel):
    """What the grader observes. It still does not choose a route."""

    needs: Literal["value", "procedure", "explanation", "location", "judgement"]
    coverage: Literal["complete", "partial", "topic_only", "absent"]
    evidence_quote: str
    finding: str
    domain: Literal["in_domain", "out_of_domain"]
    safety_topic: bool


_SYSTEM = """You examine passages retrieved from a product manual and report what they contain.
You do not answer the question and you do not decide what happens next.

`needs` — what kind of thing would answer this question:
  value        a specific number, rating, capacity or setting
  procedure    an ordered set of steps
  explanation  how something works or what it means
  location     where something is
  judgement    whether something is advisable or permitted

`coverage` — what the passages actually supply for that need:
  complete     they contain the thing needed
  partial      part of it, leaving a real gap
  topic_only   they discuss the subject but never state the thing needed
  absent       the subject does not appear

`topic_only` is the one most easily missed. Passages that describe a component at length
without ever stating the number or the step asked for are topic_only, not complete.

`evidence_quote` — when coverage is complete or partial, copy the exact sentence or table row
from the passages that carries the answer, word for word, so it can be checked against them.
If you cannot copy one, the coverage is not complete. Leave it empty otherwise.

`finding` — one line: what is present, and what is missing.

`domain` — whether the question's subject belongs to the stated domain. This is about its
subject, not about whether the passages cover it. What something costs, where to obtain it,
who to contact and whether an advisory exists are all about the product.

`safety_topic` — true when the question is about one of the listed topics and someone could be
hurt by acting on a wrong answer, including any request for a procedure, a limit or a
specification used when working on one. False when it only asks what something costs, where to
obtain it, who to contact, or whether an advisory exists."""


def _flat(text: str) -> str:
    """Whitespace and case removed, so a quote still matches when the model respaces it."""
    return re.sub(r"\s+", "", text).lower()


def decide(verdict: Verdict, quoted: bool) -> Route:
    """Pure, as today. The model supplies evidence; this picks the destination."""
    if verdict.domain == "out_of_domain":
        return "decline"
    if verdict.coverage == "complete":
        # A value it cannot point to in the passages is not a value the manual states.
        if verdict.needs == "value" and not quoted:
            return "escalate" if verdict.safety_topic else "general"
        return "manual"
    if verdict.coverage == "partial":
        return "manual+general"
    return "escalate" if verdict.safety_topic else "general"


def grade(question: str, passages: list[dict]) -> Verdict:
    excerpts = "\n\n".join(f"[{i}] {p['excerpt'][:600]}" for i, p in enumerate(passages, 1))
    topics = ", ".join(SAFETY_TOPICS) or "none configured"
    return complete(
        _SYSTEM,
        f"Domain: {DOMAIN_DESCRIPTION}\nSafety topics: {topics}\n\n"
        f"Question: {question}\n\nPassages:\n{excerpts}",
        Verdict,
    )


def main() -> None:
    rows = {
        r["id"]: r
        for r in (
            json.loads(line)
            for line in (REPO_ROOT / "eval" / "questions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        if r["id"] in TODAY
    }

    print(f"{RUNS} runs each. 'today' is the shipped gate, measured in Slice 11.\n")
    fixed = broken = 0

    for rid, row in rows.items():
        question, expected = row["question"], row["expected_route"]
        hits = search(row["manual"], question, embed_query(question), limit=RERANK_CANDIDATES)
        scored = rank(question, [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]
        passages = ordered[:RERANK_KEEP]
        haystack = _flat("".join(p["excerpt"] for p in passages))

        routes: Counter[str] = Counter()
        shapes: Counter[str] = Counter()
        quotes, findings = [], []
        for _ in range(RUNS):
            verdict = grade(question, passages)
            quoted = bool(verdict.evidence_quote) and _flat(verdict.evidence_quote) in haystack
            routes[decide(verdict, quoted)] += 1
            shapes[f"{verdict.needs}/{verdict.coverage}{'' if quoted else ' unquoted'}"] += 1
            if verdict.evidence_quote:
                quotes.append((quoted, verdict.evidence_quote))
            findings.append(verdict.finding)

        was = TODAY[rid]
        hits_right = routes[expected]
        if was != expected and hits_right == RUNS:
            fixed += 1
        if was == expected and hits_right < RUNS:
            broken += 1
        verdict_mark = "ok" if hits_right == RUNS else ("--" if hits_right == 0 else "??")

        print(f"{verdict_mark} {rid:9} want {expected:14} today {was:10} now {dict(routes)}")
        print(f"   {question}")
        for shape, count in shapes.most_common():
            print(f"     {count}x {shape}")
        if quotes:
            ok, text = quotes[0]
            print(f"     quote {'verified' if ok else 'NOT IN PASSAGES'}: {text[:110]!r}")
        print(f"     finding: {findings[0][:150]}")
        print()

    print(f"fixed {fixed}   newly broken {broken}   of {len(rows)} cases")


if __name__ == "__main__":
    main()
