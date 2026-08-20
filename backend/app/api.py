"""HTTP boundary. Owns request shapes and SSE framing; orchestration lives in the pipeline."""

import json
import logging
import queue
import threading
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from app import db
from app.config import MANUALS_DIR, MAX_AUDIO_BYTES
from app.pipeline import build_pipeline
from app.providers import azure_speech as speech

logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    """Load the cross-encoder before serving. Left lazy it costs the first question ~6.5 s."""
    from app.providers.reranker import score

    started = time.perf_counter()
    score("warmup", ["warmup"])
    logger.info("reranker ready in %.1f s", time.perf_counter() - started)
    yield


app = FastAPI(title="Manual assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_pipeline = build_pipeline()

_DONE = object()  # sentinel: the worker has finished and the queue will yield nothing more


class NewSession(BaseModel):
    manual: str


class Ask(BaseModel):
    session_id: str
    question: str


class EscalationStatus(BaseModel):
    status: Literal["open", "picked_up", "closed"]


class AgentReply(BaseModel):
    text: str


@app.get("/manuals")
def manuals() -> list[dict]:
    return db.list_manuals()


@app.get("/manuals/{manual_id}/pdf")
def manual_pdf(manual_id: str) -> FileResponse:
    manual = db.get_manual(manual_id)
    if manual is None:
        raise HTTPException(404, "No such manual")
    return FileResponse(MANUALS_DIR / manual["filename"], media_type="application/pdf")


@app.post("/sessions")
def new_session(body: NewSession) -> dict:
    if db.get_manual(body.manual) is None:
        raise HTTPException(404, "No such manual")
    # Titled on the first question instead; a session with no messages has no subject yet.
    return db.create_session(body.manual, "New conversation")


@app.get("/sessions")
def sessions() -> list[dict]:
    return db.list_sessions()


@app.get("/sessions/{session_id}")
def session(session_id: str) -> dict:
    found = db.get_session(session_id)
    if found is None:
        raise HTTPException(404, "No such session")
    return {
        **found,
        "messages": db.list_messages(session_id),
        # The same check POST /chat makes, so the screen and the pipeline can never
        # disagree about whether a person currently owns this conversation. A closed
        # handoff hands it back, and the client has to be able to see that.
        "handed_over": db.open_escalation_for_session(session_id) is not None,
    }


@app.delete("/sessions/{session_id}")
def remove_session(session_id: str) -> dict:
    """Deletes the conversation, its messages and any handoff raised from it."""
    if db.get_session(session_id) is None:
        raise HTTPException(404, "No such session")
    return db.delete_session(session_id)


@app.get("/escalations")
def escalations(status: str | None = None) -> list[dict]:
    return db.list_escalations(status)


@app.get("/escalations/{escalation_id}")
def escalation(escalation_id: str) -> dict:
    """The whole handoff package, so nobody has to ask the user to start again (D14)."""
    found = db.get_escalation(escalation_id)
    if found is None:
        raise HTTPException(404, "No such escalation")
    return found


@app.post("/escalations/{escalation_id}/reply")
def reply(escalation_id: str, body: AgentReply) -> dict:
    """An agent's turn, written into the user's own conversation (D24)."""
    found = db.get_escalation(escalation_id)
    if found is None:
        raise HTTPException(404, "No such escalation")
    # Closing hands the conversation back to the pipeline, so a reply after that would
    # arrive as a person speaking into a conversation no person is in. Enforced here, not
    # only in the screen: the rule belongs with the data.
    if found["status"] == "closed":
        raise HTTPException(409, "This handoff is closed. Reopen it before replying.")
    if not body.text.strip():
        raise HTTPException(422, "An empty reply is not a reply")
    return db.add_message(found["session_id"], "agent", body.text.strip())


@app.patch("/escalations/{escalation_id}")
def update_escalation(escalation_id: str, body: EscalationStatus) -> dict:
    if db.get_escalation(escalation_id) is None:
        raise HTTPException(404, "No such escalation")
    db.set_escalation_status(escalation_id, body.status)
    return db.get_escalation(escalation_id)


@app.post("/transcribe")
async def transcribe(request: Request) -> dict:
    """Spoken audio to text. The text is returned, never sent — the user edits it first (D35)."""
    audio = await request.body()
    if not audio:
        raise HTTPException(400, "No audio")
    if len(audio) > MAX_AUDIO_BYTES:
        raise HTTPException(413, "Recording too long")

    content_type = request.headers.get("content-type", "")
    try:
        # Blocking call on a worker thread, as the pipeline already is.
        text = await run_in_threadpool(speech.transcribe, audio, content_type)
    except ValueError as error:
        raise HTTPException(415, str(error)) from error
    except RuntimeError as error:
        logger.warning("transcription failed: %s", error)
        raise HTTPException(502, str(error)) from error
    return {"text": text}


@app.get("/speech/token")
def speech_token() -> dict:
    """Short-lived credentials for the browser recogniser. The key stays here (D36)."""
    try:
        token, region = speech.issue_token()
    except RuntimeError as error:
        logger.warning("speech token failed: %s", error)
        raise HTTPException(502, str(error)) from error
    return {"token": token, "region": region}


def _frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@app.post("/chat")
def chat(body: Ask) -> StreamingResponse:
    found = db.get_session(body.session_id)
    if found is None:
        raise HTTPException(404, "No such session")

    # Read before writing, so the turn being asked is not in its own history.
    history = db.list_messages(body.session_id)
    db.add_message(body.session_id, "user", body.question)
    if found["title"] == "New conversation":
        db.rename_session(body.session_id, body.question)

    # A person has this conversation, so the assistant stays out of it (D24). The message is
    # stored for the agent to read; no step of the pipeline runs.
    handover = db.open_escalation_for_session(body.session_id)
    if handover:
        return StreamingResponse(
            iter([_frame("handover", {"escalation_id": handover["id"]})]),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _run(
            body.session_id,
            found["manual_id"],
            body.question,
            history,
            found.get("unresolved_streak", 0),
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _run(
    session_id: str, manual: str, question: str, history: list[dict], streak: int
) -> Iterator[str]:
    """Drive the pipeline on a worker thread and forward its events as they happen.

    The pipeline is synchronous by design, so the queue — not async — is what makes a step
    event reach the browser while the next step is still running.
    """
    events: queue.Queue = queue.Queue()

    def work() -> None:
        try:
            ctx = _pipeline.run(
                question,
                manual,
                sink=lambda kind, data: events.put((kind, data)),
                session_id=session_id,
                history=history,
                unresolved_streak=streak,
            )
            # Persisted here, not in a step: the pipeline counts, the boundary stores (D14).
            if ctx.unresolved_streak != streak:
                db.set_unresolved_streak(session_id, ctx.unresolved_streak)
            if ctx.escalation is not None:
                db.add_message(
                    session_id,
                    "assistant",
                    ctx.escalation["message"],
                    escalation_id=ctx.escalation["id"],
                )
                events.put(("escalated", ctx.escalation))
            elif ctx.answer is None:
                events.put(("error", {"message": "The pipeline produced no answer."}))
            else:
                answer = ctx.answer
                db.add_message(
                    session_id,
                    "assistant",
                    answer.answer,
                    answer.source,
                    answer.format,
                    [c.model_dump(exclude_none=True) for c in answer.citations],
                )
                events.put(("done", answer.model_dump(exclude_none=True)))
        except Exception as error:  # a dead stream is indistinguishable from a slow one
            logger.exception("pipeline failed")
            events.put(("error", {"message": str(error)}))
        finally:
            events.put(_DONE)

    threading.Thread(target=work, daemon=True).start()

    while (item := events.get()) is not _DONE:
        kind, data = item
        yield _frame(kind, data)
