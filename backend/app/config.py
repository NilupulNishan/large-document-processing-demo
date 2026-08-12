"""Application settings. Environment values are read only here."""

EMBEDDING_MODEL = "text-embedding-3-large"
MAX_EMBEDDING_TOKENS = 8191

# Merge targets. Rationale and measurements in docs/build-log.md, Slice 2.
TARGET_CHUNK_TOKENS = 450
MAX_PAGE_SPAN = 3
