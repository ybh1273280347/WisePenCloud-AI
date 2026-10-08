"""把 active Document 的 Section 事实交给 Common 格式化为导航 Markdown。"""

from dataclasses import dataclass

from common.utils.markdown import OutlineFormatter, Section

from rag.application.reading import DocumentReadError
from rag.application.snapshot import ActiveDocumentSnapshotLoader
from rag.domain.acl import PermissionScope


@dataclass(frozen=True, slots=True)
class NeighborhoodItem:
    """单个 section 的邻域大纲信息。"""

    resource_id: str
    section_id: str
    section_path: str
    outline: str


class OutlineBuilder:
    """加载可见文档事实，并委托 Common 格式化 outline。"""

    def __init__(self, *, snapshots: ActiveDocumentSnapshotLoader) -> None:
        self._snapshots = snapshots

    async def neighborhood(
        self,
        section_ids: list[str],
        *,
        sibling_steps: int = 1,
        scope: PermissionScope,
    ) -> list[NeighborhoodItem]:
        """为每个可见 section 生成独立邻域窗口。"""
        locations = await self._snapshots.locate_sections(section_ids, scope=scope)
        items: list[NeighborhoodItem] = []
        formatters: dict[str, OutlineFormatter] = {}
        for section_id in section_ids:
            location = locations.get(section_id)
            if location is None:
                # 不存在、旧 revision 和无权 Section 对外必须不可区分。
                raise DocumentReadError("section is not visible")

            structure = location.document.structure
            formatter = formatters.get(location.document.resource_id)
            if formatter is None:
                formatter = OutlineFormatter(
                    sections=structure.sections,
                    anchors=structure.anchors,
                )
                formatters[location.document.resource_id] = formatter
            items.append(
                _item(
                    location.document,
                    location.section,
                    formatter.neighborhood(
                        section_id,
                        sibling_steps=sibling_steps,
                    ),
                )
            )
        return items

    async def global_outline(
        self,
        resource_id: str,
        *,
        max_level: int = 2,
        scope: PermissionScope,
    ) -> str:
        """加载 active 文档并按树深度生成全局目录。"""
        documents = await self._snapshots.load_documents([resource_id], scope=scope)
        document = documents.get(resource_id)
        if document is None:
            raise DocumentReadError("document is not visible")

        return OutlineFormatter(
            sections=document.structure.sections,
            anchors=document.structure.anchors,
        ).global_outline(max_level=max_level)


def _item(document, section: Section, outline: str) -> NeighborhoodItem:
    """从可见文档和 section 构造邻域结果。"""
    return NeighborhoodItem(
        resource_id=document.resource_id,
        section_id=section.section_id,
        section_path=" > ".join(section.section_path),
        outline=outline,
    )
