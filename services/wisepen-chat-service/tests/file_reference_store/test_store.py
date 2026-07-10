from pathlib import Path

import pytest

from chat.application.tools.common.file_reference_store import FileReferenceStore
from chat.application.tools.common.file_reference_store.core.errors import InvalidFileReferenceError
from chat.application.tools.common.file_reference_store.core.models import FileReferenceRecord


class _MemoryRepository:
    def __init__(self) -> None:
        self.records: dict[str, FileReferenceRecord] = {}

    async def put(self, record: FileReferenceRecord, *, ttl_seconds: int) -> None:
        self.records[record.ref_id] = record

    async def get(self, ref_id: str) -> FileReferenceRecord | None:
        return self.records.get(ref_id)

    async def delete(self, ref_id: str) -> None:
        self.records.pop(ref_id, None)


@pytest.mark.asyncio
async def test_store_publishes_and_resolves_file_reference(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    store = FileReferenceStore(
        repository=_MemoryRepository(),
        root_dir=tmp_path / "refs",
    )

    record = await store.publish_file(
        user_id="user-1",
        session_id="session-1",
        producer="test",
        path=source,
        ref_prefix="web_public",
    )
    resolved = await store.resolve_ref(
        user_id="user-1",
        session_id="session-1",
        ref_id=record.ref_id,
    )

    assert record.ref_id.startswith("file_web_public_")
    assert resolved.path.read_text(encoding="utf-8") == "hello"


@pytest.mark.asyncio
async def test_store_rejects_legacy_or_cross_session_reference(tmp_path: Path) -> None:
    source = tmp_path / "source.txt"
    source.write_text("hello", encoding="utf-8")
    store = FileReferenceStore(
        repository=_MemoryRepository(),
        root_dir=tmp_path / "refs",
    )
    record = await store.publish_file(
        user_id="user-1",
        session_id="session-1",
        producer="test",
        path=source,
    )

    with pytest.raises(InvalidFileReferenceError):
        await store.resolve_ref(
            user_id="user-1",
            session_id="session-1",
            ref_id="tfile_legacy",
        )
    with pytest.raises(InvalidFileReferenceError):
        await store.resolve_ref(
            user_id="user-1",
            session_id="session-2",
            ref_id=record.ref_id,
        )
