"""
Two-turn conversations. The reported failure: "I parked vechile whats now" was retrieved as a
standalone question, matched nothing, and escalated. Runs each pair with and without history.

    uv run --project backend python playground/check_followup.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.pipeline import (  # noqa: E402
    GateStep,
    Pipeline,
    RerankStep,
    ResolveQueryStep,
    RetrieveStep,
)

BJ30 = "baic-bj30-e30-owner-manual-en"
X55 = "baic-x55-ii-owner-manual-en"

PAIRS = [
    (BJ30, "how can I change flat tire", "I parked vechile whats now", "manual"),
    (BJ30, "How do I change a flat tyre?", "what torque for the nuts?", "manual"),
    (X55, "How do I change a flat tyre?", "what torque for the nuts?", "escalate"),
    (BJ30, "What engine oil does it take?", "and how much do I need?", "manual"),
]


def main() -> None:
    # Stops at the gate: the route is what the bug was about, not the prose.
    pipeline = Pipeline([ResolveQueryStep(), RetrieveStep(), RerankStep(), GateStep()])

    for manual, first, follow_up, expected in PAIRS:
        history = [
            {"role": "user", "content": first},
            {"role": "assistant", "content": "(the answer to the first question)"},
        ]
        alone = pipeline.run(follow_up, manual)
        withh = pipeline.run(follow_up, manual, history=history)

        mark = "ok" if withh.route == expected else "  "
        print(f"\n{mark} {manual[5:9]}  {first!r}\n     -> {follow_up!r}   want {expected}")
        print(f"     no history  {alone.top_score:+7.2f}  {alone.route}")
        print(f"     history     {withh.top_score:+7.2f}  {withh.route}")
        print(f"     resolved as {withh.query!r}")


if __name__ == "__main__":
    main()
