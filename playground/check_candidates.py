"""
What the reranker scored and why, for one question. Prints each candidate with its score,
its length, and whether the reranker could read all of it.

    uv run --project backend python playground/check_candidates.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import RERANK_CANDIDATES, RERANK_MAX_TOKENS  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import _model, score  # noqa: E402

QUESTIONS = [
    ("baic-bj30-e30-owner-manual-en", "What is the wheel nut torque specification?"),
    ("baic-bj30-e30-owner-manual-en", "What is the maximum trailer weight I can tow?"),
]


def main() -> None:
    tokenizer, _ = _model()
    for manual, question in QUESTIONS:
        hits = search(manual, question, embed_query(question), limit=RERANK_CANDIDATES)
        scores = score(question, [h["text"] for h in hits])
        ranked = sorted(zip(scores, hits, strict=True), key=lambda p: -p[0])

        print(f"\n{'=' * 100}\n{question}\n{'=' * 100}")
        for rank, (value, hit) in enumerate(ranked[:6], 1):
            total = len(tokenizer(hit["text"])["input_ids"])
            cut = "" if total <= RERANK_MAX_TOKENS else f"  READ {RERANK_MAX_TOKENS}/{total}"
            print(
                f"{rank}. {value:+7.2f}  p{str(hit['pages_pdf'][:2]):12} "
                f"{hit['heading_path'][:38]:40}{cut}"
            )
            head = tokenizer.decode(tokenizer(hit["text"])["input_ids"][1:60])
            print(f"          {head[:150]}")


if __name__ == "__main__":
    main()
