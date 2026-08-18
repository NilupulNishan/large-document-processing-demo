"""
What the grader should be shown. It judges whether the passages answer the question, so the
span it reads decides the route. Compares the head of each passage against the window the
reranker actually scored, at full length and at the same character budget.

    uv run --project backend python playground/check_evidence.py
"""

import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import (  # noqa: E402
    DOMAIN_DESCRIPTION,
    GATE_HIGH,
    RERANK_CANDIDATES,
    RERANK_KEEP,
    SAFETY_TOPICS,
)
from app.pipeline.gate import _SYSTEM, Verdict, decide  # noqa: E402
from app.providers.azure_openai import complete, embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

BJ30 = "baic-bj30-e30-owner-manual-en"
X55 = "baic-x55-ii-owner-manual-en"

# The rows that decide the design, plus the unlabelled case the corpus cannot answer at all.
CASES = [
    ("bj30-16", BJ30, "How often should the car be serviced?", "manual"),
    ("bj30-23", BJ30, "What is the maximum trailer weight I can tow?", "manual"),
    ("x55-08", X55, "How does hill descent control work?", "manual"),
    ("bj30-24", BJ30, "What is the wheel nut torque specification?", "manual"),
    ("esc-06", X55, "What torque do I tighten the wheel nuts to?", "escalate"),
    ("bj30-02", BJ30, "What engine oil does it take and how many litres?", "manual"),
    ("esc-01", BJ30, "What torque do I use on the brake caliper bolts?", "escalate"),
]

RUNS = 5

VARIANTS = {
    "head 600": lambda p: p["text"][:600],
    "window": lambda p: p["excerpt"],
    "window 600": lambda p: p["excerpt"][:600],
}


def grade_with(question: str, passages: list[dict], excerpt) -> Verdict:
    """gate.grade with the excerpt construction swapped out."""
    body = "\n\n".join(f"[{i}] {excerpt(p)}" for i, p in enumerate(passages, 1))
    topics = ", ".join(SAFETY_TOPICS) or "none configured"
    return complete(
        _SYSTEM,
        f"Domain: {DOMAIN_DESCRIPTION}\nSafety topics: {topics}\n\n"
        f"Question: {question}\n\nPassages:\n{body}",
        Verdict,
    )


def main() -> None:
    print(f"{RUNS} runs per variant; the grader is not fully stable, so one run proves nothing\n")
    for rid, manual, question, expected in CASES:
        hits = search(manual, question, embed_query(question), limit=RERANK_CANDIDATES)
        scored = rank(question, [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]
        top = max(value for value, _ in scored)
        passages = ordered[:RERANK_KEEP]

        print(f"\n{rid}  top {top:+.2f}  want {expected}  {question}")
        for name, excerpt in VARIANTS.items():
            routes = Counter()
            for _ in range(RUNS):
                verdict = grade_with(question, passages, excerpt)
                # Forced through the grader so the variants are comparable above the band too.
                routes[decide(min(top, GATE_HIGH), verdict)] += 1
            size = sum(len(excerpt(p)) for p in passages)
            hits = routes[expected]
            mark = "ok" if hits == RUNS else ("  " if hits == 0 else "??")
            print(f"  {mark} {name:11} {size:6} chars  {hits}/{RUNS} right  {dict(routes)}")


if __name__ == "__main__":
    main()
