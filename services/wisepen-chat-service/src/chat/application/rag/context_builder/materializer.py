from __future__ import annotations

from dataclasses import dataclass

from chat.application.rag.corpus import RagCorpusRepository
from chat.application.rag.ingestion import RagChildChunk, RagParentChunk
from chat.application.rag.retrieval import ScoredChunk
from chat.application.utils.ranking_engine.models import RankedCandidate

from .models import RagDirectEvidence, RagMatchedChildChunk


@dataclass(frozen=True, slots=True)
class RagEvidenceMaterializeRequest:
    ranked: tuple[RankedCandidate, ...]
    retrieved_chunks: tuple[ScoredChunk, ...]
    elastic_candidate_chunk_ids: tuple[str, ...] | None = None


class RagEvidenceMaterializer:
    """把命中的 child chunks 回源为 parent chunks evidence。"""

    __slots__ = ("_corpus_repository",)

    def __init__(
            self,
            *,
            corpus_repository: RagCorpusRepository,
    ) -> None:
        self._corpus_repository = corpus_repository

    async def materialize(
            self,
            request: RagEvidenceMaterializeRequest,
    ) -> tuple[RagDirectEvidence, ...]:
        ranked_ids = tuple(item.candidate_id for item in request.ranked)
        retrieved_by_id = {
            chunk.chunk_id: chunk
            for chunk in request.retrieved_chunks
        }
        child_by_id = {
            chunk.chunk_id: chunk
            for chunk in await self._corpus_repository.load_child_chunks(ranked_ids)
        }
        parent_ids = _resolve_ranked_parent_ids(
            request.ranked,
            child_by_id=child_by_id,
            retrieved_by_id=retrieved_by_id,
        )
        parent_by_id = {
            chunk.chunk_id: chunk
            for chunk in await self._corpus_repository.load_parent_chunks(parent_ids)
        }

        elastic_prefiltered_ids = (
            set(request.elastic_candidate_chunk_ids)
            if request.elastic_candidate_chunk_ids is not None
            else None
        )
        evidence_by_parent_id: dict[str, RagDirectEvidence] = {}
        for item in request.ranked:
            retrieved = retrieved_by_id.get(item.candidate_id)
            child = child_by_id.get(item.candidate_id)
            parent_id = _resolve_parent_chunk_id(child, retrieved)
            if not parent_id or parent_id in evidence_by_parent_id:
                continue

            parent = parent_by_id.get(parent_id)
            evidence_by_parent_id[parent_id] = _to_direct_evidence(
                item,
                retrieved=retrieved,
                child=child,
                parent=parent,
                elastic_prefiltered=(
                    elastic_prefiltered_ids is not None
                    and item.candidate_id in elastic_prefiltered_ids
                ),
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


def _to_direct_evidence(
        item: RankedCandidate,
        *,
        retrieved: ScoredChunk | None,
        child: RagChildChunk | None,
        parent: RagParentChunk | None,
        elastic_prefiltered: bool,
) -> RagDirectEvidence:
    matched_child = _to_matched_child(
        chunk_id=item.candidate_id,
        text=child.text if child is not None else item.candidate.text,
        retrieved=retrieved,
        child=child,
    )
    page_label = matched_child.page_label
    section_path = matched_child.section_path
    anchor_labels = matched_child.anchor_labels
    parent_chunk_id = _resolve_parent_chunk_id(child, retrieved)

    return RagDirectEvidence(
        citation_id=f"E{item.rank}",
        parent_chunk_id=parent_chunk_id,
        resource_id=retrieved.resource_id if retrieved is not None else "",
        document_version=retrieved.document_version if retrieved is not None else "",
        corpus_version=retrieved.corpus_version if retrieved is not None else "",
        text=parent.text if parent is not None else matched_child.text,
        citation_anchor=_build_citation_anchor(
            parent_chunk_id=parent_chunk_id,
            page_label=page_label,
            section_path=section_path,
            anchor_labels=anchor_labels,
        ),
        rank=item.rank,
        score=item.score,
        page_label=page_label,
        section_path=section_path,
        anchor_labels=anchor_labels,
        matched_child_chunks=(matched_child,),
        elastic_prefiltered=elastic_prefiltered,
    )


def _to_matched_child(
        *,
        chunk_id: str,
        text: str,
        retrieved: ScoredChunk | None,
        child: RagChildChunk | None,
) -> RagMatchedChildChunk:
    if child is not None:
        return RagMatchedChildChunk(
            chunk_id=chunk_id,
            text=text,
            page_label=child.page_label,
            section_path=child.section_path,
            anchor_labels=child.anchor_labels,
            retrieval_channels=retrieved.retrieval_channels if retrieved is not None else (),
        )
    if retrieved is not None:
        return RagMatchedChildChunk(
            chunk_id=chunk_id,
            text=text,
            page_label=retrieved.page_label,
            section_path=retrieved.section_path,
            anchor_labels=retrieved.anchor_labels,
            retrieval_channels=retrieved.retrieval_channels,
        )
    return RagMatchedChildChunk(chunk_id=chunk_id, text=text)


def _build_citation_anchor(
        *,
        parent_chunk_id: str,
        page_label: str | None,
        section_path: tuple[str, ...],
        anchor_labels: tuple[str, ...],
) -> str:
    parts: list[str] = []
    if page_label:
        parts.append(f"p.{page_label}")
    if section_path:
        parts.append(" > ".join(section_path))
    if anchor_labels:
        parts.append(", ".join(anchor_labels))
    if not parts:
        parts.append(parent_chunk_id)
    return " | ".join(parts)
