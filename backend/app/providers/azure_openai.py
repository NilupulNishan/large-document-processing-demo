"""Azure OpenAI boundary. SDK types stop here; callers receive plain lists."""

import json
from collections.abc import Callable
from functools import cache

from openai import BadRequestError, ContentFilterFinishReasonError
from pydantic import BaseModel

from app.config import (
    AZURE_OPENAI_API_KEY,
    AZURE_OPENAI_API_VERSION,
    AZURE_OPENAI_CHAT_DEPLOYMENT,
    AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
    AZURE_OPENAI_ENDPOINT,
    EMBED_BATCH_SIZE,
)


@cache
def _client():
    missing = [
        name
        for name, value in (
            ("AZURE_OPENAI_ENDPOINT", AZURE_OPENAI_ENDPOINT),
            ("AZURE_OPENAI_API_KEY", AZURE_OPENAI_API_KEY),
            ("AZURE_OPENAI_API_VERSION", AZURE_OPENAI_API_VERSION),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(f"Missing in backend/.env: {', '.join(missing)}")

    from openai import AzureOpenAI

    return AzureOpenAI(
        api_version=AZURE_OPENAI_API_VERSION,
        azure_endpoint=AZURE_OPENAI_ENDPOINT,
        api_key=AZURE_OPENAI_API_KEY,
    )


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Embed in batches. Results are re-sorted by index — a silent reorder would
    attach every vector to the wrong chunk."""
    if not AZURE_OPENAI_EMBEDDING_DEPLOYMENT:
        raise RuntimeError("Missing in backend/.env: AZURE_OPENAI_EMBEDDING_DEPLOYMENT")

    vectors: list[list[float]] = []
    for start in range(0, len(texts), EMBED_BATCH_SIZE):
        response = _client().embeddings.create(
            model=AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
            input=texts[start : start + EMBED_BATCH_SIZE],
        )
        vectors.extend(item.embedding for item in sorted(response.data, key=lambda i: i.index))
    return vectors


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def complete[T: BaseModel](system: str, user: str, schema: type[T], temperature: float = 0.0) -> T:
    """
    Structured completion. Raises if the model returns nothing parseable.

    Temperature 0 by default: at the API default of 1 the grader returned different verdicts
    for identical inputs, which moved 4 of 15 questions to a different route (Slice 10).
    """
    if not AZURE_OPENAI_CHAT_DEPLOYMENT:
        raise RuntimeError("Missing in backend/.env: AZURE_OPENAI_CHAT_DEPLOYMENT")

    response = _client().chat.completions.parse(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
        temperature=temperature,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError(f"{AZURE_OPENAI_CHAT_DEPLOYMENT} returned no parseable output")
    return parsed


def complete_or_none[T: BaseModel](system: str, user: str, schema: type[T]) -> T | None:
    """
    None when Azure's content filter rejects the call, so the caller can degrade (D28).

    Two different failures, and both are reachable: the prompt is rejected with a 400 before
    the model runs, or the response comes back 200 with finish_reason=content_filter. Any
    other BadRequestError is a real fault and is re-raised.
    """
    try:
        return complete(system, user, schema)
    except ContentFilterFinishReasonError:
        return None
    except BadRequestError as error:
        if error.code != "content_filter":
            raise
        return None


def _prose_so_far(buffer: str, field: str) -> str | None:
    """The value of `field` as far as it has arrived, or None if it cannot be read yet.

    Deltas carry raw JSON, so the string is still escaped and unterminated. Closing it and
    handing it to json.loads unescapes \\n, \\" and \\uXXXX for free; mid-escape buffers
    simply fail to parse and are skipped until the next delta completes them.
    """
    start = buffer.find(f'"{field}":"')
    if start < 0:
        return None
    segment = buffer[start + len(field) + 4 :]

    # The first unescaped quote ends the value; anything after it belongs to other fields.
    end, escaped = len(segment), False
    for index, character in enumerate(segment):
        if escaped:
            escaped = False
        elif character == "\\":
            escaped = True
        elif character == '"':
            end = index
            break

    try:
        return json.loads(f'"{segment[:end]}"')
    except json.JSONDecodeError:
        return None


def complete_stream[T: BaseModel](
    system: str,
    user: str,
    schema: type[T],
    on_token: Callable[[str], None],
    field: str = "answer",
    temperature: float = 0.0,
) -> T:
    """Structured completion that streams one field's prose as it arrives (D9)."""
    if not AZURE_OPENAI_CHAT_DEPLOYMENT:
        raise RuntimeError("Missing in backend/.env: AZURE_OPENAI_CHAT_DEPLOYMENT")

    buffer, sent = "", ""
    with _client().chat.completions.stream(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
        temperature=temperature,
    ) as stream:
        for event in stream:
            if event.type != "content.delta":
                continue
            buffer += event.delta
            prose = _prose_so_far(buffer, field)
            if prose is not None and prose != sent:
                on_token(prose[len(sent) :])
                sent = prose

        parsed = stream.get_final_completion().choices[0].message.parsed

    if parsed is None:
        raise RuntimeError(f"{AZURE_OPENAI_CHAT_DEPLOYMENT} returned no parseable output")
    return parsed
