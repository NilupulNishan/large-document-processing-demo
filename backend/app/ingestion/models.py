from dataclasses import dataclass


@dataclass(frozen=True)
class Chunk:
    """One retrievable passage. Pages are 1-based PDF indices, not printed page numbers."""

    text: str
    pages: tuple[int, ...]
    headings: tuple[str, ...]


@dataclass(frozen=True)
class ParsedManual:
    page_count: int
    chunks: tuple[Chunk, ...]
    full_text: str
