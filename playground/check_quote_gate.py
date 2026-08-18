"""
Can the bypass be closed with a checkable fact instead of a judgement?

check_grader.py measured vetoing a confident score on the grader's two booleans: it fixes the
two dangerous rows and breaks three the manual answers, because `safety_topic` is true of most
vehicle questions and `passages_answer_the_question` false-negatives too often.

This asks the grader to quote the sentence carrying the answer, and Python checks the quote is
really in the passages. Above the band a safety topic escalates only when nothing can be quoted.

    uv run --project backend python playground/check_quote_gate.py
"""

import json
import re
import sys
from collections import Counter
from pathlib import Path

from pydantic import BaseModel

sys.stdout.reconfigure(encoding="utf-8")
sys.path.append(str((REPO_ROOT := Path(__file__).resolve().parents[1]) / "backend"))

from app.config import (  # noqa: E402
    DOMAIN_DESCRIPTION,
    GATE_HIGH,
    RERANK_CANDIDATES,
    RERANK_KEEP,
    SAFETY_TOPICS,
    UNRESOLVED_ESCALATE,
)
from app.pipeline.gate import _SYSTEM, decide  # noqa: E402
from app.pipeline.resolve import next_streak, read  # noqa: E402
from app.providers.azure_openai import complete, embed_query  # noqa: E402
from app.providers.lancedb_store import search  # noqa: E402
from app.providers.reranker import rank  # noqa: E402

RUNS = 3

# Every row. An 11-row sample missed bj30-17, which asks "how deep" of a manual that never
# states a depth — exactly the class this policy acts on.
CASES: tuple[str, ...] = ()

_QUOTE = """

`asks_for_a_specific_value` — read the question on its own and ignore the passages entirely
when answering this one. Would a complete answer have to state a particular number, rating,
capacity, grade or setting? "What torque", "what pressure", "how much", "how many", "how deep",
"what grade" all require one, and they still require one when the passages happen not to state
it — that the passages are silent is what the other fields are for. A question asking for a
sequence of steps, or for an account of how something works, does not require one.

When it does, copy into `answer_quote` the exact sentence or table row from the passages that
states that value, word for word, so it can be checked against them. If nothing in the passages
states it, leave `answer_quote` empty. Never write a sentence that is not there."""


class Quoted(BaseModel):
    passages_answer_the_question: bool
    question_is_about_the_domain: bool
    question_touches_a_safety_topic: bool
    asks_for_a_specific_value: bool
    answer_quote: str


def _flat(text: str) -> str:
    return re.sub(r"\s+", "", text).lower()


def grade(question: str, passages: list[dict]) -> Quoted:
    excerpts = "\n\n".join(f"[{i}] {p['excerpt'][:600]}" for i, p in enumerate(passages, 1))
    topics = ", ".join(SAFETY_TOPICS) or "none configured"
    return complete(
        _SYSTEM + _QUOTE,
        f"Domain: {DOMAIN_DESCRIPTION}\nSafety topics: {topics}\n\n"
        f"Question: {question}\n\nPassages:\n{excerpts}",
        Quoted,
    )


def main() -> None:
    rows = {
        r["id"]: r
        for r in (
            json.loads(line)
            for line in (REPO_ROOT / "eval" / "questions.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
            if line.strip()
        )
        if not CASES or r["id"] in CASES
    }

    print(f"{RUNS} runs each. Above GATE_HIGH: escalate only if safety and nothing quotable.\n")
    fixed = broken = 0

    for rid, row in rows.items():
        query, person = row["question"], False
        streak = row.get("streak", 0)
        if row.get("history"):
            turn = read(row["question"], row["history"])
            query = f"{turn.standalone_question} {row['question']}"
            person = turn.asks_for_a_person
            streak = next_streak(streak, turn.progress)

        hits = search(row["manual"], query, embed_query(query), limit=RERANK_CANDIDATES)
        scored = rank(query, [h["text"] for h in hits])
        ordered = [
            h | {"excerpt": excerpt}
            for (_, excerpt), h in sorted(zip(scored, hits, strict=True), key=lambda p: -p[0][0])
        ]
        top = max(value for value, _ in scored)
        passages = ordered[:RERANK_KEEP]
        haystack = _flat("".join(p["excerpt"][:600] for p in passages))

        routes: Counter[str] = Counter()
        today: Counter[str] = Counter()
        quotes = []
        for _ in range(RUNS):
            v = grade(query, passages)
            ok = bool(v.answer_quote) and _flat(v.answer_quote) in haystack
            quotes.append((ok, v.answer_quote, v))
            if person or streak >= UNRESOLVED_ESCALATE:
                # D14's triggers run ahead of the band in decide(); the experiment must too.
                route = "escalate"
            elif top > GATE_HIGH:
                # Only a value question can be checked this way: a procedure has no one
                # sentence carrying its answer, so an absent quote proves nothing about it.
                missing = v.asks_for_a_specific_value and not ok
                route = "escalate" if (v.question_touches_a_safety_topic and missing) else "manual"
            else:
                route = decide(top, v, streak, person)
            routes[route] += 1
            today[decide(top, v if top <= GATE_HIGH else None, streak, person)] += 1

        want = row["expected_route"]
        was, now = today[want] == RUNS, routes[want] == RUNS
        fixed += now and not was
        broken += was and not now
        if dict(today) != dict(routes) or not now:
            mark = "ok" if now else ("BREAK" if was else "     ")
            print(
                f"{mark:5} {rid:9} {top:+7.2f} want {want:10} "
                f"today {dict(today)} quoted {dict(routes)}"
            )
            ok, text, v = quotes[0]
            state = "verified" if ok else ("NOT IN PASSAGES" if text else "none offered")
            print(f"       value={v.asks_for_a_specific_value} quote {state}: {text[:70]!r}")

    print(f"\nfixed {fixed}   newly broken {broken}   of {len(rows)}")


if __name__ == "__main__":
    main()
