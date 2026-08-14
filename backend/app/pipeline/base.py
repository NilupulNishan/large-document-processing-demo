"""Pipeline scaffolding. One class per step, assembled by build_pipeline()."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from typing import Literal, Protocol

from pydantic import BaseModel

logger = logging.getLogger(__name__)

Route = Literal["manual", "manual+general", "general", "decline", "escalate"]
Source = Literal["manual", "manual+general", "general"]


class Citation(BaseModel):
    """A page citation navigates the PDF pane; a web citation opens a URL (D13)."""

    type: Literal["page", "web"]
    page_pdf: int | None = None
    page_printed: int | None = None
    section: str | None = None
    url: str | None = None
    title: str | None = None


class Answer(BaseModel):
    format: Literal["direct", "steps", "troubleshoot", "explanation"]
    source: Source
    answer: str
    citations: list[Citation] = []
    resolved: bool


class PipelineContext(BaseModel):
    """State passed through every step. Each step adds to it and returns it."""

    question: str
    manual: str

    query: str = ""
    candidates: list[dict] = []
    passages: list[dict] = []
    top_score: float = 0.0

    route: Route | None = None
    answer: Answer | None = None

    # What actually ran, for the SSE step events. No step may append without running (D9).
    events: list[tuple[str, str]] = []

    def emit(self, step: str, label: str) -> None:
        self.events.append((step, label))


class PipelineStep(Protocol):
    name: str

    def run(self, ctx: PipelineContext) -> PipelineContext: ...


class Pipeline:
    def __init__(self, steps: Sequence[PipelineStep]) -> None:
        self.steps = list(steps)

    def run(self, question: str, manual: str) -> PipelineContext:
        ctx = PipelineContext(question=question, manual=manual)
        for index, step in enumerate(self.steps, start=1):
            logger.info("[%d/%d] %s", index, len(self.steps), step.name)
            ctx = step.run(ctx)
        return ctx
