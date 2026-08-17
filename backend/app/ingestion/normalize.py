"""Repair PDF extraction artifacts before indexing. Measured in docs/build-log.md, Slice 0."""

import re

_TOKEN = re.compile(r"[A-Za-z]{3,}")
_HYPHEN_BREAK = re.compile(r"\b([A-Za-z]{2,})-[ \t]*\n?[ \t]*([a-z]{2,})\b")
# A markdown rule row, padded by Docling to the column width.
_TABLE_RULE = re.compile(r"^[ \t]*\|[ \t|:-]*\|[ \t]*$", re.MULTILINE)


def build_vocabulary(text: str) -> frozenset[str]:
    """The document's own words — the dictionary for deciding which hyphens are artifacts."""
    return frozenset(m.group(0).lower() for m in _TOKEN.finditer(text))


def dehyphenate(text: str, vocab: frozenset[str]) -> str:
    def join_if_known(match: re.Match[str]) -> str:
        joined = match.group(1) + match.group(2)
        return joined if joined.lower() in vocab else match.group(0)

    return _HYPHEN_BREAK.sub(join_if_known, text)


def collapse_whitespace(text: str) -> str:
    text = re.sub(r"[ \t]{2,}", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def shrink_table_rules(text: str) -> str:
    """
    Docling pads the rule row to the column width, so one line of a wide table runs to 600+
    characters of dashes. The reranker tokenises each dash separately and spends its whole
    512-token window before reaching a data row. See build-log Slice 10.
    """
    return _TABLE_RULE.sub(lambda m: re.sub(r"[ \t]*-{2,}[ \t]*", "---", m.group()), text)


def normalize(text: str, vocab: frozenset[str]) -> str:
    return collapse_whitespace(shrink_table_rules(dehyphenate(text, vocab))).strip()
