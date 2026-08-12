"""
Check the normaliser repairs broken hyphenation without destroying real compounds.

    uv run --project backend python playground/check_normalize.py
"""

import io
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.ingestion.normalize import build_vocabulary, normalize  # noqa: E402

CHUNKS = REPO_ROOT / "data" / "chunks" / "baic-bj30-e30-owner-manual-en.jsonl"

SHOULD_JOIN = [
    ("high-voltage compo- nents", "high-voltage components"),
    ("the in-dicator light", "the indicator light"),
    ("while ensur-ing safety", "while ensuring safety"),
    ("contact a Bei-jing Automobile dealer", "contact a Beijing Automobile dealer"),
]

SHOULD_KEEP = [
    "high-voltage danger signs",
    "the anti-lock braking system",
    "a 12-volt battery",
    "four-wheel drive",
]


def load_vocabulary() -> frozenset[str]:
    if not CHUNKS.exists():
        raise SystemExit(f"Run scripts/ingest.py first — {CHUNKS.name} not found.")
    return build_vocabulary(CHUNKS.read_text(encoding="utf-8"))


def main() -> None:
    vocabulary = load_vocabulary()
    print(f"vocabulary: {len(vocabulary)} words\n")

    failures = 0

    print("--- broken hyphenation should be repaired ---")
    for broken, expected in SHOULD_JOIN:
        actual = normalize(broken, vocabulary)
        ok = actual == expected
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  {broken!r} -> {actual!r}")

    print("\n--- real compounds should survive ---")
    for phrase in SHOULD_KEEP:
        actual = normalize(phrase, vocabulary)
        ok = actual == phrase
        failures += not ok
        print(f"  {'ok  ' if ok else 'FAIL'}  {phrase!r} -> {actual!r}")

    print(f"\n{failures} failure(s)")


if __name__ == "__main__":
    main()
