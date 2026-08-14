"""
Drive the running API and read the SSE frames as they arrive. Start the server first:

    uv run --project backend uvicorn app.api:app --app-dir backend
    uv run --project backend python playground/check_api.py
"""

import json
import sys
import time
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

BASE = "http://127.0.0.1:8000"

QUESTIONS = [
    "How do I pair my phone with the car's bluetooth?",  # manual, high score
    "What engine oil does it take and how many litres?",  # manual, via the grader
    "Where is my nearest BAIC service centre?",  # general
    "What is the weather forecast for tomorrow?",  # decline
]


def call(path: str, body: dict | None = None) -> dict | list:
    request = urllib.request.Request(
        f"{BASE}{path}",
        data=json.dumps(body).encode() if body else None,
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(request) as response:
        return json.loads(response.read())


def ask(session_id: str, question: str) -> None:
    """Print each frame as it lands, with the gap since the previous one."""
    request = urllib.request.Request(
        f"{BASE}/chat",
        data=json.dumps({"session_id": session_id, "question": question}).encode(),
        headers={"Content-Type": "application/json"},
    )
    print(f"\n{'=' * 78}\n{question}\n{'=' * 78}")

    started = last = time.perf_counter()
    tokens = 0
    with urllib.request.urlopen(request) as response:
        event = None
        for raw in response:
            line = raw.decode("utf-8").rstrip("\n")
            if line.startswith("event: "):
                event = line[7:]
            elif line.startswith("data: "):
                now = time.perf_counter()
                data = json.loads(line[6:])
                if event == "token":
                    tokens += 1
                    if tokens == 1:
                        print(f"  [{now - started:5.2f}s] first token")
                elif event == "step":
                    print(f"  [{now - started:5.2f}s] +{now - last:4.2f}s  step  {data['label']}")
                elif event == "done":
                    print(f"  [{now - started:5.2f}s] done  source={data['source']} "
                          f"format={data['format']} resolved={data['resolved']} "
                          f"tokens={tokens} citations={len(data.get('citations', []))}")
                elif event == "error":
                    print(f"  [{now - started:5.2f}s] ERROR {data['message']}")
                last = now


def main() -> None:
    try:
        available = call("/manuals")
    except urllib.error.URLError:
        raise SystemExit("Server not running — start uvicorn first (see the docstring).") from None

    print("manuals:")
    for manual in available:
        print(f"  {manual['id']}  {manual['page_count']} pages  offset {manual['page_offset']}")

    session = call("/sessions", {"manual": available[0]["id"]})
    print(f"\nsession {session['id']} on {session['manual_id']}")

    for question in QUESTIONS:
        ask(session["id"], question)

    # Reopen it: the history panel depends on this returning everything with citations intact.
    stored = call(f"/sessions/{session['id']}")
    print(f"\n{'=' * 78}\nreopened '{stored['title']}' — {len(stored['messages'])} messages")
    for message in stored["messages"]:
        note = f" [{message['source']}]" if message["source"] else ""
        cites = "".join(
            f" p{c.get('page_printed') or c.get('page_pdf')}" for c in message["citations"]
        )
        print(f"  {message['role']:9}{note}{cites}  {message['content'][:60]!r}")


if __name__ == "__main__":
    main()
