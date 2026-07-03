from __future__ import annotations

from dataclasses import replace

from .models import Chunk, ChunkDocument, ChunkingResult, ChunkRole
from .pipeline import ChunkingPipeline


class ChunkingEngine:
    """通用分块引擎，按构造时绑定的 pipeline 执行分块流程。

    用法：
        engine = get_chunking_engine("markdown")
        result = engine.chunk(document=doc)
    """

    __slots__ = ("_pipeline",)

    def __init__(self, *, pipeline: ChunkingPipeline) -> None:
        self._pipeline = pipeline

    def chunk(
            self,
            *,
            document: ChunkDocument,
    ) -> ChunkingResult:
        """执行一次分块，返回分块结果。

        流程：文档转换 → 切分 → 聚合 → chunk 转换 → 索引
        """
        pipeline = self._pipeline

        # 1. 文档转换：按顺序执行所有转换器，逐步转换文档
        for transformer in pipeline.document_transformers:
            document = transformer.process(document=document)

        # 2. 切分：将文档拆成 TextUnit 列表
        units = pipeline.splitter.split(document=document)

        # 3. 聚合：将 TextUnit 聚合成 Chunk
        if pipeline.packer is not None:
            # 有聚合器时，按 packer 逻辑聚合（如 SizeBoundedUnitPacker 按大小合并相邻 unit）
            chunks = pipeline.packer.pack(units=units)
        else:
            # 无聚合器时，每个 unit 一对一映射为 chunk（适用于 RecursiveTextSplitter 等已按目标大小切分的场景）
            chunks = tuple(
                Chunk(
                    chunk_id=f"chunk-{i}",
                    text=unit.text,
                    chunk_index=i,
                    role=ChunkRole.FLAT,
                    start_offset=unit.start_offset,
                    end_offset=unit.end_offset,
                    start_unit=unit.unit_index,
                    end_unit=unit.unit_index,
                )
                for i, unit in enumerate(units)
            )
        # 聚合后重新分配 chunk_index
        chunks = self._assign_chunk_indices(chunks)

        # 4. chunk 转换：按顺序执行所有转换器，每步后重新分配 chunk_index
        for transformer in pipeline.chunk_transformers:
            chunks = transformer.process(chunks=chunks)
            chunks = self._assign_chunk_indices(chunks)

        # 5. 索引：基于最终 chunk 构建语义定位索引
        indexes = (
            pipeline.index_builder.index(
                document=document,
                units=units,
                chunks=chunks,
            )
            if pipeline.index_builder is not None
            else ()
        )

        return ChunkingResult(
            chunks=chunks,
            units=units,
            indexes=indexes,
            pipeline=pipeline.name,
            metadata={
                "unit_count": len(units),
                "chunk_count": len(chunks),
                "index_count": len(indexes),
            },
        )

    @staticmethod
    def _assign_chunk_indices(chunks: tuple[Chunk, ...]) -> tuple[Chunk, ...]:
        """全局连续重新分配 chunk_index。

        chunk 转换器可能增删 chunk（如 ChildChunkGenerator 追加子 chunk），
        导致 chunk_index 不连续。此方法全局从 0 重新编号，
        确保父子 chunk 不会出现 chunk_index 冲突。
        """
        return tuple(
            replace(chunk, chunk_index=i)
            for i, chunk in enumerate(chunks)
        )
