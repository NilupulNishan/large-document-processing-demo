"""
What the grader would say for questions the gate never asks it about. GATE_HIGH skips the
grader entirely above the band, so a confident-but-wrong score is never checked.

    uv run --project backend python playground/check_grader.py
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import GATE_HIGH, RERANK_CANDIDATES, RERANK_KEEP  # noqa: E402
from app.pipeline.gate import decide, grade  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

QUESTIONS = Path(REPO_ROOT) / "eval" / "questions.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines() if line]
    print(f"grading every row regardless of band (GATE_HIGH {GATE_HIGH})\n")
    print(f"{'id':10} {'score':>7}  {'band':5} {'answers':7} {'domain':6} {'safety':6} "
          f"{'would route':14} {'expected':14}")

    wrong = []
    for row in rows:
        hits = search(
            row["manual"], row["question"], embed_query(row["question"]), limit=RERANK_CANDIDATES
        )
        scored = rank(row["question"], [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]
        top = max(value for value, _ in scored)

        verdict = grade(row["question"], ordered[:RERANK_KEEP])
        # What routing would give if the grader always ran.
        forced = decide(min(top, GATE_HIGH), verdict)
        actual = decide(top, verdict if top <= GATE_HIGH else None)

        band = "HIGH" if top > GATE_HIGH else "grade"
        flag = "" if actual == row["expected_route"] else "  <-- misroutes today"
        if actual != row["expected_route"]:
            wrong.append((row["id"], actual, forced, row["expected_route"]))
        print(
            f"{row['id']:10} {top:+7.2f}  {band:5} "
            f"{str(verdict.passages_answer_the_question):7} "
            f"{str(verdict.question_is_about_the_domain):6} "
            f"{str(verdict.question_touches_a_safety_topic):6} "
            f"{actual:14} {row['expected_route']:14}{flag}"
        )

    print(f"\nmisrouted today: {len(wrong)}/{len(rows)}")
    for rid, actual, forced, expected in wrong:
        fixed = "FIXED by always grading" if forced == expected else "still wrong"
        print(f"  {rid:10} got {actual:14} want {expected:14} -> {fixed}")


if __name__ == "__main__":
    main()
