"""Docling boundary. Docling types stop here; callers receive plain domain objects."""

import os
from pathlib import Path

from app.config import EMBEDDING_MODEL, MAX_EMBEDDING_TOKENS
from app.ingestion.models import Chunk, ParsedManual

# Inductor needs a C++ compiler and Windows has none. Must precede docling's torch import.
os.environ.setdefault("TORCHDYNAMO_DISABLE", "1")


def _build_converter():
    from docling.datamodel.base_models import InputFormat
    from docling.datamodel.pipeline_options import PdfPipelineOptions
    from docling.document_converter import DocumentConverter, PdfFormatOption

    options = PdfPipelineOptions()
    options.do_ocr = False  # corpus is born-digital
    options.do_table_structure = True
    options.table_structure_options.do_cell_matching = True

    return DocumentConverter(
        format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=options)}
    )


def _markdown_tables():
    """
    Docling's default writes one sentence per cell, repeating the row label in every one:
    `Total mass of quasi-trailer (T), BJ6470X52MHEV = 1.5.` Neither the reranker nor the
    grader reads that as an answer. See build-log Slice 10.
    """
    from docling_core.transforms.chunker.hierarchical_chunker import (
        ChunkingDocSerializer,
        ChunkingSerializerProvider,
    )
    from docling_core.transforms.serializer.markdown import MarkdownTableSerializer

    class MarkdownTableProvider(ChunkingSerializerProvider):
        def get_serializer(self, doc):
            return ChunkingDocSerializer(doc=doc, table_serializer=MarkdownTableSerializer())

    return MarkdownTableProvider()


def _build_chunker():
    import tiktoken
    from docling.chunking import HybridChunker
    from docling_core.transforms.chunker.tokenizer.openai import OpenAITokenizer

    return HybridChunker(
        tokenizer=OpenAITokenizer(
            tokenizer=tiktoken.encoding_for_model(EMBEDDING_MODEL),
            max_tokens=MAX_EMBEDDING_TOKENS,
        ),
        merge_peers=True,
        serializer_provider=_markdown_tables(),
    )


def _pages(meta) -> tuple[int, ...]:
    return tuple(
        sorted(
            {
                prov.page_no
                for item in (getattr(meta, "doc_items", []) or [])
                for prov in (getattr(item, "prov", []) or [])
                if getattr(prov, "page_no", None) is not None
            }
        )
    )


def parse(pdf_path: Path, cache: Path | None = None) -> ParsedManual:
    """
    Convert, then chunk. Given a cache path the converted document is reused: conversion runs
    the layout models over every page and takes minutes, chunking takes seconds, and tuning
    the chunker is the only reason to run this twice.
    """
    from docling_core.types.doc.document import DoclingDocument

    if cache and cache.exists():
        document = DoclingDocument.load_from_json(cache)
    else:
        document = _build_converter().convert(pdf_path).document
        if cache:
            cache.parent.mkdir(parents=True, exist_ok=True)
            document.save_as_json(cache)

    chunks = tuple(
        Chunk(
            text=chunk.text,
            pages=_pages(chunk.meta),
            headings=tuple(getattr(chunk.meta, "headings", None) or ()),
        )
        for chunk in _build_chunker().chunk(dl_doc=document)
    )
    return ParsedManual(
        page_count=len(document.pages),
        chunks=chunks,
        full_text=document.export_to_markdown(),
    )
