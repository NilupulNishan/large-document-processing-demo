"""
Show what the merge step does to chunk size, using an already-ingested JSONL.

    uv run --project backend python playground/check_merge.py
"""

import io
import json
import statistics
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.ingestion.merge import merge_chunks, token_counter  # noqa: E402
from app.ingestion.models import Chunk  # noqa: E402

CHUNKS_DIR = REPO_ROOT / "data" / "chunks"


def load(path: Path) -> tuple[Chunk, ...]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    return tuple(
        Chunk(
            text=row["text"],
            pages=tuple(row["pages_pdf"]),
            headings=tuple(h for h in row["heading_path"].split(" > ") if h),
        )
        for row in rows
    )


def describe(label: str, chunks: tuple[Chunk, ...], count_tokens) -> None:
    sizes = sorted(count_tokens(c.text) for c in chunks)
    n = len(sizes)
    spans = [max(c.pages) - min(c.pages) + 1 if c.pages else 0 for c in chunks]
    print(
        f"{label:<10}{n:>6} chunks   "
        f"min={sizes[0]:<5} p25={sizes[n // 4]:<5} median={statistics.median(sizes):<6.0f} "
        f"p75={sizes[3 * n // 4]:<5} p95={sizes[int(n * 0.95)]:<5} max={sizes[-1]}"
    )
    print(
        f"{'':<10}{'':>6}          "
        f"under 100 tokens: {sum(s < 100 for s in sizes) / n:.0%}   "
        f"in 200-512: {sum(200 <= s <= 512 for s in sizes) / n:.0%}   "
        f"max page span: {max(spans)}"
    )


def main() -> None:
    files = sorted(CHUNKS_DIR.glob("*.jsonl"))
    if not files:
        raise SystemExit(f"No chunk files in {CHUNKS_DIR}. Run scripts/ingest.py first.")

    count_tokens = token_counter()
    for path in files:
        before = load(path)
        after = merge_chunks(before, count_tokens)
        print(f"\n=== {path.stem} ===")
        describe("before", before, count_tokens)
        describe("after", after, count_tokens)

        print("\n  sample merged chunk:")
        biggest = max(after, key=lambda c: len(c.pages))
        print(f"    pages    : {biggest.pages}")
        print(f"    headings : {biggest.headings}")
        print(f"    tokens   : {count_tokens(biggest.text)}")
        print(f"    text     : {biggest.text[:200]!r}")


if __name__ == "__main__":
    main()
