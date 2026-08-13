"""
Smoke-test the index before investing in labelled questions. Not the eval harness —
that is eval/run.py, with expected pages to assert against.

    uv run --project backend python playground/check_search.py
"""

import sys
from pathlib import Path

sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import CHUNKS_DIR  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402

QUERIES = [
    "how do I change a flat tyre",
    "what does the yellow engine warning light mean",
    "recommended tyre pressure",
    "engine oil specification and capacity",
    "how do I pair a phone over bluetooth",
]
TOP_N = 3


def main() -> None:
    manuals = sorted(path.stem for path in CHUNKS_DIR.glob("*.jsonl"))
    if not manuals:
        raise SystemExit(f"No chunk files in {CHUNKS_DIR}. Run scripts/ingest.py first.")

    for manual in manuals:
        print(f"\n{'=' * 78}\n{manual}\n{'=' * 78}")
        for query in QUERIES:
            hits = search(manual, query, embed_query(query), limit=TOP_N)
            print(f"\n  {query!r}")
            for hit in hits:
                pages = hit["pages_printed"] or hit["pages_pdf"]
                label = "printed" if hit["pages_printed"] else "pdf"
                snippet = " ".join(hit["text"].split())[:88]
                print(f"    p{pages} ({label})  {hit['heading_path'][:28]:28}  {snippet}")
            leaked = [h["chunk_id"] for h in hits if h["manual"] != manual]
            if leaked:
                print(f"    !! rows from another manual leaked in: {leaked}")


if __name__ == "__main__":
    main()
