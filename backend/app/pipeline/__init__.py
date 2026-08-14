"""Pipeline assembly. Adding a capability means adding a step here."""

from app.pipeline.answer import AnswerStep
from app.pipeline.base import Answer, Citation, Pipeline, PipelineContext, PipelineStep, Route
from app.pipeline.gate import GateStep, Verdict, decide
from app.pipeline.retrieve import RerankStep, RetrieveStep


def build_pipeline() -> Pipeline:
    """retrieve → rerank → gate → answer. resolve_query, web_search and escalate not built."""
    return Pipeline([RetrieveStep(), RerankStep(), GateStep(), AnswerStep()])


__all__ = [
    "Answer",
    "AnswerStep",
    "Citation",
    "GateStep",
    "Pipeline",
    "PipelineContext",
    "PipelineStep",
    "RerankStep",
    "RetrieveStep",
    "Route",
    "Verdict",
    "build_pipeline",
    "decide",
]
