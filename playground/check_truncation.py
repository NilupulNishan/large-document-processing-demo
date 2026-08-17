"""
How much of each chunk the cross-encoder actually reads. It truncates at RERANK_MAX_TOKENS,
so anything past that point cannot influence the score no matter how well it matches.

    uv run --project backend python playground/check_truncation.py
"""

import json
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import RERANK_MAX_TOKENS  # noqa: E402
from app.providers.reranker import _model  # noqa: E402

QUESTION = "What is the maximum trailer weight I can tow?"
NEEDLE = "quasi-trailer"


def main() -> None:
    tokenizer, _ = _model()
    files = sorted((REPO_ROOT / "data" / "chunks").glob("*.jsonl"))

    print(f"cross-encoder reads at most {RERANK_MAX_TOKENS} tokens per pair\n")

    for path in files:
        rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
        counts = [len(tokenizer(r["text"])["input_ids"]) for r in rows]
        over = [n for n in counts if n > RERANK_MAX_TOKENS]
        worst = max(counts)
        print(
            f"{path.stem:34} {len(rows):4} chunks   "
            f"{len(over):3} truncated ({len(over) / len(rows):3.0%})   longest {worst} tokens"
        )
        # Tokens the reranker never sees, as a share of the corpus.
        lost = sum(n - RERANK_MAX_TOKENS for n in over)
        print(f"{'':34} {lost:,} of {sum(counts):,} tokens unreadable ({lost / sum(counts):.0%})")

    # The specific failure: where the answer sits relative to the cut.
    bj30 = files[0]
    rows = [json.loads(line) for line in bj30.read_text(encoding="utf-8").splitlines() if line]
    chunk = next(r for r in rows if NEEDLE in r["text"])
    ids = tokenizer(chunk["text"])["input_ids"]
    visible = tokenizer.decode(ids[1 : RERANK_MAX_TOKENS - 1])

    print(f"\n{QUESTION}")
    print(f"  chunk        {len(chunk['text']):,} chars / {len(ids):,} tokens")
    print(f"  reranker sees first {len(visible):,} chars ({len(visible) / len(chunk['text']):.0%})")
    print(f"  '{NEEDLE}' at char {chunk['text'].find(NEEDLE):,}")
    print(f"  visible to reranker: {NEEDLE in visible}")
    print(f"\n  what it does see, tail end:\n  ...{visible[-300:]}")


if __name__ == "__main__":
    main()
