"""
What actually changes between identical runs, attributed to the stage that changed it.

    uv run --project backend python playground/check_grader_stability.py

Two passes. A holds the query, passages and score fixed and re-runs the grader, so every flip
is the grader's. B re-runs the whole per-row path, so the difference between them is what the
turn classifier, the rewrite and the content filter contribute (D32).
"""

import json
import sys
from collections import Counter
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import RERANK_CANDIDATES, RERANK_KEEP  # noqa: E402
from app.pipeline.gate import decide, grade, quoted  # noqa: E402
from app.pipeline.resolve import next_streak, read  # noqa: E402
from app.providers.azure_openai import embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

RUNS = 5
# Pass B re-runs retrieval and the rewrite too, which costs roughly three times pass A.
ONLY_A = "--grader-only" in sys.argv
FIELDS = (
    "passages_answer_the_question",
    "question_is_about_the_domain",
    "question_touches_a_safety_topic",
    "asks_for_a_specific_value",
)


def resolve_row(row: dict) -> tuple[str, bool, bool, int]:
    """Mirrors ResolveQueryStep, including D28's every-turn read and D30's first-turn replace."""
    streak, asks, asked = row.get("streak", 0), False, True
    turn = read(row["question"], row.get("history") or [])
    if turn is None:
        return row["question"], asks, asked, streak
    asks, asked = turn.asks_for_a_person, turn.carries_a_question
    streak = next_streak(streak, turn.progress)
    query = (
        f"{turn.standalone_question} {row['question']}"
        if row.get("history")
        else turn.standalone_question
    )
    return query, asks, asked, streak


def retrieve(row: dict, query: str) -> tuple[list[dict], float]:
    hits = search(row["manual"], query, embed_query(query), limit=RERANK_CANDIDATES)
    scored = rank(query, [h["text"] for h in hits])
    ordered = [
        h | {"excerpt": excerpt}
        for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
    ]
    return ordered[:RERANK_KEEP], max((value for value, _ in scored), default=0.0)


def route_once(row: dict, query: str, asks: bool, asked: bool, streak: int):
    """One route, plus the verdict behind it. None where the turn ends before the gate."""
    if not asked and not asks:
        return "acknowledge", None, 0.0
    passages, top = retrieve(row, query)
    verdict = grade(query, passages)
    return decide(top, verdict, streak, asks, quoted(verdict, passages)), verdict, top


def report(title: str, rows: list[dict], observed: dict[str, dict]) -> None:
    unstable = {rid: o for rid, o in observed.items() if len(o["route"]) > 1}
    print(f"\n{title} — {RUNS} runs over {len(rows)} rows")
    print(f"  rows whose route is not stable: {len(unstable)}/{len(rows)}")
    flips = Counter()
    for o in observed.values():
        for field in FIELDS:
            flips[field] += len(o[field]) > 1
    for field, count in flips.most_common():
        print(f"    {field:34} flipped on {count:2} rows")
    for rid, o in unstable.items():
        extra = []
        if len(o["query"]) > 1:
            extra.append(f"{len(o['query'])} queries")
        if len(o["top"]) > 1:
            extra.append(f"{len(o['top'])} scores")
        varied = [f.split("_")[-1] for f in FIELDS if len(o[field := f]) > 1]
        if varied:
            extra.append("grader: " + ",".join(varied))
        print(f"    {rid:10} {dict(o['route'])}   {' · '.join(extra)}")


def main() -> None:
    lines = (REPO_ROOT / "eval" / "questions.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(line) for line in lines if line]

    blank = lambda: {k: Counter() for k in ("route", "query", "top", *FIELDS)}  # noqa: E731
    pass_a: dict[str, dict] = {}
    pass_b: dict[str, dict] = {}

    for row in rows:
        rid = row["id"]
        # A: resolve and retrieve once, then only the grader moves.
        query, asks, asked, streak = resolve_row(row)
        observed = pass_a[rid] = blank()
        observed["query"][query] += 1
        if not asked and not asks:
            observed["route"]["acknowledge"] += RUNS
        else:
            passages, top = retrieve(row, query)
            observed["top"][f"{top:+.2f}"] += RUNS
            for _ in range(RUNS):
                verdict = grade(query, passages)
                seen = decide(top, verdict, streak, asks, quoted(verdict, passages))
                observed["route"][seen] += 1
                for field in FIELDS:
                    observed[field][getattr(verdict, field)] += 1

        if ONLY_A:
            continue

        # B: everything re-runs, so the rewrite and the classifier move too.
        observed = pass_b[rid] = blank()
        for _ in range(RUNS):
            query, asks, asked, streak = resolve_row(row)
            observed["query"][query] += 1
            route, verdict, top = route_once(row, query, asks, asked, streak)
            observed["route"][route] += 1
            observed["top"][f"{top:+.2f}"] += 1
            if verdict is not None:
                for field in FIELDS:
                    observed[field][getattr(verdict, field)] += 1

    report("A · grader only", rows, pass_a)
    if ONLY_A:
        return
    report("B · end to end", rows, pass_b)

    only_b = {r for r, o in pass_b.items() if len(o["route"]) > 1} - {
        r for r, o in pass_a.items() if len(o["route"]) > 1
    }
    print(f"\nrows unstable only end to end (not the grader): {sorted(only_b) or 'none'}")
    reworded = sorted(r for r, o in pass_b.items() if len(o["query"]) > 1)
    print(f"rows where the rewrite itself varied:            {reworded or 'none'}")


if __name__ == "__main__":
    main()
