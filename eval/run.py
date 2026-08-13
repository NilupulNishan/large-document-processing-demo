"""
Retrieval quality against eval/questions.jsonl. This is the test suite for this project.

    uv run --project backend python eval/run.py

Routing accuracy is not reported yet — the gate does not exist. Rows with no expected
pages are scored only for their top relevance score, which is what will calibrate it.
"""

import json
import sys
from collections import defaultdict
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402

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
    print(f"  {title:30} n={len(ranks):3}  {recalls}   MRR {mrr:.3f}")


def main() -> None:
    rows = [json.loads(line) for line in QUESTIONS.read_text(encoding="utf-8").splitlines()]

    for row in rows:
        row["hits"] = search(
            row["manual"], row["question"], embed_query(row["question"]), limit=max(CUTOFFS)
        )
        row["rank"] = hit_rank(row["hits"], set(row["expected_pages"]))
        row["top_score"] = row["hits"][0]["_relevance_score"] if row["hits"] else 0.0

    grounded = [r for r in rows if r["expected_pages"]]
    ungrounded = [r for r in rows if not r["expected_pages"]]

    by_manual: dict[str, list[int | None]] = defaultdict(list)
    by_kind: dict[str, list[int | None]] = defaultdict(list)
    for row in grounded:
        by_manual[row["manual"].replace("-owner-manual-en", "")].append(row["rank"])
        by_kind[row["kind"]].append(row["rank"])

    print(f"\nRetrieval — {len(grounded)} grounded questions\n")
    report("overall", [r["rank"] for r in grounded])
    print()
    for title, values in sorted(by_manual.items()):
        report(title, values)
    print()
    for title, values in sorted(by_kind.items()):
        report(title, values)

    misses = [r for r in grounded if r["rank"] is None]
    if misses:
        print(f"\nMissed entirely ({len(misses)}):\n")
        for row in misses:
            got = [h["pages_printed"] or h["pages_pdf"] for h in row["hits"][:3]]
            print(f"  {row['id']}  {row['question']}")
            print(f"       expected {row['expected_pages']}  got {got}")

    print("\nTop score where the manual should not answer — calibrates the gate\n")
    for row in ungrounded:
        print(f"  {row['id']}  {row['top_score']:.4f}  {row['expected_route']:8} {row['question']}")

    scores = sorted(r["top_score"] for r in grounded)
    median = scores[len(scores) // 2]
    print(f"\n  grounded rows score {scores[0]:.4f}–{scores[-1]:.4f}, median {median:.4f}")


if __name__ == "__main__":
    main()
