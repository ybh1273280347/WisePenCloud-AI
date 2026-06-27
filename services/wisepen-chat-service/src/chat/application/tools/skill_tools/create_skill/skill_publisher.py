from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol, runtime_checkable

import httpx

from chat.application.tools.skill_tools.create_skill import SkillAssetFile
from chat.application.tools.skill_tools.create_skill.serializer import SkillAssetFile
from chat.service_client import AIAssetClient


@dataclass(frozen=True, slots=True)
class SkillPublishResult:
    skill_id: str
    version: int
    published_at: datetime
    status: str


@runtime_checkable
class SkillPublisher(Protocol):
    async def publish(
        self,
        *,
        skill_id: str,
        title: str,
        trigger_description: str,
        description: str,
        assets: list[SkillAssetFile],
    ) -> SkillPublishResult:
        ...


class AIAssetSkillPublisher:
    """基于 Java ai-asset-service 的 Skill 发布实现。

    按顺序执行三步流程：
    1. 调用 createSkill 创建 Skill 基本信息，获得 resourceId
    2. 调用 initUploadSkillAssets 批量申请上传凭证，然后并发 PUT 上传文件内容
    3. 调用 publishSkillVersion 将草案版本发布为正式版本

    替代了原先 zip 压缩包一键上传的方式，改为逐文件上传，与 Java 端 API 对齐。
    """

    def __init__(self, ai_asset_client: AIAssetClient) -> None:
        self._ai_asset_client = ai_asset_client

    async def publish(
        self,
        *,
        skill_id: str,
        title: str,
        trigger_description: str,
        description: str,
        assets: list[SkillAssetFile],
    ) -> SkillPublishResult:
        """发布 Skill 的主入口方法。

        Args:
            skill_id: Skill 唯一标识（英文 kebab-case）
            title: Skill 显示标题
            trigger_description: 触发描述（用于技能发现）
            description: Skill 描述文本
            assets: 待上传的资源文件列表
            user_id: 当前用户 ID
            session_id: 当前会话 ID

        Returns:
            SkillPublishResult 发布结果
        """
        # ---- 第一步：创建 Skill 基本信息 ----
        # 调用 Java 端 createSkill 接口，生成 resourceId 并自动创建版本 1 草案

        resource_id = await self._ai_asset_client.create_skill(
            title=title,
            name=skill_id,
            description=description or trigger_description,
        )

        # 首版草案版本号固定为 1
        draft_version = 1

        # ---- 第二步：批量申请上传凭证，然后并发上传文件 ----
        # 构造上传申请列表，每个文件指定路径、名称、类型和预期大小
        assets_payload = [
            {
                "name": asset.name,
                "path": asset.path,
                "skillAssetResourceType": asset.asset_type,
                "expectedSize": len(asset.content.encode("utf-8")),
            }
            for asset in assets
        ]

        # 调用 initUploadSkillAssets 接口，一次性获取所有文件的上传凭证
        upload_init_resp = await self._ai_asset_client.init_upload_skill_assets(
            resource_id=resource_id,
            draft_version=draft_version,
            assets=assets_payload
        )

        upload_tickets = upload_init_resp.get("assetUploadTickets", [])

        # 使用 httpx 并发上传所有需要 PUT 的文件
        # flashUploaded 为 true 表示秒传成功，无需再次上传
        async with httpx.AsyncClient() as http_client:
            tasks = []
            for ticket in upload_tickets:
                put_url = ticket.get("putUrl")
                if not put_url or ticket.get("flashUploaded"):
                    continue
                # 根据 path 和 name 匹配对应的 asset，获取文件内容
                asset = next(
                    (a for a in assets if a.path == ticket.get("path") and a.name == ticket.get("name")),
                    None,
                )
                if asset is None:
                    continue
                tasks.append(self._upload_file(http_client, put_url, asset.content))
            if tasks:
                await asyncio.gather(*tasks)

        # ---- 第三步：发布 Skill 版本 ----
        # 将版本 1 草案从 DRAFT 状态发布为 PUBLISHED 状态
        await self._ai_asset_client.publish_skill_version(
            resource_id=resource_id,
            draft_version=draft_version,
        )

        return SkillPublishResult(
            skill_id=resource_id,
            version=draft_version,
            published_at=datetime.now(timezone.utc),
            status="published",
        )

    async def _upload_file(self, http_client: httpx.AsyncClient, put_url: str, content: str) -> None:
        """使用 PUT 请求上传单个文件到对象存储。

        Args:
            http_client: httpx 异步客户端实例
            put_url: 预签名的上传 URL
            content: 文件文本内容（会编码为 UTF-8 字节）
        """
        resp = await http_client.put(put_url, content=content.encode("utf-8"))
        resp.raise_for_status()
