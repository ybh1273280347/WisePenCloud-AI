from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from chat.application.rag.cache.evidence_materialization import (
    RagEvidenceMaterializationCache,
    RagEvidenceMaterializationCacheScope,
    RagMaterializedEvidenceView,
)
from chat.application.rag.retrieval.models import RagRankedChunk, ScoredChunk
from chat.application.utils.ranking_engine.models import RankedCandidate
from .models import RagDirectEvidence

if TYPE_CHECKING:
    from chat.application.rag.corpus import RagCorpusRepository
    from chat.application.rag.ingestion.models import RagChildChunk, RagParentChunk


@dataclass(frozen=True, slots=True)
class RagEvidenceMaterializeRequest:
    candidates: tuple[RagRankedChunk, ...]
    cache_scope: RagEvidenceMaterializationCacheScope | None = None


class RagEvidenceMaterializer:
    """把命中的 child chunks 回源为 parent chunks evidence。"""

    __slots__ = ("_cache", "_corpus_repository")

    def __init__(
            self,
            *,
            corpus_repository: RagCorpusRepository,
            cache: RagEvidenceMaterializationCache | None = None,
    ) -> None:
        self._corpus_repository = corpus_repository
        self._cache = cache

    async def materialize(
            self,
            request: RagEvidenceMaterializeRequest,
    ) -> tuple[RagDirectEvidence, ...]:
        ranked = tuple(item.ranking for item in request.candidates)
        ranked_ids = tuple(item.candidate_id for item in ranked)
        cached_views_by_child_id = (
            await self._cache.get_many(scope=request.cache_scope, child_chunk_ids=ranked_ids)
            if self._cache is not None and request.cache_scope is not None
            else {}
        )
        missing_ids = tuple(
            chunk_id
            for chunk_id in ranked_ids
            if chunk_id not in cached_views_by_child_id
        )
        retrieved_by_id = {
            item.ranking.candidate_id: item.chunk
            for item in request.candidates
        }
        child_by_id = {
            chunk.chunk_id: chunk
            for chunk in await self._corpus_repository.load_child_chunks(missing_ids)
        }
        parent_ids = _resolve_ranked_parent_ids(
            ranked,
            child_by_id=child_by_id,
            retrieved_by_id=retrieved_by_id,
        )
        parent_by_id = {
            chunk.chunk_id: chunk
            for chunk in await self._corpus_repository.load_parent_chunks(parent_ids)
        }

        views_to_cache: dict[str, RagMaterializedEvidenceView] = {}
        evidence_by_parent_id: dict[str, RagDirectEvidence] = {}
        for item in ranked:
            retrieved = retrieved_by_id.get(item.candidate_id)
            view = cached_views_by_child_id.get(item.candidate_id)
            if view is None:
                child = child_by_id.get(item.candidate_id)
                parent_id = _resolve_parent_chunk_id(child, retrieved)
                if not parent_id:
                    continue

                view = _to_materialized_view(
                    item,
                    retrieved=retrieved,
                    child=child,
                    parent=parent_by_id.get(parent_id),
                )
                views_to_cache[item.candidate_id] = view

            if not view.parent_chunk_id or view.parent_chunk_id in evidence_by_parent_id:
                continue

            evidence_by_parent_id[view.parent_chunk_id] = RagDirectEvidence(
                citation_id=f"E{item.rank}",
                document_version=view.document_version,
                text=view.text,
                page_label=view.page_label,
                section_path=view.section_path,
                anchor_labels=view.anchor_labels,
                matched_child_ids=view.matched_child_ids,
            )
        if self._cache is not None and request.cache_scope is not None:
            await self._cache.set_many(
                scope=request.cache_scope,
                views_by_child_id=views_to_cache,
            )
        return tuple(evidence_by_parent_id.values())


def _resolve_parent_chunk_id(
        child: RagChildChunk | None,
        retrieved: ScoredChunk | None,
) -> str:
    if child is not None and child.parent_chunk_id:
        return child.parent_chunk_id
    if retrieved is not None:
        return retrieved.parent_chunk_id
    return ""


def _resolve_ranked_parent_ids(
        ranked: tuple[RankedCandidate, ...],
        *,
        child_by_id: dict[str, RagChildChunk],
        retrieved_by_id: dict[str, ScoredChunk],
) -> tuple[str, ...]:
    parent_ids: list[str] = []
    for item in ranked:
        parent_id = _resolve_parent_chunk_id(
            child_by_id.get(item.candidate_id),
            retrieved_by_id.get(item.candidate_id),
        )
        if parent_id:
            parent_ids.append(parent_id)
    return tuple(dict.fromkeys(parent_ids))


def _to_materialized_view(
        item: RankedCandidate,
        *,
        retrieved: ScoredChunk | None,
        child: RagChildChunk | None,
        parent: RagParentChunk | None,
) -> RagMaterializedEvidenceView:
    page_label = child.page_label if child is not None else None
    section_path = child.section_path if child is not None else ()
    anchor_labels = child.anchor_labels if child is not None else ()
    if child is None and retrieved is not None:
        page_label = retrieved.page_label
        section_path = retrieved.section_path
        anchor_labels = retrieved.anchor_labels
    parent_chunk_id = _resolve_parent_chunk_id(child, retrieved)
    text = item.candidate.text
    if child is not None:
        text = child.text
    if parent is not None:
        text = parent.text

    return RagMaterializedEvidenceView(
        parent_chunk_id=parent_chunk_id,
        document_version=retrieved.document_version if retrieved is not None else "",
        text=text,
        page_label=page_label,
        section_path=section_path,
        anchor_labels=anchor_labels,
        matched_child_ids=(item.candidate_id,),
    )
