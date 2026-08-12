"""Qdrant point payload 到检索候选事实的反序列化。"""

from collections.abc import Mapping, Sequence

from rag.domain.retrieval import RetrievalCandidate


def to_retrieval_candidate(
    payload: Mapping[str, object] | None,
    *,
    score: float,
) -> RetrievalCandidate:
    """校验并还原 CandidateSearch 实际消费的 payload 字段。"""
    if payload is None:
        raise ValueError("Qdrant candidate payload is missing")

    return RetrievalCandidate(
        chunk_id=_required_text(payload, "chunk_id"),
        reading_block_id=_required_text(payload, "reading_block_id"),
        section_id=_required_text(payload, "section_id"),
        section_path=_required_text_list(payload, "section_path"),
        resource_id=_required_text(payload, "resource_id"),
        content_revision=_required_text(payload, "content_revision"),
        raw_text=_required_text(payload, "raw_text"),
        anchor_labels=_required_text_list(payload, "anchor_labels"),
        source_ref_id=_required_text(payload, "source_ref_id"),
        score=float(score),
    )


def _required_text(payload: Mapping[str, object], field_name: str) -> str:
    value = payload.get(field_name)
    if not isinstance(value, str) or not value:
        raise TypeError(f"Qdrant candidate payload field {field_name} is invalid")
    return value


def _required_text_list(
    payload: Mapping[str, object],
    field_name: str,
) -> list[str]:
    value = payload.get(field_name)
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        raise TypeError(f"Qdrant candidate payload field {field_name} is invalid")
    if not all(isinstance(item, str) for item in value):
        raise TypeError(f"Qdrant candidate payload field {field_name} is invalid")
    return list(value)
