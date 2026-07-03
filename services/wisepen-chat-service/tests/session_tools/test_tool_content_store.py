from __future__ import annotations

import pytest

from chat.application.tools.common.tool_content_store.models import StoredToolContent
from chat.application.tools.common.tool_content_store.store import ToolContentStore


class _RepositoryStub:
    def __init__(self) -> None:
        self.stored: StoredToolContent | None = None

    async def put(self, stored: StoredToolContent) -> None:
        self.stored = stored

    async def get(self, content_id: str) -> StoredToolContent | None:
        if self.stored is None or self.stored.content_id != content_id:
            return None
        return self.stored


@pytest.mark.anyio
async def test_tool_content_store_projects_explicit_index_fields() -> None:
    repository = _RepositoryStub()
    store = ToolContentStore(repository=repository)

    receipt = await store.put(
        session_id="session-1",
        text="\n\n".join(
            (
                "<!-- page 1 -->",
                "# 鉴权",
                "请求必须携带 AppBuilder API Key。",
            )
        ),
    )

    assert receipt is not None
    assert repository.stored is not None
    assert repository.stored.chunks
    assert repository.stored.index is not None

    chunk = repository.stored.chunks[0]
    assert chunk.page_label == "1"
    page_entry = next(
        entry
        for entry in repository.stored.index.entries
        if entry.index_kind == "page"
    )

    assert page_entry.index_name == "page:1"
    assert page_entry.page_label == "1"
    assert page_entry.chunk_indices == (chunk.chunk_index,)
