from dataclasses import replace

import pytest
from common.utils.markdown import TokenCounter

from rag.application.document.models import DocChunk
from rag.application.retrieval.context_expander import (
    ContextExpander,
    ExpansionStrategy,
)


class _Chars(TokenCounter):
    name = "chars"

    def count(self, text: str) -> int:
        return len(text)

    def split(self, text: str, max_tokens: int) -> tuple[str, ...]:
        return tuple(text[i : i + max_tokens] for i in range(0, len(text), max_tokens))


def _chunk(index: int, text: str, section: str = "s") -> DocChunk:
    return DocChunk(
        chunk_id=f"c{index}",
        resource_id="r",
        content_revision="rev",
        section_id=section,
        section_path=[section],
        chunk_index=index,
        raw_text=text,
    )


def test_neighbor_expansion_is_bounded_and_deduplicated() -> None:
    chunks = [_chunk(index, chr(97 + index)) for index in range(4)]
    result = ContextExpander(_Chars()).expand(
        seeds=[chunks[1], chunks[1]],
        all_chunks=chunks,
        strategy=ExpansionStrategy.NEIGHBOR,
        token_budget=3,
    )

    assert [(item.chunk_id, item.role) for item in result] == [
        ("c0", "neighbor"),
        ("c1", "seed"),
        ("c2", "neighbor"),
    ]


def test_none_returns_only_seeds() -> None:
    chunks = [_chunk(index, str(index)) for index in range(2)]
    result = ContextExpander(_Chars()).expand(
        seeds=[chunks[0]],
        all_chunks=chunks,
        strategy=ExpansionStrategy.NONE,
        token_budget=20,
    )

    assert len(result) == 1
    assert result[0].role == "seed"


@pytest.mark.parametrize(
    "strategy", [ExpansionStrategy.SECTION_LOCAL, ExpansionStrategy.NEIGHBOR]
)
def test_expansion_never_crosses_resource_revision_or_section(strategy):
    seed = _chunk(1, "seed")
    chunks = [
        seed,
        _chunk(0, "local"),
        _chunk(2, "sibling", "other"),
        replace(_chunk(3, "foreign"), resource_id="foreign", chunk_id="foreign"),
        replace(_chunk(4, "old"), content_revision="old", chunk_id="old"),
    ]
    result = ContextExpander(_Chars()).expand(
        seeds=[seed],
        all_chunks=chunks,
        strategy=strategy,
        token_budget=100,
    )
    assert {item.chunk_id for item in result} == {"c0", "c1"}


def test_whole_section_is_atomic_under_budget():
    chunks = [_chunk(0, "small"), _chunk(1, "seed"), _chunk(2, "large" * 5)]
    result = ContextExpander(_Chars()).expand(
        seeds=[chunks[1]],
        all_chunks=chunks,
        strategy=ExpansionStrategy.WHOLE_SECTION_IF_SMALL,
        token_budget=15,
    )
    assert [item.chunk_id for item in result] == ["c1"]


def test_seed_budget_must_fit_complete_evidence():
    with pytest.raises(ValueError, match="seed chunks"):
        ContextExpander(_Chars()).expand(
            seeds=[_chunk(0, "very long seed")],
            all_chunks=[],
            strategy=ExpansionStrategy.NONE,
            token_budget=2,
        )
