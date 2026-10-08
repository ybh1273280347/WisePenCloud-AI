"""Select structural context around retrieval seeds without changing Chunk identity."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from common.utils.markdown import TokenCounter, default_token_counter

from rag.application.document.models import DocChunk


class ExpansionStrategy(StrEnum):
    NONE = "none"
    NEIGHBOR = "neighbor"
    SECTION_LOCAL = "section_local"
    WHOLE_SECTION_IF_SMALL = "whole_section_if_small"


@dataclass(frozen=True, slots=True)
class ContextUnit:
    """A selected chunk with an explicit evidence/context role."""

    chunk_id: str
    section_id: str | None
    chunk_index: int
    text: str
    role: Literal["seed", "neighbor", "section_context"]


class ContextExpander:
    """Expand seed chunks by structural order under an independent token budget."""

    def __init__(self, token_counter: TokenCounter | None = None) -> None:
        self._token_counter = token_counter or default_token_counter()

    def expand(
        self,
        *,
        seeds: Sequence[DocChunk],
        all_chunks: Sequence[DocChunk],
        strategy: ExpansionStrategy,
        token_budget: int,
    ) -> tuple[ContextUnit, ...]:
        if token_budget <= 0:
            raise ValueError("token_budget must be positive")
        ordered = sorted(_deduplicate(all_chunks), key=_order)
        seed_chunks = sorted(_deduplicate(seeds), key=_order)
        selected: list[
            tuple[DocChunk, Literal["seed", "neighbor", "section_context"]]
        ] = [(chunk, "seed") for chunk in seed_chunks]
        selected_ids = {chunk.chunk_id for chunk in seed_chunks}
        used_tokens = sum(
            self._token_counter.count(chunk.raw_text) for chunk in seed_chunks
        )
        if used_tokens > token_budget:
            # Seeds are indivisible evidence. Reject an insufficient budget
            # instead of truncating evidence or silently exceeding the limit.
            raise ValueError("seed chunks exceed token_budget")
        if strategy is not ExpansionStrategy.NONE:
            candidates = self._candidates(
                seed_chunks=seed_chunks,
                ordered=ordered,
                strategy=strategy,
            )
            if strategy is ExpansionStrategy.WHOLE_SECTION_IF_SMALL:
                # Include a whole section atomically; an over-budget section
                # contributes no partial context.
                for seed in seed_chunks:
                    local = [
                        chunk
                        for chunk in candidates
                        if _same_section(seed, chunk)
                        and chunk.chunk_id not in selected_ids
                    ]
                    cost = sum(
                        self._token_counter.count(chunk.raw_text) for chunk in local
                    )
                    if used_tokens + cost > token_budget:
                        continue
                    selected.extend((chunk, "section_context") for chunk in local)
                    selected_ids.update(chunk.chunk_id for chunk in local)
                    used_tokens += cost
                candidates = ()
            for chunk in candidates:
                if chunk.chunk_id in selected_ids:
                    continue
                cost = self._token_counter.count(chunk.raw_text)
                if used_tokens + cost > token_budget:
                    break
                selected.append(
                    (
                        chunk,
                        "neighbor"
                        if strategy is ExpansionStrategy.NEIGHBOR
                        else "section_context",
                    )
                )
                selected_ids.add(chunk.chunk_id)
                used_tokens += cost
        # Evidence and background remain individually labelled; document order
        # is deterministic even when multiple resources share chunk_index.
        selected.sort(key=lambda item: _order(item[0]))
        return tuple(_unit(chunk, role) for chunk, role in selected)

    @staticmethod
    def _candidates(
        *,
        seed_chunks: Sequence[DocChunk],
        ordered: Sequence[DocChunk],
        strategy: ExpansionStrategy,
    ) -> tuple[DocChunk, ...]:
        if strategy is ExpansionStrategy.WHOLE_SECTION_IF_SMALL:
            return tuple(
                chunk
                for chunk in ordered
                if any(_same_section(seed, chunk) for seed in seed_chunks)
            )
        candidates: list[DocChunk] = []
        locals_by_seed = [
            (seed, [chunk for chunk in ordered if _same_section(seed, chunk)])
            for seed in seed_chunks
        ]
        for distance in range(1, len(ordered) + 1):
            for seed, local in locals_by_seed:
                position = next(
                    (
                        i
                        for i, chunk in enumerate(local)
                        if chunk.chunk_id == seed.chunk_id
                    ),
                    -1,
                )
                if position < 0:
                    continue
                for index in (position - distance, position + distance):
                    if 0 <= index < len(local):
                        candidates.append(local[index])
        return tuple(candidates)


def _same_section(left: DocChunk, right: DocChunk) -> bool:
    if (
        left.resource_id != right.resource_id
        or left.content_revision != right.content_revision
    ):
        return False
    # Titles are display text, not section identity. A subtree strategy requires
    # an explicit Section tree and is not inferred from duplicate title paths.
    return left.section_id == right.section_id


def _order(chunk: DocChunk) -> tuple[str, str, int]:
    return chunk.resource_id, chunk.content_revision, chunk.chunk_index


def _deduplicate(chunks: Sequence[DocChunk]) -> tuple[DocChunk, ...]:
    seen: set[str] = set()
    result: list[DocChunk] = []
    for chunk in chunks:
        if chunk.chunk_id not in seen:
            seen.add(chunk.chunk_id)
            result.append(chunk)
    return tuple(result)


def _unit(
    chunk: DocChunk, role: Literal["seed", "neighbor", "section_context"]
) -> ContextUnit:
    return ContextUnit(
        chunk_id=chunk.chunk_id,
        section_id=chunk.section_id,
        chunk_index=chunk.chunk_index,
        text=chunk.raw_text,
        role=role,
    )
