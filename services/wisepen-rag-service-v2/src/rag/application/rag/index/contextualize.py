"""为 RetrievalChunk 生成可复用的检索上下文。

实现的是 Contextual Retrieval 思路：在向量/BM25 索引前，给每个 chunk 注入一段
由 LLM 生成的“上下文文本”，描述该 chunk 在文档中的位置与主题，以提升召回精度。

关键设计：
- 上下文按 ``artifact_key`` 哈希持久化到 ``GenerationArtifactStore``，重复索引时直接复用，
  避免重复消耗 LLM 调用。
- ``artifact_key`` 涵盖 prompt 版本、响应 schema 版本、模型 ID、thinking 配置、
  章节、section preview、reading block 文本、chunk 文本等多个维度，任何输入变化都会
  让 key 改变，强制重新生成。
- FLAT_TEXT/EMPTY 文档不调用模型（无足够上下文意义），直接返回原 chunk。
"""

from __future__ import annotations

import asyncio
import json
from hashlib import sha256
from typing import TYPE_CHECKING

from rag.domain.models.content import ReadingBlock
from rag.domain.models.retrieval import RetrievalChunk
from rag.domain.models.structure import DocumentStructure, StructureMode
from rag.domain.repositories.mongo.generation_artifact_store import (
    GenerationArtifactStore,
)
from rag.utils.xml_markup import xml_cdata

if TYPE_CHECKING:
    from rag.utils.llm_clients import QueryClient


# Prompt 与响应 schema 的版本号；任一变更都会让旧 artifact key 失效，强制重新生成。
_PROMPT_VERSION = "contextual-indexing:v1"
_RESPONSE_SCHEMA_VERSION = "contextual-text:v1"
# 单次并发调用 LLM 的上限，避免大批量 chunk 同时打爆模型 API。
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

    __slots__ = ("_artifact_store", "_client")

    def __init__(
        self,
        *,
        client: QueryClient,
        artifact_store: GenerationArtifactStore,
    ) -> None:
        self._client = client
        self._artifact_store = artifact_store

    async def contextualize(
        self,
        *,
        resource_id: str,
        structure: DocumentStructure,
        reading_blocks: list[ReadingBlock],
        chunks: list[RetrievalChunk],
    ) -> list[RetrievalChunk]:
        """生成上下文并返回增强后的 chunk；flat_text/empty 不调用模型。

        流程：
        1. 校验每个 chunk 的 section/reading_block 归属一致性。
        2. 为每个 chunk 计算 artifact_key，并尝试从 artifact_store 批量命中已缓存的上下文。
        3. 缺失的 chunk 并发调用 LLM 生成上下文（信号量限流），生成后写回 artifact_store。
        4. 用命中或新生成的上下文重写每个 chunk 的 ``index_text``，返回新列表。
        """
        # FLAT_TEXT/EMPTY 缺乏章节上下文，生成意义不大，直接透传。
        if not chunks or structure.mode in (StructureMode.FLAT_TEXT, StructureMode.EMPTY):
            return list(chunks)

        sections_by_id = {section.section_id: section for section in structure.sections}
        blocks_by_id = {block.block_id: block for block in reading_blocks}
        chunk_contexts: dict[str, RetrievalChunk] = {}
        section_previews: dict[str, str] = {}
        for chunk in chunks:
            # 归属一致性校验：chunk 必须挂在已存在的 section 与 reading_block 上。
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
            # artifact_key 作为缓存键，与 chunk 一一对应。
            chunk_contexts[
                self._artifact_key(
                    chunk,
                    section.preview,
                    blocks_by_id[chunk.reading_block_id],
                )
            ] = chunk

        # 批量读取已持久化的上下文，过滤掉空值。
        stored_contexts = {
            key: value.strip()
            for key, value in (
                await self._artifact_store.get_many(
                    resource_id=resource_id,
                    artifact_kind="context",
                    artifact_keys=list(chunk_contexts),
                )
            ).items()
            if value.strip()
        }
        missing = [key for key in chunk_contexts if key not in stored_contexts]
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
            # missing 与 generated 顺序一致，可严格 zip 成 dict。
            generated_by_key = dict(zip(missing, generated, strict=True))
            stored_contexts.update(generated_by_key)
            # 新生成的上下文写回缓存，供后续重复索引复用。
            await self._artifact_store.set_many(
                resource_id=resource_id,
                artifact_kind="context",
                artifacts=generated_by_key,
            )

        # 用上下文重写每个 chunk 的 index_text，返回新列表（原 chunk 不变）。
        contextualized_chunks: list[RetrievalChunk] = []
        for chunk in chunks:
            key = self._artifact_key(
                chunk,
                section_previews[chunk.section_id],
                blocks_by_id[chunk.reading_block_id],
            )
            contextualized_chunks.append(
                chunk.with_contextual_text(stored_contexts[key])
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
        """在信号量限流下调用 LLM 生成上下文文本，返回去除首尾空白的字符串。

        要求模型以 JSON 对象返回 ``{"contextual_text": "..."}``，便于严格解析；
        任一字段缺失或类型错误都会抛错，让上层感知到失败。
        """
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

    def _artifact_key(
        self,
        chunk: RetrievalChunk,
        section_preview: str,
        reading_block: ReadingBlock,
    ) -> str:
        """计算 chunk 的上下文缓存键。

        将所有可能影响生成结果的输入维度（prompt 版本、schema 版本、模型与 thinking
        配置、章节路径、section preview、reading block、chunk 文本）拼接后哈希，
        任何一项变化都会让 key 改变，从而强制重新生成。
        """
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
    """组装发送给 LLM 的用户 prompt。

    使用 XML 标签包裹各部分内容，便于模型区分“任务、章节、上下文、目标 chunk”；
    ``xml_cdata`` 会转义特殊字符，避免 chunk 内容破坏 XML 结构。
    """
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
