"""Application settings. Environment values are read only here."""

import os
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_DIR.parent

load_dotenv(BACKEND_DIR / ".env")

CHUNKS_DIR = REPO_ROOT / "data" / "chunks"
MANUALS_DIR = REPO_ROOT / "data" / "manuals"
DB_PATH = REPO_ROOT / "data" / "app.db"
LANCEDB_DIR = REPO_ROOT / "data" / "lancedb"
MODELS_DIR = REPO_ROOT / "data" / "models"
CHUNKS_TABLE = "chunks"

EMBEDDING_MODEL = "text-embedding-3-large"
MAX_EMBEDDING_TOKENS = 8191
EMBEDDING_DIMENSIONS = 3072
EMBED_BATCH_SIZE = 64

# Retrieval. D3: fuse BM25 and dense with RRF at k=60. How many come back is
# RERANK_CANDIDATES below — one stage, not the two D3 originally described.
RRF_K = 60

# Reranking. The gate reads these scores and nothing else — RRF scores rank position,
# not relevance, and cannot separate a grounded question from a poem. See D3.
RERANKER_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
# 12 rather than D3's 30: Recall@10 is 100%, so the answer is always already in the
# top 10 and reranking the tail costs latency for nothing. See build-log Slice 5.
RERANK_CANDIDATES = 12
RERANK_KEEP = 6
RERANK_MAX_TOKENS = 512

# Gate bands, read off the reranker score distribution: observed ungrounded max -4.44,
# grounded min -7.21. Set outside those, not on them — pinned to the exact extremes, the
# lowest grounded question falls below LOW and gets declined. Widening only costs a
# grader call; narrowing misroutes. Between the bands the grader decides (D2).
GATE_HIGH = -4.1
GATE_LOW = -7.5

# Merge targets. Rationale and measurements in docs/build-log.md, Slice 2.
TARGET_CHUNK_TOKENS = 450
MAX_PAGE_SPAN = 3

# Read, not required. Missing values fail in the provider that needs them, so tools
# with no network dependency still import this module.
AZURE_OPENAI_ENDPOINT = os.getenv("AZURE_OPENAI_ENDPOINT", "")
AZURE_OPENAI_API_KEY = os.getenv("AZURE_OPENAI_API_KEY", "")
AZURE_OPENAI_API_VERSION = os.getenv("AZURE_OPENAI_API_VERSION", "")
AZURE_OPENAI_CHAT_DEPLOYMENT = os.getenv("AZURE_OPENAI_CHAT_DEPLOYMENT", "")
AZURE_OPENAI_EMBEDDING_DEPLOYMENT = os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", "")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY", "")
DOMAIN_DESCRIPTION = os.getenv("DOMAIN_DESCRIPTION", "")
# Corpus knowledge, not code. See D13 and backend/.env.example.
SAFETY_TOPICS = tuple(t.strip() for t in os.getenv("SAFETY_TOPICS", "").split(",") if t.strip())
# Empty means the open web. Goes to Tavily as include_domains — never into the query text
# as a site: operator, which is how the previous build turned it into noise tokens.
WEB_DOMAINS = tuple(d.strip() for d in os.getenv("WEB_DOMAINS", "").split(",") if d.strip())

WEB_RESULTS = 4
