"""
Retrieval quality against eval/questions.jsonl. This is the test suite for this project.

    uv run --project backend python eval/run.py

Reports fusion order against reranked order over the same candidates, so the reranker's
contribution is isolated, then routing accuracy for the gate exactly as it runs in
production — the grader is called only below GATE_HIGH, as it is at query time.
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import GATE_HIGH, GATE_LOW, RERANK_CANDIDATES, RERANK_KEEP  # noqa: E402
from app.pipeline.gate import decide, grade  # noqa: E402
from app.pipeline.resolve import next_streak, read  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

QUESTIONS = Path(__file__).parent / "questions.jsonl"
CUTOFFS = (1, 3, 5, 10)


def hit_rank(hits: list[dict], expected: set[int]) -> int | None:
    """1-based rank of the first chunk overlapping an expected page."""
    for position, hit in enumerate(hits, start=1):
        # Printed numbers where a manual has a detected offset, PDF indices otherwise (D6).
        if expected & set(hit["pages_printed"] or hit["pages_pdf"]):
            return position
    return None


def report(title: str, ranks: list[int | None]) -> None:
    recalls = " ".join(
        f"@{k} {sum(1 for r in ranks if r and r <= k) / len(ranks):4.0%}" for k in CUTOFFS
    )
    mrr = sum(1 / r for r in ranks if r) / len(ranks)
    print(f"  {title:26} n={len(ranks):3}  {recalls}   MRR {mrr:.3f}")


def main() -> None:
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]
    started = time.perf_counter()

    for row in rows:
        # Mirrors ResolveQueryStep: a row with history is rewritten before anything searches,
        # and the same call reports D14's two observations (D20).
        query, asks_for_person = row["question"], False
        streak = row.get("streak", 0)
        if row.get("history"):
            turn = read(row["question"], row["history"])
            query = f"{turn.standalone_question} {row['question']}"
            asks_for_person = turn.asks_for_a_person
            streak = next_streak(streak, turn.progress)
        row["query"] = query

        hits = search(row["manual"], query, embed_query(query), limit=RERANK_CANDIDATES)
        scored = rank(query, [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]

        expected = set(row["expected_pages"])
        row["fusion_rank"] = hit_rank(hits, expected)
        row["rerank_rank"] = hit_rank(ordered, expected)
        row["top_score"] = top = max((value for value, _ in scored), default=0.0)
        # The gate as it runs at query time: above the band no grader is called (D2).
        verdict = None if top > GATE_HIGH else grade(query, ordered[:RERANK_KEEP])
        row["route"] = decide(top, verdict, streak, asks_for_person)

    grounded = [r for r in rows if r["expected_pages"]]

    print(f"\nRetrieval — {len(grounded)} grounded questions, {RERANK_CANDIDATES} candidates\n")
    report("fusion only", [r["fusion_rank"] for r in grounded])
    report("+ cross-encoder", [r["rerank_rank"] for r in grounded])

    by_kind: dict[str, list[tuple[int | None, int | None]]] = defaultdict(list)
    for row in grounded:
        by_kind[row["kind"]].append((row["fusion_rank"], row["rerank_rank"]))

    print("\nby kind, reranked\n")
    for kind, pairs in sorted(by_kind.items()):
        report(kind, [r for _, r in pairs])

    moved = [(r["fusion_rank"], r["rerank_rank"], r) for r in grounded]
    worse = [(f, k, r) for f, k, r in moved if f and k and k > f]
    better = [(f, k, r) for f, k, r in moved if f and k and k < f]
    print(f"\nreranking moved {len(better)} questions up, {len(worse)} down")
    for f, k, row in sorted(worse, key=lambda t: t[1] - t[0], reverse=True)[:5]:
        print(f"  down {f}->{k}  {row['id']}  {row['question']}")

    print("\nRouting\n")
    misrouted = [r for r in rows if r["route"] != r["expected_route"]]
    for row in misrouted:
        band = "HIGH" if row["top_score"] > GATE_HIGH else "grader"
        print(
            f"  {row['id']:10} {row['top_score']:+7.2f} {band:6} "
            f"got {row['route']:14} want {row['expected_route']}"
        )

    correct = len(rows) - len(misrouted)
    print(f"\n  routing accuracy {correct / len(rows):.0%}  ({correct}/{len(rows)})")

    by_route: dict[str, list[bool]] = defaultdict(list)
    for row in rows:
        by_route[row["expected_route"]].append(row["route"] == row["expected_route"])
    for route, results in sorted(by_route.items()):
        print(f"    {route:16} {sum(results)}/{len(results)}")

    graded = [r for r in rows if r["top_score"] <= GATE_HIGH]
    print(f"\n  reached the grader: {len(graded)}/{len(rows)}")
    print(f"  bands GATE_HIGH {GATE_HIGH:+.2f}  GATE_LOW {GATE_LOW:+.2f}")
    print(f"\n{(time.perf_counter() - started) / len(rows) * 1000:.0f} ms per question end to end")


if __name__ == "__main__":
    main()
