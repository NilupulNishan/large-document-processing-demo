"""Cross-encoder boundary. ONNX on CPU. The gate reads these scores and no others (D3)."""

import os
from functools import cache

from app.config import MODELS_DIR, RERANK_MAX_TOKENS, RERANKER_MODEL

_ONNX_DIR = MODELS_DIR / RERANKER_MODEL.replace("/", "__")


@cache
def _model():
    """Export to ONNX once and keep it. Re-exporting on every start costs two minutes."""
    import onnxruntime
    from optimum.onnxruntime import ORTModelForSequenceClassification
    from transformers import AutoTokenizer

    if _ONNX_DIR.exists():
        source, export = _ONNX_DIR, False
    else:
        source, export = RERANKER_MODEL, True

    # ONNX Runtime does not reliably pick up all cores on its own here.
    options = onnxruntime.SessionOptions()
    options.intra_op_num_threads = os.cpu_count() or 4

    tokenizer = AutoTokenizer.from_pretrained(source)
    model = ORTModelForSequenceClassification.from_pretrained(
        source, export=export, session_options=options
    )

    if export:
        model.save_pretrained(_ONNX_DIR)
        tokenizer.save_pretrained(_ONNX_DIR)

    return tokenizer, model


def score(query: str, passages: list[str]) -> list[float]:
    """Relevance of each passage to the query, judged jointly. Higher is better."""
    if not passages:
        return []

    tokenizer, model = _model()
    inputs = tokenizer(
        [query] * len(passages),
        passages,
        padding=True,
        truncation=True,
        max_length=RERANK_MAX_TOKENS,
        return_tensors="np",
    )
    logits = model(**inputs).logits
    return [float(row[0]) for row in logits]
