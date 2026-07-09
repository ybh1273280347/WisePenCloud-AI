from __future__ import annotations

from redis.asyncio import Redis

from chat.application.tools.common.tool_run_file_store.core.models import ToolFileRefRecord
from chat.application.tools.common.tool_run_file_store.core.protocols import ToolRunFileRepository
from chat.core.persistence.redis._utils.cache_codec import dumps_cache, loads_cache_or_none
from chat.core.persistence.redis.base import RedisRepository

# --- 全局命名空间配置 ---
_REF_KEY_PREFIX = "wisepen:tool_file_ref:item:"
_SESSION_KEY_PREFIX = "wisepen:tool_file_ref:session:"


class RedisToolRunFileRepository(RedisRepository, ToolRunFileRepository):
    """Redis 元数据仓库，用于 `tfile_*` 引用。"""

    def __init__(self, *, redis_client: Redis) -> None:
        super().__init__(redis_client=redis_client)

    async def put(self, record: ToolFileRefRecord, *, ttl_seconds: int) -> None:
        """写入文件引用元数据。"""
        item_key = self._item_key(record.ref_id)
        session_key = self._session_key(
            user_id=record.user_id,
            session_id=record.session_id,
        )

        # 使用 Pipeline (transaction=True) 保证单体 KV 记录与会话集合添加的原子性
        async with self._redis.pipeline(transaction=True) as pipe:
            await pipe.set(item_key, dumps_cache(record), ex=ttl_seconds)
            await pipe.sadd(session_key, record.ref_id)
            await pipe.expire(session_key, ttl_seconds)
            await pipe.execute()

    async def get(self, ref_id: str) -> ToolFileRefRecord | None:
        """按 tfile_* 引用读取文件引用元数据。"""
        raw = await self._redis.get(self._item_key(ref_id))
        if raw is None:
            return None

        return loads_cache_or_none(raw, ToolFileRefRecord)

    async def delete(self, ref_id: str) -> None:
        """删除文件引用元数据。"""
        await self._redis.delete(self._item_key(ref_id))

    @staticmethod
    def _item_key(ref_id: str) -> str:
        return f"{_REF_KEY_PREFIX}{ref_id}"

    @staticmethod
    def _session_key(*, user_id: str, session_id: str) -> str:
        return f"{_SESSION_KEY_PREFIX}{user_id}:{session_id}"
