"""OpenAI embedding 异步公共客户端。"""

from __future__ import annotations

from openai import AsyncOpenAI


class EmbeddingClient:
    """封装 OpenAI embedding 请求并返回按输入顺序排列的向量。"""

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    async def embed(
        self,
        *,
        model: str,
        texts: list[str],
        dimensions: int | None = None,
    ) -> list[list[float]]:
        """异步生成文本向量。

        Args:
            model: 供应商支持的 embedding 模型名称。
            texts: 待向量化的文本列表，不能为空。
            dimensions: 可选，仅在需要显式指定维度时传给供应商。

        Returns:
            与输入顺序严格对应的向量列表。

        Raises:
            ValueError: 当 texts 为空，或返回结果数量与输入不一致时。
        """
        if not texts:
            raise ValueError("embedding texts must not be empty")

        kwargs: dict[str, object] = {
            "model": model,
            "input": texts,
        }
        if dimensions is not None:
            kwargs["dimensions"] = dimensions

        response = await self._client.embeddings.create(**kwargs)

        # 依据 item.index 排序，严格保障返回向量顺序与输入文本完全对应
        sorted_data = sorted(response.data, key=lambda item: item.index)
        vectors = [list(item.embedding) for item in sorted_data]

        if len(vectors) != len(texts):
            raise ValueError("embedding response count does not match texts")

        return vectors