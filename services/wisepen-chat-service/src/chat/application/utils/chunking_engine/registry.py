from __future__ import annotations

from .engine import ChunkingEngine
from .index_builders.markdown_locator_index_builder import MarkdownLocatorIndexBuilder
from .models import ChunkRole, UnitType
from .packers.size_bounded_unit_packer import SizeBoundedUnitPacker, SizeBoundedUnitPackerConfig
from .pipeline import ChunkingPipeline
from .chunk_transformers.child_chunk_generator import ChildChunkConfig, ChildChunkGenerator
from .chunk_transformers.flat_chunk_finalizer import FlatChunkFinalizer
from .chunk_transformers.parent_child_chunk_finalizer import ParentChildChunkFinalizer
from .document_transformers.markdown_section_path_injector import MarkdownSectionPathInjector
from .splitters.markdown_block_splitter import MarkdownBlockSplitter
from .splitters.recursive_text_splitter import RecursiveTextSplitter, RecursiveTextSplitterConfig

DEFAULT_CHUNK_SIZE: int = 4000


class ChunkingEngineRegistry:
    """按名称提供已注册的 ChunkingEngine 单例。"""

    __slots__ = ("_engines",)

    def __init__(self) -> None:
        self._engines = {
            "markdown": ChunkingEngine(
                pipeline=ChunkingPipeline(
                    name="markdown",
                    splitter=MarkdownBlockSplitter(),
                    packer=SizeBoundedUnitPacker(
                        SizeBoundedUnitPackerConfig(
                            chunk_size=DEFAULT_CHUNK_SIZE,
                            role=ChunkRole.FLAT,
                            # Markdown 默认读取块；page marker 是硬边界，避免引用页码时跨页。
                            hard_boundary_unit_types=(UnitType.PAGE_MARKER,),
                        )
                    ),
                    document_transformers=(MarkdownSectionPathInjector(),),
                    chunk_transformers=(FlatChunkFinalizer(),),
                    index_builder=MarkdownLocatorIndexBuilder(),
                )
            ),
            "plain_text": ChunkingEngine(
                pipeline=ChunkingPipeline(
                    name="plain_text",
                    # 无 Markdown 结构时使用；不产出 section/page/anchor 语义索引。
                    splitter=RecursiveTextSplitter(
                        RecursiveTextSplitterConfig(
                            chunk_size=DEFAULT_CHUNK_SIZE,
                            chunk_overlap=0,
                        )
                    ),
                    document_transformers=(),
                    chunk_transformers=(FlatChunkFinalizer(),),
                )
            ),
            "markdown_recursive": ChunkingEngine(
                pipeline=ChunkingPipeline(
                    name="markdown_recursive",
                    # 结构块过大时兜底递归切分；更偏文本长度，不保证 Markdown block 完整。
                    splitter=RecursiveTextSplitter(
                        RecursiveTextSplitterConfig.for_markdown(
                            chunk_size=DEFAULT_CHUNK_SIZE,
                            chunk_overlap=0,
                        )
                    ),
                    document_transformers=(MarkdownSectionPathInjector(),),
                    chunk_transformers=(FlatChunkFinalizer(),),
                    index_builder=MarkdownLocatorIndexBuilder(),
                )
            ),
            "parent_child_markdown": ChunkingEngine(
                pipeline=ChunkingPipeline(
                    name="parent_child_markdown",
                    splitter=MarkdownBlockSplitter(),
                    packer=SizeBoundedUnitPacker(
                        SizeBoundedUnitPackerConfig(
                            chunk_size=DEFAULT_CHUNK_SIZE,
                            role=ChunkRole.PARENT,
                            # RAG 父子块首选；父块不跨页，子块继承父块页码 metadata。
                            hard_boundary_unit_types=(UnitType.PAGE_MARKER,),
                        )
                    ),
                    document_transformers=(MarkdownSectionPathInjector(),),
                    chunk_transformers=(
                        ChildChunkGenerator(
                            ChildChunkConfig(
                                child_chunk_size=600,
                                child_overlap=100,
                            )
                        ),
                        ParentChildChunkFinalizer(),
                    ),
                    index_builder=MarkdownLocatorIndexBuilder(),
                )
            ),
        }

    def get(self, name: str) -> ChunkingEngine:
        try:
            return self._engines[name]
        except KeyError as exc:
            raise KeyError(f"Unknown chunking engine: {name!r}") from exc


_REGISTRY = ChunkingEngineRegistry()


def get_chunking_engine(name: str) -> ChunkingEngine:
    return _REGISTRY.get(name)
