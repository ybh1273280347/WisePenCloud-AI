from rag.utils.chunkers import ChunkDocument, PlainTextChunker, PlainTextChunkerConfig
from rag.utils.ranking import RankCandidate, RankedCandidate
from rag.utils.ranking.relevance_gate import (
    HighLowRelevanceGate,
    HighLowRelevanceGateConfig,
)
from rag.utils.xml_markup import xml_attr, xml_cdata


def test_plain_text_chunker_preserves_source_offsets() -> None:
    text = "alpha beta gamma"
    result = PlainTextChunker(
        PlainTextChunkerConfig(chunk_size=10, chunk_overlap=2)
    ).chunk(document=ChunkDocument(text=text))

    assert result.chunks
    for chunk in result.chunks:
        assert chunk.start_offset is not None
        assert chunk.end_offset is not None
        assert text[chunk.start_offset : chunk.end_offset] == chunk.text


def test_relevance_gate_keeps_only_high_watermark_candidates() -> None:
    gate = HighLowRelevanceGate(
        HighLowRelevanceGateConfig(
            low_watermark=0.2,
            high_watermark=0.6,
            uncertain_limit=2,
        )
    )
    result = gate.evaluate(
        ranked=(
            RankedCandidate(
                candidate=RankCandidate(candidate_id="high"),
                rank=1,
                score=0.8,
            ),
            RankedCandidate(
                candidate=RankCandidate(candidate_id="uncertain"),
                rank=2,
                score=0.4,
            ),
        )
    )

    assert [item.candidate_id for item in result.ranked] == ["high"]


def test_xml_helpers_escape_attributes_and_split_cdata_terminators() -> None:
    assert xml_attr('a&"b') == "a&amp;&quot;b"
    assert xml_cdata("a]]>b") == "<![CDATA[a]]]]><![CDATA[>b]]>"
