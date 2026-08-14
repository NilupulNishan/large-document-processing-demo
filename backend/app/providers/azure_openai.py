"""Azure OpenAI boundary. SDK types stop here; callers receive plain lists."""

from functools import cache

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


def complete[T: BaseModel](system: str, user: str, schema: type[T]) -> T:
    """Structured completion. Raises if the model returns nothing parseable."""
    if not AZURE_OPENAI_CHAT_DEPLOYMENT:
        raise RuntimeError("Missing in backend/.env: AZURE_OPENAI_CHAT_DEPLOYMENT")

    response = _client().chat.completions.parse(
        model=AZURE_OPENAI_CHAT_DEPLOYMENT,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format=schema,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise RuntimeError(f"{AZURE_OPENAI_CHAT_DEPLOYMENT} returned no parseable output")
    return parsed
