"""
Embed one manual's chunks into LanceDB. Reads ingest.py's JSONL, so changing what
gets embedded never costs another 10-minute PDF parse.

    uv run --project backend python scripts/index.py data/chunks/<file>.jsonl
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.ingestion.merge import token_counter  # noqa: E402
from app.providers.azure_openai import embed_texts  # noqa: E402
from app.providers.lancedb_store import write_chunks  # noqa: E402


def embeddable(record: dict) -> str:
    """D4: the heading path rides along with the chunk text into the vector."""
    heading = record["heading_path"]
    return f"{heading}\n\n{record['text']}" if heading else record["text"]


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Embed one manual into LanceDB.")
    argument_parser.add_argument("jsonl", type=Path)
    arguments = argument_parser.parse_args()

    jsonl_path = arguments.jsonl if arguments.jsonl.is_absolute() else REPO_ROOT / arguments.jsonl
    if not jsonl_path.exists():
        raise SystemExit(f"Chunk file not found: {jsonl_path}")

    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]
    texts = [embeddable(record) for record in records]

    count_tokens = token_counter()
    total_tokens = sum(count_tokens(text) for text in texts)
    print(f"{jsonl_path.name}: {len(records)} chunks, {total_tokens:,} tokens")

    started = time.perf_counter()
    vectors = embed_texts(texts)
    print(f"  embedded in {time.perf_counter() - started:.1f} s")

    rows = [
        {
            "chunk_id": record["chunk_id"],
            "manual": record["manual"],
            "text": record["text"],
            "heading_path": record["heading_path"],
            "pages_pdf": record["pages_pdf"],
            "pages_printed": record["pages_printed"] or [],
            "vector": vector,
        }
        for record, vector in zip(records, vectors, strict=True)
    ]

    print(f"  table now holds {write_chunks(rows)} rows")


if __name__ == "__main__":
    main()
