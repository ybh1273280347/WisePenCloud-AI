"""为 RetrievalChunk 生成可复用的检索上下文。"""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from typing import TYPE_CHECKING

from rag.domain.models.structure import DocumentStructure, StructureMode
from rag.domain.models.generation import GenerationCacheKind
from rag.domain.models.content import ReadingBlock
from rag.domain.repositories.mongo.generation_artifact_store import GenerationArtifactStore
from rag.domain.models.retrieval import RetrievalChunk
from rag.utils.xml_markup import xml_cdata

if TYPE_CHECKING:
    from rag.utils.llm_clients import QueryClient


_PROMPT_VERSION = "contextual-indexing:v1"
_RESPONSE_SCHEMA_VERSION = "contextual-text:v1"
_MAX_CONCURRENCY = 5

_SYSTEM_PROMPT = """\
You create one short retrieval context for a target passage from a private document.
The context is prepended to the target passage for dense and BM25 retrieval; it is
not an answer, a rewrite of the passage, or a general document summary.

Use the section path to name the document topic and the section preview and reading
block to resolve local references. Describe only what is supported by the supplied
target passage and reading block. Do not add outside knowledge, recommendations, or
facts that are only implied by the section title. Keep the target passage's primary
language and stay concise.

Return only a JSON object with this shape:
{"contextual_text": "..."}
"""


class ContextualTextIndexer:
    """为结构化文档的检索块生成上下文并增强 `index_text`。"""

    __slots__ = ("_cache", "_client")

    def __init__(
        self,
        *,
        client: QueryClient,
        cache: GenerationArtifactStore,
    ) -> None:
        self._client = client
        self._cache = cache

    async def contextualize(
        self,
        *,
        resource_id: str,
        structure: DocumentStructure,
        reading_blocks: list[ReadingBlock],
        chunks: list[RetrievalChunk],
    ) -> list[RetrievalChunk]:
        """生成上下文并返回增强后的 chunk；flat_text/empty 不调用模型。"""
        if not chunks or structure.mode in (StructureMode.FLAT_TEXT, StructureMode.EMPTY):
            return list(chunks)

        sections_by_id = {section.section_id: section for section in structure.sections}
        blocks_by_id = {block.block_id: block for block in reading_blocks}
        chunk_contexts: dict[str, RetrievalChunk] = {}
        section_previews: dict[str, str] = {}
        for chunk in chunks:
            section = sections_by_id.get(chunk.section_id)
            if section is None:
                raise ValueError(f"retrieval chunk {chunk.chunk_id} has no section")
            if chunk.section_path != section.section_path:
                raise ValueError(f"retrieval chunk {chunk.chunk_id} has invalid section path")
            if chunk.reading_block_id not in blocks_by_id:
                raise ValueError(
                    f"retrieval chunk {chunk.chunk_id} has no reading block"
                )
            section_previews[chunk.section_id] = section.preview
            chunk_contexts[
                self._cache_key(
                    chunk,
                    section.preview,
                    blocks_by_id[chunk.reading_block_id],
                )
            ] = chunk

        cached = {
            key: value.strip()
            for key, value in (
                await self._cache.get_many(
                    resource_id=resource_id,
                    cache_kind=GenerationCacheKind.CONTEXTUAL_TEXT,
                    keys=list(chunk_contexts),
                )
            ).items()
            if value.strip()
        }
        missing = [key for key in chunk_contexts if key not in cached]
        if missing:
            semaphore = asyncio.Semaphore(_MAX_CONCURRENCY)
            generated = await asyncio.gather(
                *(
                    self._generate(
                        chunk=chunk_contexts[key],
                        section_preview=section_previews[chunk_contexts[key].section_id],
                        reading_block=blocks_by_id[chunk_contexts[key].reading_block_id],
                        semaphore=semaphore,
                    )
                    for key in missing
                )
            )
            generated_by_key = dict(zip(missing, generated, strict=True))
            cached.update(generated_by_key)
            await self._cache.set_many(
                resource_id=resource_id,
                cache_kind=GenerationCacheKind.CONTEXTUAL_TEXT,
                values=generated_by_key,
            )

        contextualized_chunks: list[RetrievalChunk] = []
        for chunk in chunks:
            key = self._cache_key(
                chunk,
                section_previews[chunk.section_id],
                blocks_by_id[chunk.reading_block_id],
            )
            contextualized_chunks.append(
                chunk.with_contextual_text(cached[key])
            )
        return contextualized_chunks

    async def _generate(
        self,
        *,
        chunk: RetrievalChunk,
        section_preview: str,
        reading_block: ReadingBlock,
        semaphore: asyncio.Semaphore,
    ) -> str:
        async with semaphore:
            response = await self._client.aquery(
                _build_prompt(chunk, section_preview, reading_block),
                system_prompt=_SYSTEM_PROMPT,
                max_tokens=256,
                response_format={"type": "json_object"},
            )

        payload = json.loads(response.content)
        if not isinstance(payload, dict):
            raise TypeError("contextual text response is not a JSON object")
        contextual_text = payload.get("contextual_text")
        if not isinstance(contextual_text, str) or not contextual_text.strip():
            raise ValueError("contextual_text is missing")
        return contextual_text.strip()

    def _cache_key(
        self,
        chunk: RetrievalChunk,
        section_preview: str,
        reading_block: ReadingBlock,
    ) -> str:
        input_fingerprint = "\0".join(
            (
                _PROMPT_VERSION,
                _RESPONSE_SCHEMA_VERSION,
                self._client.model,
                self._client.thinking or "default",
                "\n".join(chunk.section_path),
                section_preview,
                reading_block.raw_text,
                chunk.raw_text,
                chunk.index_text,
            )
        )
        return sha256(input_fingerprint.encode("utf-8")).hexdigest()


def _build_prompt(
    chunk: RetrievalChunk,
    section_preview: str,
    reading_block: ReadingBlock,
) -> str:
    return "\n".join(
        (
            "<contextual_indexing_request>",
            (
                "<task>Create one concise context for the target retrieval chunk. "
                "State what it is about and how it fits the section. "
                "Do not answer a question.</task>"
            ),
            f"<section_path>{xml_cdata(' > '.join(chunk.section_path) or '(document root)')}</section_path>",
            f"<section_preview>{xml_cdata(section_preview)}</section_preview>",
            f"<section_reading_block>{xml_cdata(reading_block.raw_text)}</section_reading_block>",
            f"<target_retrieval_chunk>{xml_cdata(chunk.raw_text)}</target_retrieval_chunk>",
            "</contextual_indexing_request>",
        )
    )
