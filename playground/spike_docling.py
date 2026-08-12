"""
Measure Docling parse speed and verify chunk metadata. Results in docs/build-log.md, Slice 0.

    uv run --project backend python playground/spike_docling.py [page_from] [page_to]
"""

from __future__ import annotations

import io
import sys
import time
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

REPO_ROOT = Path(__file__).resolve().parents[1]
MANUAL = REPO_ROOT / "data" / "manuals" / "baic-bj30-e30-owner-manual-en.pdf"

# Default: 20 pages of dense body content, mid-document.
# Override from the command line, e.g. `... spike_docling.py 268 281` for Technical Parameters.
PAGE_FROM = int(sys.argv[1]) if len(sys.argv) > 1 else 130
PAGE_TO = int(sys.argv[2]) if len(sys.argv) > 2 else 149
CORPUS_PAGES = 546


def pages_of(meta) -> list[int]:
    """Page numbers a chunk spans, read from Docling provenance."""
    return sorted(
        {
            prov.page_no
            for item in (getattr(meta, "doc_items", []) or [])
            for prov in (getattr(item, "prov", []) or [])
            if getattr(prov, "page_no", None) is not None
        }
    )


def build_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False
    options.do_table_structure = True
    options.table_structure_options.do_cell_matching = True

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def main() -> None:
    if not MANUAL.exists():
        raise SystemExit(f"Manual not found: {MANUAL}")

    print(f"parsing pages {PAGE_FROM}-{PAGE_TO} of {MANUAL.name}")
    print("OCR disabled (born-digital corpus). Layout + table models download on first run.\n")

    converter = build_converter()

    # Warm the models on one page so the timed run measures parsing, not downloading.
    t0 = time.perf_counter()
    converter.convert(MANUAL, page_range=(PAGE_FROM, PAGE_FROM))
    print(f"warmup (1 page, includes model load): {time.perf_counter() - t0:6.1f} s")

    t0 = time.perf_counter()
    result = converter.convert(MANUAL, page_range=(PAGE_FROM, PAGE_TO))
    elapsed = time.perf_counter() - t0

    n_pages = PAGE_TO - PAGE_FROM + 1
    per_page = elapsed / n_pages
    print(f"parse  ({n_pages} pages):                  {elapsed:6.1f} s")
    print(f"per page:                             {per_page:6.2f} s")
    print(f"-> extrapolated {CORPUS_PAGES} pages:        {per_page * CORPUS_PAGES / 60:6.1f} min\n")

    doc = result.document

    # ---- chunking -----------------------------------------------------------
    from docling.chunking import HybridChunker

    try:
        import tiktoken
        from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

        chunker = HybridChunker(
            tokenizer=OpenAITokenizer(
                tokenizer=tiktoken.encoding_for_model("gpt-4o"), max_tokens=8191
            ),
            merge_peers=True,
        )
        print("chunker: HybridChunker + OpenAITokenizer(gpt-4o)")
    except Exception as e:  # noqa: BLE001
        chunker = HybridChunker(merge_peers=True)
        print(f"chunker: HybridChunker default tokenizer ({type(e).__name__}: {e})")

    t0 = time.perf_counter()
    chunks = list(chunker.chunk(dl_doc=doc))
    print(f"chunking: {len(chunks)} chunks in {time.perf_counter() - t0:.1f} s")
    print(f"-> extrapolated corpus: ~{len(chunks) * CORPUS_PAGES // n_pages} chunks\n")

    # ---- metadata verification ---------------------------------------------
    print("=" * 78)
    print("METADATA CHECK - do we get headings and page numbers?")
    print("=" * 78)

    with_headings = sum(1 for c in chunks if getattr(c.meta, "headings", None))
    with_pages = sum(1 for c in chunks if pages_of(c.meta))
    multipage = sum(1 for c in chunks if len(pages_of(c.meta)) > 1)

    print(f"chunks with headings:     {with_headings}/{len(chunks)}")
    print(f"chunks with page numbers: {with_pages}/{len(chunks)}")
    print(f"chunks spanning >1 page:  {multipage}/{len(chunks)}\n")

    for i, ch in enumerate(chunks[:3]):
        print(f"--- chunk {i} ---")
        print(f"  headings : {getattr(ch.meta, 'headings', None)}")
        print(f"  pages    : {pages_of(ch.meta)}")
        print(f"  chars    : {len(ch.text)}")
        print(f"  text     : {ch.text[:260]!r}\n")

    # ---- table check --------------------------------------------------------
    print(f"tables detected in this page range: {len(getattr(doc, 'tables', []) or [])}")
    md = doc.export_to_markdown()
    print(f"markdown export: {len(md)} chars")
    if "|" in md:
        start = md.index("|")
        print("first markdown table fragment:")
        print(md[start : start + 400])


if __name__ == "__main__":
    main()
