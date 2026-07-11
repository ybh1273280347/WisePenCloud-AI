from __future__ import annotations

import pytest

pytest.importorskip("jieba")
pytest.importorskip("thulac")

from chat.application.utils.ranking_engine.tokenizer.ranking_tokenizers import (
    JiebaRankingTokenizer,
    ThuLacRankingTokenizer,
)


@pytest.mark.parametrize(
    ("tokenizer_cls", "expected_token"),
    [
        (JiebaRankingTokenizer, "人工智能"),
        (ThuLacRankingTokenizer, "人工智能"),
    ],
)
def test_ranking_tokenizers_tokenize_cjk(
        tokenizer_cls: type[JiebaRankingTokenizer] | type[ThuLacRankingTokenizer],
        expected_token: str,
) -> None:
    try:
        tokenizer = tokenizer_cls()
    except MemoryError:
        pytest.skip("THULAC model cannot be loaded with the available memory")

    tokens = tokenizer.tokenize("我爱北京天安门和人工智能")

    assert tokens
    assert "北京" in tokens
    assert "天安门" in tokens
    assert expected_token in tokens
