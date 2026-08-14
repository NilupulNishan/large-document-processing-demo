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

from app.config import MANUALS_DIR  # noqa: E402
from app.db import upsert_manual  # noqa: E402
from app.ingestion.merge import token_counter  # noqa: E402
from app.providers.azure_openai import embed_texts  # noqa: E402
from app.providers.lancedb_store import write_chunks  # noqa: E402


def embeddable(record: dict) -> str:
    """D4: the heading path rides along with the chunk text into the vector."""
    heading = record["heading_path"]
    return f"{heading}\n\n{record['text']}" if heading else record["text"]


def recover_offset(records: list[dict]) -> int | None:
    """The printed-page offset, read back off the chunks rather than re-parsing the PDF."""
    for record in records:
        if record["pages_pdf"] and record["pages_printed"]:
            return record["pages_pdf"][0] - record["pages_printed"][0]
    return None


def register_manual(manual_id: str, records: list[dict], title: str | None = None) -> None:
    """Metadata the API needs — title, page count, offset — which ingest does not persist."""
    import pypdfium2

    pdf_path = MANUALS_DIR / f"{manual_id}.pdf"
    if not pdf_path.exists():
        raise SystemExit(f"PDF not found beside the chunks: {pdf_path}")

    with pypdfium2.PdfDocument(pdf_path) as pdf:
        page_count = len(pdf)

    # The title shows in the picker and rides into every web search query, so it is worth
    # setting properly. It stays a database row, never a product name in code (rule 3).
    # PDF metadata is no help here — these two report '6.24画册' and '前言'.
    title = title or manual_id.replace("-", " ").title()
    offset = recover_offset(records)
    upsert_manual(manual_id, title, pdf_path.name, page_count, offset)
    print(f"  registered '{title}' — {page_count} pages, offset {offset}")


def main() -> None:
    argument_parser = argparse.ArgumentParser(description="Embed one manual into LanceDB.")
    argument_parser.add_argument("jsonl", type=Path)
    argument_parser.add_argument(
        "--register-only",
        action="store_true",
        help="Rewrite the manuals row without re-embedding. data/app.db is derived state and "
        "may be deleted; recovering it should not cost another embedding run.",
    )
    argument_parser.add_argument(
        "--title", help="Display name for the picker and web search queries."
    )
    arguments = argument_parser.parse_args()

    jsonl_path = arguments.jsonl if arguments.jsonl.is_absolute() else REPO_ROOT / arguments.jsonl
    if not jsonl_path.exists():
        raise SystemExit(f"Chunk file not found: {jsonl_path}")

    records = [json.loads(line) for line in jsonl_path.read_text(encoding="utf-8").splitlines()]

    if arguments.register_only:
        register_manual(records[0]["manual"], records, arguments.title)
        return

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
    register_manual(records[0]["manual"], records, arguments.title)


if __name__ == "__main__":
    main()
