from __future__ import annotations

from dataclasses import dataclass

from .protocols import (
    ChunkIndexBuilder,
    ChunkPacker,
    ChunkTransformer,
    DocumentTransformer,
    UnitSplitter,
)


@dataclass(frozen=True, slots=True)
class ChunkingPipeline:
    """分块流水线配置，定义分块的完整流程。

    执行顺序：document_transformers → splitter → packer → chunk_transformers → index_builder

    - document_transformers：文档转换（如注入标题路径），在切分前修改原文
    - splitter：切分为 TextUnit，是流程的核心
    - packer：将 TextUnit 聚合为 Chunk（可选，None 时 unit 一对一映射为 chunk）
    - chunk_transformers：chunk 转换（如生成子 chunk、合并短 chunk、生成 ID）
    - index_builder：构建语义定位索引（可选，供下游按维度查找 chunk）
    """

    name: str  # pipeline 名称，如 "markdown"、"plain_text"
    splitter: UnitSplitter  # unit 切分器（必选）
    packer: ChunkPacker | None = None  # chunk 聚合器，None 时 unit 一对一映射为 chunk
    document_transformers: tuple[DocumentTransformer, ...] = ()  # 文档转换器列表，按顺序执行
    chunk_transformers: tuple[ChunkTransformer, ...] = ()  # chunk 转换器列表，按顺序执行
    index_builder: ChunkIndexBuilder | None = None  # 语义定位索引构建器（可选）
