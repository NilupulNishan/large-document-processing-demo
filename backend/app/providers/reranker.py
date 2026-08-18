"""Cross-encoder boundary. ONNX on CPU. The gate reads these scores and no others (D3)."""

import os
from functools import cache

from app.config import MODELS_DIR, RERANK_MAX_TOKENS, RERANK_WINDOW_OVERLAP, RERANKER_MODEL

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


def rank(query: str, passages: list[str]) -> list[tuple[float, str]]:
    """
    Relevance of each passage to the query, judged jointly. Higher is better.

    A passage longer than the model's window is scored by its best window, not its first.
    Spec tables run to thousands of tokens and the answer is rarely in the opening rows.
    Returns that winning window's text with each score — it is the span the score was
    measured on, and the only part of a long passage the gate has evidence about.
    """
    if not passages:
        return []

    tokenizer, model = _model()
    inputs = tokenizer(
        [query] * len(passages),
        passages,
        padding=True,
        truncation="only_second",
        max_length=RERANK_MAX_TOKENS,
        stride=RERANK_WINDOW_OVERLAP,
        return_overflowing_tokens=True,
        return_offsets_mapping=True,
        return_tensors="np",
    )
    # One row per window; this maps each back to the passage it came from.
    windows = inputs.pop("overflow_to_sample_mapping")
    # Char spans into the passage, so a window can be cut back out of the original text.
    offsets = inputs.pop("offset_mapping")
    types = inputs["token_type_ids"]
    logits = model(**inputs).logits

    best = [(float("-inf"), "")] * len(passages)
    for row, passage, offset, kind in zip(logits, windows, offsets, types, strict=True):
        value = float(row[0])
        if value <= best[passage][0]:
            continue
        # token_type_ids marks the passage half; (0, 0) spans are specials and padding.
        spans = [o for o, t in zip(offset, kind, strict=True) if t == 1 and o[1] > o[0]]
        text = passages[passage][spans[0][0] : spans[-1][1]] if spans else passages[passage]
        best[passage] = (value, text)
    return best


def score(query: str, passages: list[str]) -> list[float]:
    """Scores alone, for callers that do not need the window text."""
    return [value for value, _ in rank(query, passages)]
