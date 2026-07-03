from __future__ import annotations

from typing import List, Optional, Set

from chat.domain.entities import SkillMeta, Skill
from common.core.exceptions import RpcError
from common.http.rpc_client import RpcClient

_DEFAULT_SERVICE_NAME = "wisepen-ai-asset-service"
_GET_SKILL_PATH = "/internal/skill/getSkillByResourceId"
_LIST_PUBLISHED_SKILLS_META_PATH = "/internal/skill/listPublishedSkillsMetaByResourceIds"
# 创建 Skill 基本信息
_CREATE_SKILL_PATH = "/skill/createSkill"
# 批量申请 Skill 资源文件上传凭证
_INIT_UPLOAD_SKILL_ASSETS_PATH = "/skill/initUploadSkillAssets"
# 发布 Skill 版本（将草案转为正式版）
_PUBLISH_SKILL_VERSION_PATH = "/skill/publishSkillVersion"


class AIAssetClient:
    def __init__(
            self,
            rpc: RpcClient,
            *,
            service_name: str = _DEFAULT_SERVICE_NAME,
    ) -> None:
        self._rpc = rpc
        self._service_name = service_name

    async def list_published_skills_meta(self, skill_ids: Set[str]) -> List[SkillMeta]:
        payloads = await self._list_published_skills_meta_by_resource_ids(skill_ids)
        metas = [SkillMeta.from_response(item) for item in payloads]
        return [meta for meta in metas if meta.skill_id]

    async def get_skill_with_version(self, skill_id: str, skill_version: int) -> Optional[Skill]:
        published_skill_res = await self._get_skill_by_resource_id(skill_id, skill_version)
        return Skill.from_response(published_skill_res)

    async def get_published_skill(self, skill_id: str) -> Optional[Skill]:
        published_skill_res = await self._get_skill_by_resource_id(skill_id)
        return Skill.from_response(published_skill_res)

    async def _get_skill_by_resource_id(self, resource_id: str, skill_version: int = None) -> dict:
        try:
            data = await self._rpc.get(
                self._service_name,
                _GET_SKILL_PATH,
                params={"resourceId": resource_id, "skillVersion": skill_version},
            )
        except RpcError as e:
            raise e
        if not isinstance(data, dict):
            raise RpcError(
                service_name=self._service_name, path=_GET_SKILL_PATH,
                msg=f"unexpected data payload: {data!r}",
            )
        return data

    async def _list_published_skills_meta_by_resource_ids(self, resource_ids: Set[str]) -> List[dict]:
        try:
            data = await self._rpc.post(
                self._service_name,
                _LIST_PUBLISHED_SKILLS_META_PATH,
                json={"resourceIds": sorted(resource_ids)},
            )
        except RpcError as e:
            raise e
        if not isinstance(data, list):
            raise RpcError(
                service_name=self._service_name, path=_LIST_PUBLISHED_SKILLS_META_PATH,
                msg=f"unexpected data payload: {data!r}",
            )
        return data

    async def create_skill(self, *, title: str, name: str = None, description: str = None,
                           source_type: str = "BY_AGENT") -> str:
        """创建 Skill 基本信息。

        调用 Java 端 /skill/createSkill 接口，生成 resourceId 并自动创建版本 1 草案。
        source_type 默认为 BY_AGENT，表示由 AI Agent 创建的技能。

        Args:
            title: Skill 标题（必填）
            name: Skill 名称，默认与 title 相同
            description: Skill 描述，默认为空字符串
            source_type: 来源类型，默认 BY_AGENT

        Returns:
            新创建的 Skill 的 resourceId

        Raises:
            RpcError: 调用失败或返回格式异常
        """
        try:
            data = await self._rpc.post(
                self._service_name,
                _CREATE_SKILL_PATH,
                json={
                    "title": title,
                    # name 为空时使用 title 作为默认值
                    "name": name or title,
                    "description": description or "",
                    "sourceType": source_type,
                },
            )
        except RpcError as e:
            raise e
        if not isinstance(data, str):
            raise RpcError(
                service_name=self._service_name, path=_CREATE_SKILL_PATH,
                msg=f"unexpected data payload: {data!r}",
            )
        return data

    async def init_upload_skill_assets(
            self,
            *,
            resource_id: str,
            draft_version: int,
            assets: List[dict],
    ) -> dict:
        """批量申请 Skill 资源文件的上传凭证。

        调用 Java 端 /skill/initUploadSkillAssets 接口，为每个文件获取预签名的 putUrl。
        调用方需自行使用 PUT 请求上传文件内容。

        Args:
            resource_id: Skill 的 resourceId
            draft_version: 草案版本号
            assets: 待上传的文件列表，每个元素包含 name、path、skillAssetResourceType、expectedSize 等字段

        Returns:
            包含 assetUploadTickets 的响应字典，每个 ticket 含 assetId、putUrl、flashUploaded 等

        Raises:
            RpcError: 调用失败或返回格式异常
        """
        try:
            data = await self._rpc.post(
                self._service_name,
                _INIT_UPLOAD_SKILL_ASSETS_PATH,
                json={
                    "resourceId": resource_id,
                    "draftVersion": draft_version,
                    "assets": assets,
                },
            )
        except RpcError as e:
            raise e
        if not isinstance(data, dict):
            raise RpcError(
                service_name=self._service_name, path=_INIT_UPLOAD_SKILL_ASSETS_PATH,
                msg=f"unexpected data payload: {data!r}",
            )
        return data

    async def publish_skill_version(self, *, resource_id: str, draft_version: int) -> None:
        """发布 Skill 版本，将草案版本转为正式版本。

        调用 Java 端 /skill/publishSkillVersion 接口。
        发布前需确保所有资源文件已上传完成且状态为 AVAILABLE。

        Args:
            resource_id: Skill 的 resourceId
            draft_version: 要发布的草案版本号

        Raises:
            RpcError: 调用失败
        """
        try:
            await self._rpc.post(
                self._service_name,
                _PUBLISH_SKILL_VERSION_PATH,
                json={
                    "resourceId": resource_id,
                    "draftVersion": draft_version,
                },
            )
        except RpcError as e:
            raise e
