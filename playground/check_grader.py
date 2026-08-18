"""
What closing the GATE_HIGH bypass would cost. Above the band the gate never asks the grader, so
a confident-but-wrong score is never checked — and 43 of 59 rows are above it.

Compares three policies over the same verdicts:
  today   the shipped gate: no grader call above GATE_HIGH
  narrow  graded everywhere, but above the band only a safety topic the passages do not
          answer overrides the score
  always  graded everywhere, the verdict decides outright

    uv run --project backend python playground/check_grader.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import (  # noqa: E402
    GATE_HIGH,
    RERANK_CANDIDATES,
    RERANK_KEEP,
    UNRESOLVED_ESCALATE,
)
from app.pipeline.base import Route  # noqa: E402
from app.pipeline.gate import Verdict, decide, grade  # noqa: E402
from app.pipeline.resolve import next_streak, read  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

QUESTIONS = Path(REPO_ROOT) / "eval" / "questions.jsonl"
RUNS = 3


def narrow(top: float, verdict: Verdict, streak: int, person: bool) -> Route:
    """Proposed. The score still carries the confident cases; the grader only vetoes."""
    if person:
        return "escalate"
    if streak >= UNRESOLVED_ESCALATE:
        return "escalate"
    if top > GATE_HIGH:
        # High relevance means the manual discusses the subject. Only a safety topic it
        # demonstrably does not answer is worth overriding that.
        if not verdict.passages_answer_the_question and verdict.question_touches_a_safety_topic:
            return "escalate"
        return "manual"
    return decide(top, verdict, streak, person)


def main() -> None:
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line]
    print(f"{len(rows)} rows, {RUNS} runs each. GATE_HIGH {GATE_HIGH}\n")

    # policy -> row id -> how many runs matched the label
    right: dict[str, Counter[str]] = {p: Counter() for p in ("today", "narrow", "always")}
    bypassing = 0

    for row in rows:
        query, person = row["question"], False
        streak = row.get("streak", 0)
        if row.get("history"):
            turn = read(row["question"], row["history"])
            query = f"{turn.standalone_question} {row['question']}"
            person = turn.asks_for_a_person
            streak = next_streak(streak, turn.progress)

        hits = search(row["manual"], query, embed_query(query), limit=RERANK_CANDIDATES)
        scored = rank(query, [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]
        top = max(value for value, _ in scored)
        passages = ordered[:RERANK_KEEP]
        bypassing += top > GATE_HIGH

        seen: dict[str, Counter[str]] = {p: Counter() for p in right}
        for _ in range(RUNS):
            verdict = grade(query, passages)
            seen["today"][decide(top, verdict if top <= GATE_HIGH else None, streak, person)] += 1
            seen["narrow"][narrow(top, verdict, streak, person)] += 1
            seen["always"][decide(min(top, GATE_HIGH), verdict, streak, person)] += 1

        for policy, counts in seen.items():
            right[policy][row["id"]] = counts[row["expected_route"]]

        changed = {p: dict(c) for p, c in seen.items() if dict(c) != dict(seen["today"])}
        if changed or seen["today"][row["expected_route"]] < RUNS:
            band = "HIGH" if top > GATE_HIGH else "grade"
            print(f"{row['id']:10} {top:+7.2f} {band:5} want {row['expected_route']:14}")
            for policy, counts in seen.items():
                mark = "ok" if counts[row["expected_route"]] == RUNS else "  "
                print(f"   {mark} {policy:7} {dict(counts)}")

    print(f"\n{bypassing}/{len(rows)} rows are above GATE_HIGH and skip the grader today\n")
    print(f"{'policy':8} {'fully right':12} {'partly':7} {'never':6}")
    for policy, counts in right.items():
        full = sum(1 for v in counts.values() if v == RUNS)
        never = sum(1 for v in counts.values() if v == 0)
        print(f"{policy:8} {full:>3}/{len(rows):<8} {len(rows) - full - never:>6} {never:>6}")


if __name__ == "__main__":
    main()
