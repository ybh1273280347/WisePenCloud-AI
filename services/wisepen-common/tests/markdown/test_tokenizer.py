from hashlib import sha256
from importlib.resources import files
from unittest.mock import Mock

import pytest
import tiktoken

from common.utils.markdown import MarkdownChunkerConfig, TiktokenTokenCounter
from common.utils.markdown.chunking.tokenizer import _local_encoding


def test_cold_initialization_never_downloads(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("TIKTOKEN_CACHE_DIR", str(tmp_path))
    monkeypatch.setattr(
        tiktoken, "get_encoding", Mock(side_effect=AssertionError("download"))
    )
    _local_encoding.cache_clear()
    counter = TiktokenTokenCounter()
    assert counter.count("中文 emoji 🙂") == 4
    data = (
        files("common.utils.markdown")
        .joinpath("chunking/data/cl100k_base.tiktoken")
        .read_bytes()
    )
    assert (
        sha256(data).hexdigest()
        == "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
    )
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize(
    "text",
    [
        "English words " * 80,
        "中文文本" * 60,
        "混合 English 中文🙂\r\n\u2028" * 50,
        "<|endoftext|> literal",
    ],
)
def test_split_preserves_unicode_and_all_characters(text) -> None:
    counter = TiktokenTokenCounter()
    parts = counter.split(text, 32)
    assert "".join(parts) == text
    assert all(counter.count(part) <= 32 for part in parts)
    assert all("\ufffd" not in part for part in parts)


def test_count_cache_and_token_unit() -> None:
    counter = TiktokenTokenCounter()
    english = "a" * 20
    chinese = "中" * 20
    assert len(english) == len(chinese)
    assert counter.count(english) != counter.count(chinese)
    assert counter.count(chinese) == counter._counts[chinese]
    assert counter.count(chinese) == 20


@pytest.mark.parametrize("soft,hard", [(0, 1), (-1, 2), (3, 2)])
def test_invalid_budgets(soft, hard) -> None:
    with pytest.raises(ValueError):
        MarkdownChunkerConfig(target_chunk_tokens=soft, split_threshold_tokens=hard)
