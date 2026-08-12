"""Combine undersized chunks into retrievable windows. See docs/build-log.md, Slice 2."""

from collections import Counter
from collections.abc import Callable, Sequence

from app.config import EMBEDDING_MODEL, MAX_PAGE_SPAN, TARGET_CHUNK_TOKENS
from app.ingestion.models import Chunk


def token_counter() -> Callable[[str], int]:
    import tiktoken

    encoding = tiktoken.encoding_for_model(EMBEDDING_MODEL)
    return lambda text: len(encoding.encode(text))


def _page_span(pages: Sequence[int]) -> int:
    return max(pages) - min(pages) + 1 if pages else 0


def _combine(group: list[Chunk], frequency: Counter[str]) -> Chunk:
    pages = sorted({page for chunk in group for page in chunk.pages})
    # Least frequent heading first: a heading on many chunks locates nothing.
    headings = sorted({h for chunk in group for h in chunk.headings}, key=lambda h: frequency[h])
    return Chunk(
        text="\n\n".join(chunk.text for chunk in group),
        pages=tuple(pages),
        headings=tuple(headings),
    )


def merge_chunks(
    chunks: Sequence[Chunk],
    count_tokens: Callable[[str], int],
    target_tokens: int = TARGET_CHUNK_TOKENS,
    max_page_span: int = MAX_PAGE_SPAN,
) -> tuple[Chunk, ...]:
    """Greedily join consecutive chunks up to a token target, without crossing a page span."""
    frequency = Counter(heading for chunk in chunks for heading in chunk.headings)
    merged: list[Chunk] = []
    group: list[Chunk] = []
    group_tokens = 0
    group_pages: set[int] = set()

    for chunk in chunks:
        tokens = count_tokens(chunk.text)
        combined_pages = group_pages | set(chunk.pages)
        fits = (
            group_tokens + tokens <= target_tokens
            and _page_span(sorted(combined_pages)) <= max_page_span
        )
        if group and not fits:
            merged.append(_combine(group, frequency))
            group, group_tokens, group_pages = [], 0, set()
            combined_pages = set(chunk.pages)

        group.append(chunk)
        group_tokens += tokens
        group_pages = combined_pages

    if group:
        merged.append(_combine(group, frequency))
    return tuple(merged)
