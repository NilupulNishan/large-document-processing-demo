"""
Ingest one manual into normalised chunks. Stops at JSONL; embedding is the next slice.

    uv run --project backend python scripts/ingest.py data/manuals/<file>.pdf
"""

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.ingestion.merge import merge_chunks, token_counter  # noqa: E402
from app.ingestion.normalize import build_vocabulary, normalize  # noqa: E402
from app.ingestion.offset import detect_page_offset  # noqa: E402
from app.providers.docling_parser import parse  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "data" / "chunks"
PARSED_DIR = REPO_ROOT / "data" / "parsed"


def heading_path(headings: tuple[str, ...]) -> str:
    return " > ".join(headings)


def main() -> None:
    argument_parser = argparse.ArgumentParser(
        description="Ingest one manual into normalised chunks."
    )
    argument_parser.add_argument("pdf", type=Path)
    argument_parser.add_argument(
        "--reparse", action="store_true", help="ignore the cached parse and run the models again"
    )
    arguments = argument_parser.parse_args()

    pdf_path = arguments.pdf if arguments.pdf.is_absolute() else REPO_ROOT / arguments.pdf
    if not pdf_path.exists():
        raise SystemExit(f"Manual not found: {pdf_path}")

    # Cheap and fallible, so it runs before the parse rather than after it.
    offset = detect_page_offset(pdf_path)
    print(f"printed-page offset: {offset if offset is not None else 'none detected'}")

    cache = PARSED_DIR / f"{pdf_path.stem}.json"
    if arguments.reparse:
        cache.unlink(missing_ok=True)

    print(f"parsing {pdf_path.name} ({'cached' if cache.exists() else 'running the models'}) ...")
    started = time.perf_counter()
    manual = parse(pdf_path, cache=cache)
    elapsed = time.perf_counter() - started
    print(
        f"  {manual.page_count} pages, {len(manual.chunks)} chunks "
        f"in {elapsed / 60:.1f} min ({elapsed / manual.page_count:.2f} s/page)"
    )

    count_tokens = token_counter()
    chunks = merge_chunks(manual.chunks, count_tokens)
    sizes = sorted(count_tokens(chunk.text) for chunk in chunks)
    print(
        f"  merged {len(manual.chunks)} -> {len(chunks)} chunks "
        f"(median {sizes[len(sizes) // 2]} tokens, max {sizes[-1]})"
    )

    vocabulary = build_vocabulary(manual.full_text)
    print(f"  vocabulary: {len(vocabulary)} words")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_path = OUTPUT_DIR / f"{pdf_path.stem}.jsonl"
    changed = 0

    with output_path.open("w", encoding="utf-8") as handle:
        for index, chunk in enumerate(chunks):
            text = normalize(chunk.text, vocabulary)
            if text != chunk.text:
                changed += 1
            record = {
                "chunk_id": f"{pdf_path.stem}:{index}",
                "manual": pdf_path.stem,
                "text": text,
                "heading_path": heading_path(chunk.headings),
                "pages_pdf": list(chunk.pages),
                "pages_printed": (
                    [page - offset for page in chunk.pages] if offset is not None else None
                ),
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    print(f"  normalised {changed}/{len(chunks)} chunks")
    print(f"wrote {output_path.relative_to(REPO_ROOT)}")


if __name__ == "__main__":
    main()
