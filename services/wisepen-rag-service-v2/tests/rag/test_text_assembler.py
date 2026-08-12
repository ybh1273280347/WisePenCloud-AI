import pytest

from rag.domain.models.content import SourcePart
from rag.core.persistence.mongo.text_assembler import assemble_source_text
from rag.utils.chunkers import SourceSpan


def _part(index: int, start: int, end: int, text: str) -> SourcePart:
    return SourcePart(
        resource_id="resource-1",
        content_revision="revision-1",
        part_index=index,
        source_span=SourceSpan(start, end),
        text=text,
    )


def test_assemble_source_text_joins_contiguous_parts() -> None:
    parts = [_part(0, 0, 3, "abc"), _part(1, 3, 6, "def")]

    assert assemble_source_text(parts, [SourceSpan(1, 5)]) == "bcde"


def test_assemble_source_text_rejects_gaps() -> None:
    parts = [_part(0, 0, 3, "abc"), _part(1, 4, 6, "ef")]

    with pytest.raises(RuntimeError, match="gap"):
        assemble_source_text(parts, [SourceSpan(0, 6)])


def test_assemble_source_text_rejects_overlapping_parts() -> None:
    parts = [_part(0, 0, 4, "abcd"), _part(1, 3, 6, "def")]

    with pytest.raises(RuntimeError, match="overlap"):
        assemble_source_text(parts, [SourceSpan(0, 6)])
