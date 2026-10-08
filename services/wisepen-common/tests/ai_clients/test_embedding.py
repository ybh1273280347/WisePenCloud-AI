from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from common.utils.ai_clients import EmbeddingClient


@pytest.mark.asyncio
async def test_embed_forwards_optional_dimensions_and_preserves_vectors():
    create = AsyncMock(
        return_value=SimpleNamespace(
            data=[
                SimpleNamespace(index=1, embedding=(3.0, 4.0)),
                SimpleNamespace(index=0, embedding=(1.0, 2.0)),
            ]
        )
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    result = await EmbeddingClient(client).embed(
        model="text-embedding", texts=["a", "b"], dimensions=2
    )

    assert result == [[1.0, 2.0], [3.0, 4.0]]
    create.assert_awaited_once_with(
        model="text-embedding", input=["a", "b"], dimensions=2
    )


@pytest.mark.asyncio
async def test_embed_omits_dimensions_when_unspecified():
    create = AsyncMock(
        return_value=SimpleNamespace(data=[SimpleNamespace(index=0, embedding=(1.0,))])
    )
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))

    result = await EmbeddingClient(client).embed(model="text-embedding", texts=["a"])

    assert result == [[1.0]]
    create.assert_awaited_once_with(model="text-embedding", input=["a"])


@pytest.mark.asyncio
async def test_embed_rejects_empty_input_and_mismatched_response():
    with pytest.raises(ValueError, match="must not be empty"):
        await EmbeddingClient(SimpleNamespace()).embed(model="m", texts=[])

    create = AsyncMock(return_value=SimpleNamespace(data=[]))
    client = SimpleNamespace(embeddings=SimpleNamespace(create=create))
    with pytest.raises(ValueError, match="count"):
        await EmbeddingClient(client).embed(model="m", texts=["a"])
