from __future__ import annotations

from typing import Protocol

from .models import ToolFileRefRecord


class ToolRunFileRepository(Protocol):
    """短期工具文件引用的元数据持久化协议。"""

    async def put(self, record: ToolFileRefRecord, *, ttl_seconds: int) -> None:
        """写入引用记录。"""
        ...

    async def get(self, ref_id: str) -> ToolFileRefRecord | None:
        """按 tfile_* 引用读取记录，不存在时返回 None。"""
        ...

    async def delete(self, ref_id: str) -> None:
        """删除指定 tfile_* 引用记录。"""
        ...
