"""Detect the gap between PDF page index and printed page number. See docs/decisions.md, D6."""

import re
from collections import Counter
from pathlib import Path

_HEADER_RIGHT = re.compile(r"^.{2,60}?\s*\|\s*(\d{1,4})\s*$")
_HEADER_LEFT = re.compile(r"^(\d{1,4})\s*\|\s*.{2,60}$")

MIN_COVERAGE = 0.25
MIN_AGREEMENT = 0.9


def _printed_page_number(page_text: str) -> int | None:
    lines = [line.strip() for line in page_text.splitlines() if line.strip()]
    for candidate in lines[:1] + lines[-1:]:
        for pattern in (_HEADER_RIGHT, _HEADER_LEFT):
            match = pattern.match(candidate)
            if match:
                return int(match.group(1))
    return None


def detect_page_offset(pdf_path: Path) -> int | None:
    """PDF index minus printed page number, or None when the manual prints no page numbers."""
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(str(pdf_path))
    try:
        page_count = len(pdf)
        offsets: Counter[int] = Counter()
        for index in range(page_count):
            text = pdf[index].get_textpage().get_text_range()
            printed = _printed_page_number(text)
            if printed is not None:
                offsets[(index + 1) - printed] += 1
    finally:
        pdf.close()

    if not offsets:
        return None

    offset, count = offsets.most_common(1)[0]
    total = sum(offsets.values())
    if total / page_count < MIN_COVERAGE or count / total < MIN_AGREEMENT:
        return None
    return offset
