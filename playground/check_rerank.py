"""
Derive the gate bands from reranker scores. RRF scores could not separate a grounded
question from a poem (build-log Slice 4); this measures whether the cross-encoder can.

    uv run --project backend python playground/check_rerank.py

Prints the widest HIGH and LOW that keep the confident bands pure, and how many
questions land in the ambiguous band that costs a grader call (D2).
"""

import json
import sys
import time
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import RERANK_CANDIDATES, RERANKER_MODEL  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import score  # noqa: E402

QUESTIONS = REPO_ROOT / "eval" / "questions.jsonl"


def main() -> None:
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]

    print(f"loading {RERANKER_MODEL} ...")
    started = time.perf_counter()
    score("warm up", ["warm up"])
    print(f"  ready in {time.perf_counter() - started:.1f} s\n")

    elapsed = 0.0
    for row in rows:
        hits = search(
            row["manual"], row["question"], embed_query(row["question"]), limit=RERANK_CANDIDATES
        )
        started = time.perf_counter()
        scores = score(row["question"], [h["text"] for h in hits])
        elapsed += time.perf_counter() - started
        row["top"] = max(scores) if scores else 0.0

    grounded = sorted(r["top"] for r in rows if r["expected_pages"])
    ungrounded = sorted((r for r in rows if not r["expected_pages"]), key=lambda r: -r["top"])

    # Widest bands that stay pure: nothing ungrounded above HIGH, nothing grounded below LOW.
    high = max(r["top"] for r in ungrounded)
    low = grounded[0]

    print("questions the manual cannot answer, highest first\n")
    for row in ungrounded:
        print(f"  {row['id']}  {row['top']:+7.2f}  {row['expected_route']:8} {row['question']}")

    print(f"\ngrounded  n={len(grounded)}  min {grounded[0]:+.2f}  max {grounded[-1]:+.2f}")
    print("\nlowest-scoring grounded questions\n")
    for row in sorted((r for r in rows if r["expected_pages"]), key=lambda r: r["top"])[:5]:
        print(f"  {row['id']}  {row['top']:+7.2f}  {row['kind']:9} {row['question']}")

    if high >= low:
        ambiguous = [g for g in grounded if low <= g <= high]
        print(f"\nGATE_HIGH {high:+.2f}   above this, nothing ungrounded appeared")
        print(f"GATE_LOW  {low:+.2f}   below this, nothing grounded appeared")
        print(f"\nambiguous band holds {len(ambiguous)}/{len(grounded)} grounded "
              f"({len(ambiguous) / len(grounded):.0%}) — each costs one grader call")
    else:
        print(f"\nfully separated: set both thresholds anywhere in {high:+.2f}..{low:+.2f}")

    print(f"\nrerank latency: {elapsed / len(rows) * 1000:.0f} ms per question "
          f"for {RERANK_CANDIDATES} passages")


if __name__ == "__main__":
    main()
