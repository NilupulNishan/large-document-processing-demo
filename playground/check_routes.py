"""
Which questions actually reach `escalate` and `manual+general`. Stops at the gate, so no
answer is generated. Candidates that route as intended become eval rows.

    uv run --project backend python playground/check_routes.py
"""

import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.pipeline import GateStep, Pipeline, RerankStep, RetrieveStep  # noqa: E402

BJ30 = "baic-bj30-e30-owner-manual-en"
X55 = "baic-x55-ii-owner-manual-en"

# A safety topic the manual does not settle — the only way to reach `escalate`. Owner's manuals
# cover the safety topics well, so what works is service-manual data about a safety system.
ESCALATE = [
    (BJ30, "What torque do I use on the brake caliper bolts?"),
    (X55, "Can I tow a 2,500 kg caravan with this?"),
    (BJ30, "What is the wheel nut torque specification?"),
    (BJ30, "What brake fluid DOT rating and part number does the ABS module require?"),
    (X55, "What is the maximum tongue weight on the tow bar?"),
    (X55, "Which airbag control module part number is fitted to this car?"),
    (BJ30, "Where are the reinforced jacking points for a two-post lift?"),
    (X55, "What is the isolation resistance spec for the high-voltage battery pack?"),
    (BJ30, "Can I fit a towbar myself and what wiring does it need?"),
    (X55, "What is the brake disc minimum thickness before replacement?"),
]

# Partly covered — the manual answers some of it, general knowledge finishes it.
PARTIAL = [
    (X55, "What does the check engine light mean and can I diagnose it with an OBD reader?"),
    (BJ30, "What size wiper blades does it take and where can I buy them?"),
    (BJ30, "How do I connect Android Auto and why does it keep dropping out?"),
    (X55, "What coolant does it use and can I top it up with tap water in an emergency?"),
    (BJ30, "How long does the battery last and what happens if I leave it parked a month?"),
    (X55, "What fuel grade does it need and can I use E10?"),
]


def main() -> None:
    pipeline = Pipeline([RetrieveStep(), RerankStep(), GateStep()])
    for title, group in (("escalate", ESCALATE), ("manual+general", PARTIAL)):
        print(f"\n{'=' * 92}\nwanted: {title}\n{'=' * 92}")
        for manual, question in group:
            ctx = pipeline.run(question, manual)
            mark = "OK " if ctx.route == title else "   "
            print(f"{mark} {ctx.top_score:+7.2f}  {ctx.route:<15} {question}")


if __name__ == "__main__":
    main()
