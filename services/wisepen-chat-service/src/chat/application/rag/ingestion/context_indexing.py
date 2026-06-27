from __future__ import annotations

import json
from typing import Any

from chat.application.utils.llm_clients import AdapterQueryClient, build_query_client
from chat.core.config.app_settings import settings

from .models import ContextIndexingInput, ContextIndexingResult

CONTEXT_INDEXING_SYSTEM_PROMPT = """\
<system_prompt>
  <role>你是 WisePen 私有知识库的 Context Indexing 助手。</role>

  <objective>结合 parent_text 和 child_text 生成短上下文，让后续 embedding、Elasticsearch BM25 和图谱抽取消歧更稳定。</objective>

  <rules>
    <rule>只能使用输入中已经给出的信息，不要补充外部知识。</rule>
    <rule>parent_text 是 child_text 所在父块，只用于判断局部语义位置和术语边界。</rule>
    <rule>不要改写 child_text 的事实。</rule>
    <rule>context_summary 必须短，控制在 80 个中文字以内。</rule>
    <rule>important_terms 只保留文档内出现或由标题路径明确给出的术语。</rule>
    <rule>输出必须是严格 JSON，绝对不要带有 Markdown 标记（如 ```json）、不要有任何解释性文字或前后缀。</rule>
  </rules>

  <output_format>
    {
      "context_summary": "这个片段在文档中的局部语义作用",
      "important_terms": ["术语1", "术语2"]
    }
  </output_format>
</system_prompt>
"""


class ContextIndexingError(RuntimeError):
    """Context Indexing 失败，调用方应标记任务可重试。"""


class ContextIndexingService:
    """生成 child chunk 的 indexing_text。"""

    __slots__ = ("_client",)

    def __init__(self, *, client: AdapterQueryClient | None = None) -> None:
        # 允许注入 client 是为了单测时替换成 fake，生产路径走 build_query_client() 的默认配置。
        self._client = client or build_query_client()

    async def build(
            self,
            payload: ContextIndexingInput,
    ) -> ContextIndexingResult:
        try:
            response = await self._client.aquery(
                prompt=_build_llm_prompt(payload),
                system_prompt=CONTEXT_INDEXING_SYSTEM_PROMPT,
                model=settings.SUMMARY_MODEL,
                temperature=0.0,
                max_tokens=256,
            )
            context_summary, important_terms = _parse_llm_payload(response.content)
        except Exception as exc:
            # indexing_text 会进入长期检索索引；失败时不写低质量替代结果，交给入库任务重试。
            raise ContextIndexingError("Context indexing LLM call failed.") from exc

        # evidence_text 保留原始 child_text，检索召回后展示给用户的必须是未被模型改写过的原文。
        indexing_text = _compose_indexing_text(
            payload=payload,
            context_summary=context_summary,
            important_terms=important_terms,
        )
        return ContextIndexingResult(
            evidence_text=payload.child_text.strip(),
            indexing_text=indexing_text,
            context_summary=context_summary,
            important_terms=important_terms,
            usage_tokens=response.usage_tokens,
            metadata={"strategy": "llm_contextualizer"},
        )


def _build_llm_prompt(payload: ContextIndexingInput) -> str:
    section_path = " > ".join(payload.section_path) or "（无章节信息）"
    return "\n".join(
        (
            f"【文档标题】{payload.document_title.strip()}",
            f"【章节路径】{section_path}",
            "",
            "【父块全文 —— 仅用于判断下面 child_text 在文档中的局部语义位置和术语边界，"
            "不要从这一段提取术语，也不要概括这一段的内容】",
            payload.parent_text.strip(),
            "",
            "【待索引子块原文 —— context_summary 和 important_terms 必须只围绕这一段生成】",
            payload.child_text.strip(),
        )
    )


def _parse_llm_payload(content: str) -> tuple[str, tuple[str, ...]]:
    # LLM 输出是外部边界，即使 prompt 要求 JSON，也必须做结构校验。
    payload: Any = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Context indexing response must be a JSON object.")

    context_summary = str(payload.get("context_summary") or "").strip()
    raw_terms = payload.get("important_terms") or []
    if not isinstance(raw_terms, list):
        raise ValueError("important_terms must be a list.")

    important_terms = _dedupe_terms(str(term) for term in raw_terms)
    return context_summary, important_terms


def _compose_indexing_text(
        *,
        payload: ContextIndexingInput,
        context_summary: str,
        important_terms: tuple[str, ...],
) -> str:
    # indexing_text 服务检索和消歧；最终引用仍使用原始 evidence_text。
    parts = [
        ("文档", payload.document_title),
        ("章节", " > ".join(payload.section_path)),
        ("上下文", context_summary),
        ("重要术语", "、".join(important_terms)),
        ("正文", payload.child_text),
    ]
    # 过滤空字段，避免 important_terms 为空时拼出一行多余的 "重要术语: "。
    lines = [
        f"{label}: {value.strip()}"
        for label, value in parts
        if value and value.strip()
    ]
    return "\n".join(lines)


def _dedupe_terms(values: tuple[str, ...] | Any) -> tuple[str, ...]:
    terms: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = str(value).strip()
        if not term or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return tuple(terms)
