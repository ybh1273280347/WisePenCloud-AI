"""为各 contract demo 构造中性、可回源的真实索引产物。"""

from dataclasses import dataclass

from rag.application.rag.index.constructor import (
    build_content_revision_id,
    build_flat_text_sections,
    build_reading_blocks,
    build_retrieval_chunks,
    build_source_refs,
    create_content_revision,
    parse_document_structure,
)
from rag.domain.models.content import ContentRevision, ReadingBlock
from rag.domain.models.provenance import SourceRef
from rag.domain.models.retrieval import RetrievalChunk
from rag.domain.models.structure import DocumentStructure, Section, StructureMode


@dataclass(slots=True)
class DemoDocument:
    """一份 demo 文档及生产索引构造器派生出的完整事实。"""

    resource_id: str
    markdown: str
    revision: ContentRevision
    structure: DocumentStructure
    sections: list[Section]
    reading_blocks: list[ReadingBlock]
    retrieval_chunks: list[RetrievalChunk]
    source_refs: list[SourceRef]


def build_demo_document(*, resource_id: str, markdown: str) -> DemoDocument:
    """执行 ResourceIndexer 中内容派生阶段的同一组生产算法。"""
    content_revision = build_content_revision_id(
        resource_id=resource_id,
        document_version=1,
        markdown=markdown,
    )
    structure = parse_document_structure(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
    )
    revision = create_content_revision(
        resource_id=resource_id,
        document_version=1,
        markdown=markdown,
        structure=structure,
    )
    sections = (
        build_flat_text_sections(
            resource_id=resource_id,
            content_revision=content_revision,
            markdown=markdown,
        )
        if structure.mode is StructureMode.FLAT_TEXT
        else structure.sections
    )
    structure.sections = sections
    reading_blocks = build_reading_blocks(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=sections,
    )
    retrieval_chunks = build_retrieval_chunks(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=sections,
        reading_blocks=reading_blocks,
    )
    source_refs = build_source_refs(
        resource_id=resource_id,
        content_revision=content_revision,
        markdown=markdown,
        structure=structure,
        sections=sections,
        reading_blocks=reading_blocks,
        retrieval_chunks=retrieval_chunks,
    )
    return DemoDocument(
        resource_id=resource_id,
        markdown=markdown,
        revision=revision,
        structure=structure,
        sections=sections,
        reading_blocks=reading_blocks,
        retrieval_chunks=retrieval_chunks,
        source_refs=source_refs,
    )


def sectioned_markdown() -> str:
    return """# 城市雨水花园巡检手册

雨水花园通过下凹绿地、种植土和排水设施暂存并净化地表径流。巡检记录应同时描述天气、积水和植被状态。

<!-- page 1 -->

## 一、降雨后现场巡检

巡检宜在降雨结束后二十四小时内进行。工作人员先记录进水口是否被落叶或泥沙堵塞，再沿设施边缘检查冲刷沟和裸露土面。

## 二、入渗与排水检查

正常情况下，浅层积水会在降雨结束后逐步消退。若四十八小时后仍有连续积水，应复查溢流口、盲管和种植土的含水状态。

### 二.1 土壤表层

土壤板结会降低入渗速度，并使表层积水消退时间延长。检查时可比较高频踩踏区与封闭区的入渗差异，不宜仅凭一次局部积水判断设施失效。

<!-- page 2 -->

### 二.2 排水构件

溢流口周围不得堆积覆盖物。盲管检查口若持续满水，应排查下游管线是否堵塞，并记录水位恢复所需时间。

### 二.3 复核记录

复核记录中的土壤板结样点应附带位置和照片。复核记录中的高频踩踏区还应标注人流方向，便于后续比较治理前后的入渗变化。

## 三、季节性植被维护

春季补植应优先选择耐短时淹水的乡土植物。修剪后保留地表覆盖，减少暴雨直接冲刷种植土。
"""


def flat_text_markdown() -> str:
    return """果园霜冻观测记录，四月十二日。傍晚十八时，坡底测点温度为六点八摄氏度，坡肩测点为八点一摄氏度，风速低于每秒一米。天空晴朗，地表长波辐射散失明显，值班人员因此将本夜判断为辐射降温风险较高。

二十二时三十分，坡底温度降至三点二摄氏度，叶面仍未结霜。工作人员检查风机燃油、转向和警戒范围，并确认灌溉主管无渗漏。按照预案，风机不因单个测点短时下降立即启动，而要结合坡底与坡肩温差、露点和连续下降趋势判断。

次日零时四十分，坡底与坡肩温差扩大到三点四摄氏度，近地层出现稳定逆温。风机于零时四十五分启动，每二十分钟复测一次。启动后坡底温度回升约零点七摄氏度，叶面未发现冰晶。

日出前后最容易出现当夜最低温。值班人员在五时二十分停止风机前，先确认东方云量增加、坡底温度连续三次回升，并保留一组未干预地块作为对照。最终记录应注明仪器编号、校准日期和缺测时段，避免把设备漂移误判为防霜措施效果。
"""
