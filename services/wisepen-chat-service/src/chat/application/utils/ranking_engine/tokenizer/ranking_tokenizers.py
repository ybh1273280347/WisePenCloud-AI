from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import jieba
import thulac
import unicodedata

from .stopwords import DEFAULT_STOPWORDS

# 混合 Token 正则表达式（优先级：compound > alnum > cjk）
# compound：带分隔符的复合词（如 GPT-4、api_key）
# alnum：纯英数 token
# cjk：连续中文字符
_TOKEN_PATTERN = re.compile(
    r"(?P<compound>[A-Za-z0-9]+(?:[._\-/][A-Za-z0-9]+)+)"
    r"|(?P<alnum>[A-Za-z0-9]+)"
    r"|(?P<cjk>[\u4e00-\u9fff]+)"
)
# 复合词内部分隔符（点、下划线、横线、斜杠）
_COMMON_SEPARATOR_PATTERN = re.compile(r"[._\-/]+")


@dataclass(frozen=True, slots=True)
class RankingTokenizerConfig:
    """Ranking Engine 词法分词配置。"""

    normalize_unicode: bool = True  # NFKC 归一化（全角转半角等）
    lowercase_latin: bool = True  # 拉丁 token 统一小写
    remove_stopwords: bool = True  # 过滤停用词
    deduplicate: bool = False  # BM25 通常保留重复词频
    enable_cjk_bigram: bool = True  # 中文 bigram 兜底
    split_common_separators: bool = True  # 按常见分隔符拆复合词
    keep_compound_token: bool = True  # 拆复合词时保留原 token
    min_token_length: int = 1  # 最短 token 长度
    max_tokens: int | None = None  # 防止 token 爆炸


class RankingTokenizer:
    """面向 BM25 / lexical ranking 的 tokenizer 基类。
    子类通过实现 _tokenize_cjk 接入不同中文分词器。
    """

    __slots__ = ("config", "stopwords")

    def __init__(
            self,
            config: RankingTokenizerConfig | None = None,
            stopwords: frozenset[str] | None = None,
    ) -> None:
        self.config = config or RankingTokenizerConfig()
        # 默认使用内置通用停用词表；调用方可传入自定义停用词覆盖
        self.stopwords = DEFAULT_STOPWORDS if stopwords is None else stopwords

    def tokenize(self, text: str) -> tuple[str, ...]:
        """将文本切分为面向排序的 token 序列。"""
        text = text.strip()
        if not text:
            return ()

        # 第一步：Unicode 归一化，统一全角/半角等异体字符
        if self.config.normalize_unicode:
            text = unicodedata.normalize("NFKC", text)

        cfg = self.config
        tokens: list[str] = []

        # 第二步：按正则三模式逐一提取原始 token
        for match in _TOKEN_PATTERN.finditer(text):
            value = match.group(0)
            if match.lastgroup == "cjk":
                # 中文片段：使用子类分词器 + bigram 兜底
                tokens.extend(self._tokenize_cjk(value))
                if cfg.enable_cjk_bigram:
                    tokens.extend(_make_cjk_bigrams(value))
                continue

            # 英数 / 复合词：按配置决定是否拆分
            if not cfg.split_common_separators or not _COMMON_SEPARATOR_PATTERN.search(value):
                tokens.append(value)
                continue

            # 复合词拆分，例如 "GPT-4" → "GPT-4"(原型) + "GPT" + "4"
            if cfg.keep_compound_token:
                tokens.append(value)
            tokens.extend(_split_common_compound(value))

        # 第三步：后处理（小写化、长度过滤、停用词过滤）
        result: list[str] = []
        for token in tokens:
            token = token.strip()
            # 拉丁字母统一转小写，保证大小写不敏感匹配
            if cfg.lowercase_latin and any(char.isascii() and char.isalpha() for char in token):
                token = token.casefold()
            if len(token) < cfg.min_token_length:
                continue
            if cfg.remove_stopwords and token in self.stopwords:
                continue
            result.append(token)

        # 第四步：可选去重与截断
        if cfg.deduplicate:
            result = list(dict.fromkeys(result))
        if cfg.max_tokens is not None:
            result = result[: max(0, cfg.max_tokens)]

        return tuple(result)

    def _tokenize_cjk(self, text: str) -> tuple[str, ...]:
        """模板方法：子类实现具体的中文分词逻辑。"""
        raise NotImplementedError


class JiebaRankingTokenizer(RankingTokenizer):
    """使用 jieba 搜索模式分词的中文 tokenizer。"""

    __slots__ = ("_jieba_tokenizer",)

    def __init__(
            self,
            config: RankingTokenizerConfig | None = None,
            stopwords: frozenset[str] | None = None,
    ) -> None:
        super().__init__(config=config, stopwords=stopwords)
        # jieba.cut_for_search 在精确分词基础上补充粗粒度切分，
        # 适合搜索引擎场景，能覆盖更多候选边界
        self._jieba_tokenizer = jieba.Tokenizer()

    def _tokenize_cjk(self, text: str) -> tuple[str, ...]:
        return tuple(self._jieba_tokenizer.cut_for_search(text))


class ThuLacRankingTokenizer(RankingTokenizer):
    """使用 THULAC 分词的中文 tokenizer。"""

    __slots__ = ("_thulac_tokenizer",)

    def __init__(
            self,
            config: RankingTokenizerConfig | None = None,
            stopwords: frozenset[str] | None = None,
    ) -> None:
        super().__init__(config=config, stopwords=stopwords)
        # seg_only=True 表示只分词不标注词性，提高吞吐
        self._thulac_tokenizer = thulac.thulac(seg_only=True)

    def _tokenize_cjk(self, text: str) -> tuple[str, ...]:
        return _cut_with_thulac(self._thulac_tokenizer, text)


def _make_cjk_bigrams(text: str) -> tuple[str, ...]:
    """为连续中文片段生成 bigram，覆盖分词器未命中的边界。
    对于未登录词或单字切分场景，bigram 是不依赖词典的有效兜底。
    """
    chars = [char for char in text if "\u4e00" <= char <= "\u9fff"]
    if len(chars) < 2:
        return ()
    return tuple(chars[index] + chars[index + 1] for index in range(len(chars) - 1))


def _split_common_compound(token: str) -> tuple[str, ...]:
    """按通用分隔符拆分复合 token，丢弃空片段。
    例如 "deep-learning" → ("deep", "learning")。
    """
    return tuple(part for part in _COMMON_SEPARATOR_PATTERN.split(token) if part)


def _cut_with_thulac(tokenizer: Any, text: str) -> tuple[str, ...]:
    """调用 THULAC 分词并解析输出格式。
    THULAC 默认返回 "word_pos word_pos ..." 格式，每条为 "词_词性"。
    此函数只提取词干，丢弃词性标注。
    """
    segmented = tokenizer.cut(text, text=True)
    if not isinstance(segmented, str):
        return ()

    tokens: list[str] = []
    for part in segmented.split():
        # 取 "_" 前的纯词干部分
        value = part.split("_", 1)[0].strip()
        if value:
            tokens.append(value)
    return tuple(tokens)
