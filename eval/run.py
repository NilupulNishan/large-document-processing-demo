"""
Retrieval quality against eval/questions.jsonl. This is the test suite for this project.

    uv run --project backend python eval/run.py

Reports fusion order against reranked order over the same candidates, so the reranker's
contribution is isolated. Routing accuracy is not reported yet — the gate does not exist.
"""

import json
import sys
import time
from collections import defaultdict
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import GATE_HIGH, GATE_LOW, RERANK_CANDIDATES  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import score  # noqa: E402

QUESTIONS = Path(__file__).parent / "questions.jsonl"
CUTOFFS = (1, 3, 5, 10)


def hit_rank(hits: list[dict], expected: set[int]) -> int | None:
    """1-based rank of the first chunk overlapping an expected page."""
    for rank, hit in enumerate(hits, start=1):
        # Printed numbers where a manual has a detected offset, PDF indices otherwise (D6).
        if expected & set(hit["pages_printed"] or hit["pages_pdf"]):
            return rank
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
        hits = search(
            row["manual"], row["question"], embed_query(row["question"]), limit=RERANK_CANDIDATES
        )
        scores = score(row["question"], [h["text"] for h in hits])
        ordered = [h for _, h in sorted(zip(scores, hits, strict=True), key=lambda p: -p[0])]

        expected = set(row["expected_pages"])
        row["fusion_rank"] = hit_rank(hits, expected)
        row["rerank_rank"] = hit_rank(ordered, expected)
        row["top_score"] = max(scores) if scores else 0.0

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

    print("\nGate — top reranker score per question\n")
    for row in rows:
        if not row["expected_pages"]:
            band = "HIGH" if row["top_score"] > GATE_HIGH else "grader"
            band = "LOW" if row["top_score"] < GATE_LOW else band
            print(f"  {row['id']}  {row['top_score']:+7.2f}  {band:6} {row['expected_route']}")

    in_band = [r for r in grounded if GATE_LOW <= r["top_score"] <= GATE_HIGH]
    print(f"\n  grounded needing a grader call: {len(in_band)}/{len(grounded)}")
    print(f"  bands GATE_HIGH {GATE_HIGH:+.2f}  GATE_LOW {GATE_LOW:+.2f}")
    print(f"\n{(time.perf_counter() - started) / len(rows) * 1000:.0f} ms per question end to end")


if __name__ == "__main__":
    main()
