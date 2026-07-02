from __future__ import annotations

import json
from typing import Any

from chat.application.utils.llm_clients import LiteLLMQueryClient, build_query_client
from chat.core.config.app_settings import settings

from .models import ContextIndexingInput, ContextIndexingResult

CONTEXT_INDEXING_SYSTEM_PROMPT = """\
<system_prompt>
  <role>你是 WisePen 私有知识库的 Context Indexing 助手。</role>

  <objective>结合 parent_text 和 child_text 生成一段上下文补充，让后续 embedding 和 lexical indexing 更稳定。</objective>

  <rules>
    <rule>只能使用输入中已经给出的信息，不要补充外部知识。</rule>
    <rule>parent_text 是 child_text 所在父块，只用于判断 child_text 的局部语义位置。</rule>
    <rule>不要改写 child_text 的事实。</rule>
    <rule>indexing_context 只补充检索需要的上下文，不抽取实体、关系或关键词列表。</rule>
    <rule>indexing_context 必须短，控制在 120 个中文字以内。</rule>
    <rule>输出必须是严格 JSON，绝对不要带有 Markdown 标记（如 ```json）、不要有任何解释性文字或前后缀。</rule>
  </rules>

  <output_format>
    {
      "indexing_context": "这个片段在文档中的局部语义位置和必要上下文"
    }
  </output_format>
</system_prompt>
"""


class ContextIndexingError(RuntimeError):
    """Context Indexing 失败，调用方应标记任务可重试。"""


class ContextIndexingService:
    """生成 child chunk 的 indexing_text。"""

    __slots__ = ("_client",)

    def __init__(self, *, client: LiteLLMQueryClient | None = None) -> None:
        # 允许注入 client 是为了单测时替换成 fake，生产路径按用途固定小模型配置。
        self._client = client or build_query_client(
            model=settings.SUMMARY_MODEL,
        )

    async def build(
        self,
        payload: ContextIndexingInput,
    ) -> ContextIndexingResult:
        try:
            response = await self._client.aquery(
                prompt=_build_llm_prompt(payload),
                system_prompt=CONTEXT_INDEXING_SYSTEM_PROMPT,
                max_tokens=256,
            )
            indexing_context = _parse_llm_payload(response.content)
        except Exception as exc:
            # indexing_text 会进入长期检索索引；失败时不写低质量替代结果，
            # 而是让调用方（入库任务）标记失败并重试，避免污染搜索索引。
            raise ContextIndexingError("Context indexing LLM call failed.") from exc

        indexing_text = _compose_indexing_text(
            payload=payload,
            indexing_context=indexing_context,
        )
        # 返回新的 child_chunk，不修改原 payload 中的对象，保持输入不可变。
        return ContextIndexingResult(
            child_chunk=payload.child_chunk.with_indexing_context(
                indexing_context=indexing_context,
                indexing_text=indexing_text,
            ),
        )


def _build_llm_prompt(payload: ContextIndexingInput) -> str:
    """把 Context Indexing 输入整理成单次小模型提示词。"""
    section_path = " > ".join(payload.child_chunk.section_path) or "（无章节信息）"
    return "\n".join(
        (
            "<context_indexing_input>",
            "  <metadata>",
            f"    <document_title>{payload.document_title.strip()}</document_title>",
            f"    <section_path>{section_path}</section_path>",
            "  </metadata>",
            "",
            "  <parent_text usage=\"只用于判断 child_text 在文档中的局部语义位置；"
            "不要从这一段抽取实体、关系或关键词列表\">",
            payload.parent_text.strip(),
            "  </parent_text>",
            "",
            "  <child_text usage=\"indexing_context 必须只围绕这一段生成\">",
            payload.child_chunk.text.strip(),
            "  </child_text>",
            "</context_indexing_input>",
        )
    )


def _parse_llm_payload(content: str) -> str:
    """解析并校验 Context Indexing 小模型输出。"""
    # LLM 输出是外部边界，即使 prompt 要求 JSON，也必须做结构校验。
    payload: Any = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Context indexing response must be a JSON object.")

    indexing_context = str(payload.get("indexing_context") or "").strip()
    if not indexing_context:
        raise ValueError("indexing_context must not be empty.")
    return indexing_context


def _compose_indexing_text(
    *,
    payload: ContextIndexingInput,
    indexing_context: str,
) -> str:
    # indexing_text 服务检索；最终引用仍使用原始 evidence_text。
    parts = [
        ("文档", payload.document_title),
        ("章节", " > ".join(payload.child_chunk.section_path)),
        ("上下文补充", indexing_context),
        ("正文", payload.child_chunk.text),
    ]
    lines = [
        f"{label}: {value.strip()}"
        for label, value in parts
        if value and value.strip()
    ]
    return "\n".join(lines)
