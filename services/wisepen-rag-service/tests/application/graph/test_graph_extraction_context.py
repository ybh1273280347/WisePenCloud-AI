import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from rag.application.document.models import DocChunk
from rag.application.graph.graph_fact_builder import _chunk_source, _extract_chunk
from rag.application.plugins.core.ontology import Ontology


def test_extraction_request_only_contains_target_and_section_path():
    chunk = DocChunk(
        "c", "r", "rev", "s", 1, "target evidence", section_path=["background"]
    )
    create = AsyncMock()
    client = SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=create))
    )
    ontology = Ontology(domain="test")
    asyncio.run(
        _extract_chunk(
            client,
            model="model",
            chunk=chunk,
            ontology=ontology,
            semaphore=asyncio.Semaphore(1),
        )
    )
    messages = create.call_args.kwargs["messages"]
    assert "target evidence" in messages[1]["content"]
    assert "<section_path>" in messages[1]["content"]
    assert "<context_chunk" not in messages[1]["content"]
    assert "background for disambiguation only" in messages[0]["content"]


def test_source_attribution_points_to_target_chunk_identity():
    chunk = DocChunk("c", "r", "rev", "s", 1, "evidence", section_path=["title"])
    document = SimpleNamespace(
        resource_id="r", revision=SimpleNamespace(content_revision="rev")
    )
    source = _chunk_source(document, chunk, "node", "graph-node")
    assert source.chunk_id == "c"
    assert source.section_id == "s"
    assert source.content_revision == "rev"
