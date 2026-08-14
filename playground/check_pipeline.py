"""
Ask the pipeline real questions and read what comes back.

    uv run --project backend python playground/check_pipeline.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")  # answers contain — and →; the console defaults to cp1252
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.pipeline import build_pipeline  # noqa: E402

BJ30 = "baic-bj30-e30-owner-manual-en"
X55 = "baic-x55-ii-owner-manual-en"

QUESTIONS = [
    (BJ30, "How do I pair my phone with the car's bluetooth?"),
    (BJ30, "What engine oil does it take and how many litres?"),
    (BJ30, "The airbag warning light is on. What does that mean?"),
    (X55, "I accidentally put diesel in. What now?"),
    (X55, "How do I pair my phone with bluetooth?"),
    (BJ30, "Is there a recall on this vehicle?"),
    (BJ30, "What does the warranty cover and for how long?"),
    (BJ30, "What is the weather forecast for tomorrow?"),
]


def main() -> None:
    pipeline = build_pipeline()
    for manual, question in QUESTIONS:
        ctx = pipeline.run(question, manual)
        print(f"\n{'=' * 78}\n{question}   [{manual.split('-owner')[0]}]\n{'=' * 78}")
        print(f"  score {ctx.top_score:+.2f}   route {ctx.route}")
        for step, label in ctx.events:
            print(f"    · {step}: {label}")

        if ctx.answer is None:
            print("  (no answer — escalation not built)")
            continue

        print(f"\n  format {ctx.answer.format}   source {ctx.answer.source}   "
              f"resolved {ctx.answer.resolved}")
        for line in ctx.answer.answer.splitlines():
            print(f"  {line}")
        for citation in ctx.answer.citations:
            if citation.type == "web":
                print(f"    [web]  {citation.url}")
                continue
            page = citation.page_printed or citation.page_pdf
            kind = "printed" if citation.page_printed else "pdf"
            print(f"    [page] p{page} ({kind})  {(citation.section or '')[:50]}")


if __name__ == "__main__":
    main()
