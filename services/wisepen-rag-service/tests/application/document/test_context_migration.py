import asyncio
from unittest.mock import Mock

import pytest

from rag.application.document.context import ContextMigrationRequired
from rag.application.document.indexing import DocumentIndexBuilder
from rag.application.retrieval.hybrid_retriever import HybridRetriever


def _builder(enabled):
    return DocumentIndexBuilder(
        documents=Mock(),
        doc_chunks=Mock(),
        resource_acls=Mock(),
        index_states=Mock(),
        publication=Mock(),
        document_vectors=Mock(),
        chat_client=Mock(),
        embedding_client=Mock(),
        query_model="unused",
        embedding_model="unused",
        embedding_dimensions=3,
        llm_semaphore=asyncio.Semaphore(1),
        embedding_semaphore=asyncio.Semaphore(1),
        enhancement_enabled=enabled,
    )


def test_enhancement_gate_fails_even_without_pending_chunks():
    with pytest.raises(ContextMigrationRequired, match="enhancement_enabled=False"):
        asyncio.run(_builder(True)._enhance(Mock(), []))


def test_disabled_enhancement_passes_raw_chunks():
    chunks = [Mock(raw_text="raw", retrieval_context="")]
    assert asyncio.run(_builder(False)._enhance(Mock(), chunks)) == chunks


def test_dynamic_parents_have_explicit_migration_error():
    with pytest.raises(ContextMigrationRequired, match="ContextExpander"):
        HybridRetriever._build_dynamic_parents()
