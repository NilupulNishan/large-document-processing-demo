"""Pipeline assembly. Adding a capability means adding a step here."""

from app.pipeline.answer import AnswerStep
from app.pipeline.base import Answer, Citation, Pipeline, PipelineContext, PipelineStep, Route
from app.pipeline.escalate import EscalateStep
from app.pipeline.gate import GateStep, Verdict, decide
from app.pipeline.retrieve import RerankStep, RetrieveStep
from app.pipeline.web import WebSearchStep


def build_pipeline() -> Pipeline:
    """retrieve → rerank → gate → web → answer → escalate. resolve_query not built."""
    return Pipeline(
        [RetrieveStep(), RerankStep(), GateStep(), WebSearchStep(), AnswerStep(), EscalateStep()]
    )


__all__ = [
    "Answer",
    "AnswerStep",
    "Citation",
    "EscalateStep",
    "GateStep",
    "Pipeline",
    "PipelineContext",
    "PipelineStep",
    "RerankStep",
    "RetrieveStep",
    "Route",
    "Verdict",
    "WebSearchStep",
    "build_pipeline",
    "decide",
]
