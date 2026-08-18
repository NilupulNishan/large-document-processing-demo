"""
How often the grader gives the same verdict for the same input. It decides every route below
GATE_HIGH, so any flipping here is a route flipping.

    uv run --project backend python playground/check_grader_stability.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import (  # noqa: E402
    RERANK_CANDIDATES,
    RERANK_KEEP,
    UNRESOLVED_ESCALATE,
)
from app.pipeline.gate import decide, grade, quoted  # noqa: E402
from app.pipeline.resolve import next_streak, read  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

RUNS = 5
FIELDS = ("passages_answer_the_question", "question_is_about_the_domain",
          "question_touches_a_safety_topic", "asks_for_a_specific_value")


def main() -> None:
    questions = (REPO_ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8")
    rows = [json.loads(line) for line in questions.splitlines() if line]
    # Only rows the grader actually decides: at or below the band, no shortcut.
    graded = []
    for row in rows:
        # Mirrors ResolveQueryStep, or the history rows are measured on a question the
        # pipeline never sends.
        query, asks_for_person = row["question"], False
        streak = row.get("streak", 0)
        if row.get("history"):
            turn = read(row["question"], row["history"])
            query = f"{turn.standalone_question} {row['question']}"
            asks_for_person = turn.asks_for_a_person
            streak = next_streak(streak, turn.progress)

        hits = search(row["manual"], query, embed_query(query), limit=RERANK_CANDIDATES)
        scored = rank(query, [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]
        top = max(value for value, _ in scored)
        # Every question is graded now (D22), so every row is measured — except those a D14
        # trigger decides before the grader is consulted.
        if not asks_for_person and streak < UNRESOLVED_ESCALATE:
            graded.append((row, query, ordered[:RERANK_KEEP], top, streak))

    print(f"{len(graded)} rows the grader can move; {RUNS} runs each\n")
    print(f"{'id':10} {'routes seen':38} {'stable':7} {'expected'}")

    flipping = 0
    for row, query, passages, top, streak in graded:
        routes, flips = [], Counter()
        for _ in range(RUNS):
            verdict = grade(query, passages)
            routes.append(decide(top, verdict, streak, False, quoted(verdict, passages)))
            for field in FIELDS:
                flips[field] += getattr(verdict, field)
        seen = Counter(routes)
        stable = len(seen) == 1
        flipping += not stable
        unstable = [f.split("_")[-1] for f in FIELDS if 0 < flips[f] < RUNS]
        print(
            f"{row['id']:10} {str(dict(seen)):38} {'yes' if stable else 'NO':7} "
            f"{row['expected_route']:14} {'flips: ' + ','.join(unstable) if unstable else ''}"
        )

    print(f"\n{flipping}/{len(graded)} rows changed route across identical runs")


if __name__ == "__main__":
    main()
