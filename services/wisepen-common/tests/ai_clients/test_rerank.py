from http import HTTPStatus
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from common.utils.ai_clients import RerankClient


@pytest.mark.asyncio
async def test_rerank_forwards_instruction_and_projects_sdk_results():
    call = AsyncMock(
        return_value=SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(
                results=[
                    SimpleNamespace(index=1, relevance_score=0.9),
                    SimpleNamespace(index=0, relevance_score=0.2),
                ]
            ),
        )
    )

    with patch("common.utils.ai_clients.rerank.AioTextReRank.call", call):
        result = await RerankClient().rerank(
            model="rerank-model",
            query="query",
            documents=["first", "second"],
            instruct="prefer exact product matches",
            top_n=2,
        )

    assert result == [
        {"index": 1, "relevance_score": 0.9},
        {"index": 0, "relevance_score": 0.2},
    ]
    call.assert_awaited_once_with(
        model="rerank-model",
        query="query",
        documents=["first", "second"],
        instruct="prefer exact product matches",
        top_n=2,
    )


@pytest.mark.asyncio
async def test_rerank_passes_optional_arguments_as_none():
    call = AsyncMock(
        return_value=SimpleNamespace(
            status_code=HTTPStatus.OK,
            output=SimpleNamespace(results=[]),
        )
    )
    with patch("common.utils.ai_clients.rerank.AioTextReRank.call", call):
        result = await RerankClient().rerank(
            model="rerank-model", query="query", documents=["document"]
        )

    assert result == []
    call.assert_awaited_once_with(
        model="rerank-model",
        query="query",
        documents=["document"],
        instruct=None,
        top_n=None,
    )


@pytest.mark.asyncio
async def test_rerank_raises_for_non_success_status():
    response = SimpleNamespace(
        status_code=HTTPStatus.BAD_REQUEST,
        code="BadRequest",
        message="invalid request",
    )
    call = AsyncMock(return_value=response)
    with (
        patch("common.utils.ai_clients.rerank.AioTextReRank.call", call),
        pytest.raises(RuntimeError, match="BadRequest: invalid request"),
    ):
        await RerankClient().rerank(model="m", query="q", documents=["d"])
