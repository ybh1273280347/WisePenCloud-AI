from chat.application.utils.chunking_engine import Chunk, ChunkDocument, ChunkRole
from chat.application.utils.chunking_engine.block_splitters.recursive_text_block_splitter import (
    RecursiveTextBlockSplitter,
    RecursiveTextBlockSplitterConfig,
)
from chat.application.utils.chunking_engine.chunk_normalizers.parent_child_chunk_normalizer import (
    ParentChildChunkNormalizer,
)
from chat.application.utils.chunking_engine.registry import get_chunking_engine


def test_markdown_pipeline_offsets_point_to_original_text() -> None:
    text = "# 快速开始\n\n这里是正文。"

    result = get_chunking_engine("markdown").chunk(
        document=ChunkDocument(text=text, content_type="text/markdown"),
    )

    assert result.chunks
    for chunk in result.chunks:
        assert chunk.start_offset is not None
        assert chunk.end_offset is not None
        assert text[chunk.start_offset:chunk.end_offset].strip() == chunk.text


def test_markdown_block_splitter_keeps_full_section_path() -> None:
    text = "# 一级\n\n## 二级\n\n正文。"

    result = get_chunking_engine("markdown").chunk(
        document=ChunkDocument(text=text, content_type="text/markdown"),
    )

    paragraph = next(block for block in result.blocks if block.text == "正文。")
    assert paragraph.section_path == ("一级", "二级")
    assert any(
        locator.name == "section:一级 > 二级"
        for locator in result.locators
    )


def test_parent_child_normalizer_remaps_children_after_heading_only_merge() -> None:
    chunks = (
        Chunk(
            chunk_id="parent-heading",
            text="# 标题",
            chunk_index=0,
            role=ChunkRole.PARENT,
        ),
        Chunk(
            chunk_id="parent-body",
            text="正文内容。",
            chunk_index=1,
            role=ChunkRole.PARENT,
        ),
        Chunk(
            chunk_id="child-body",
            text="正文内容。",
            chunk_index=2,
            role=ChunkRole.CHILD,
            parent_chunk_id="parent-body",
        ),
    )

    normalized = ParentChildChunkNormalizer(min_size=0).process(chunks=chunks)

    parent_ids = {
        chunk.chunk_id
        for chunk in normalized
        if chunk.role == ChunkRole.PARENT
    }
    children = [chunk for chunk in normalized if chunk.role == ChunkRole.CHILD]

    assert children
    assert all(child.parent_chunk_id in parent_ids for child in children)


def test_recursive_splitter_offsets_handle_overlap() -> None:
    text = "abcdefghijklmnopqrstuvwxyz"
    splitter = RecursiveTextBlockSplitter(
        RecursiveTextBlockSplitterConfig(
            chunk_size=10,
            chunk_overlap=3,
            separators=("",),
        )
    )

    blocks = splitter.split(document=ChunkDocument(text=text))

    assert len(blocks) > 1
    for block in blocks:
        assert block.start_offset is not None
        assert block.end_offset is not None
        assert text[block.start_offset:block.end_offset] == block.text
