"""Repair PDF extraction artifacts before indexing. Measured in docs/build-log.md, Slice 0."""

import re

_TOKEN = re.compile(r"[A-Za-z]{3,}")
_HYPHEN_BREAK = re.compile(r"\b([A-Za-z]{2,})-[ \t]*\n?[ \t]*([a-z]{2,})\b")


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


def normalize(text: str, vocab: frozenset[str]) -> str:
    return collapse_whitespace(dehyphenate(text, vocab)).strip()
