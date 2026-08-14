"""LanceDB boundary. LanceDB types stop here; callers pass and receive plain dicts."""

import lancedb
from lancedb.pydantic import LanceModel, Vector
from lancedb.rerankers import RRFReranker

from app.config import (
    CHUNKS_TABLE,
    EMBEDDING_DIMENSIONS,
    LANCEDB_DIR,
    RRF_K,
)


class ChunkRecord(LanceModel):
    chunk_id: str
    manual: str
    text: str
    heading_path: str
    pages_pdf: list[int]
    # Empty, never null, when a manual has no detected page offset (D6).
    pages_printed: list[int]
    vector: Vector(EMBEDDING_DIMENSIONS)


def _quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def write_chunks(rows: list[dict]) -> int:
    """Replace one manual's rows, leaving the others intact, then rebuild the text index."""
    database = lancedb.connect(LANCEDB_DIR)
    manual = rows[0]["manual"]

    if CHUNKS_TABLE in database.table_names():
        table = database.open_table(CHUNKS_TABLE)
        table.delete(f"manual = {_quote(manual)}")
        table.add(rows)
    else:
        table = database.create_table(CHUNKS_TABLE, rows, schema=ChunkRecord)

    table.create_fts_index("text", replace=True)
    return table.count_rows()


def search(
    manual: str, query: str, query_vector: list[float], limit: int
) -> list[dict]:
    """Dense and full-text in parallel, fused with RRF (D3), scoped to one manual (D11)."""
    table = lancedb.connect(LANCEDB_DIR).open_table(CHUNKS_TABLE)
    return (
        table.search(query_type="hybrid")
        .vector(query_vector)
        .text(query)
        .where(f"manual = {_quote(manual)}", prefilter=True)
        .limit(limit)
        .rerank(RRFReranker(K=RRF_K))
        .to_list()
    )
