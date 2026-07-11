from __future__ import annotations

import json

from chat.application.utils.llm_clients import QueryClient, build_query_client
from chat.core.config.app_settings import settings
from .models import ContextIndexingInput, ContextIndexingResult

CONTEXT_INDEXING_SYSTEM_PROMPT = """\
# 角色

你是 WisePen 私有知识库的 Context Indexing 助手。

# 任务

为 `child_text` 生成简短的 `indexing_context`，补充它在文档中的局部语义位置和检索所需上下文，使 embedding 和 lexical indexing 更稳定。

# 规则

- 严格依据 `parent_text`、`section_path` 和 `child_text` 中的信息生成内容。
- 结合 `parent_text` 判断 `child_text` 的局部语义位置，并通过 `section_path` 补充章节语境。
- 使用输入内容的主体语言；多语言混合时优先跟随 `child_text` 的主要语言。
- 保持简短：中文控制在 120 字以内，其他语言采用相当的简短篇幅。
- 输出内容仅包含严格 JSON 对象。

# 输出格式

{"indexing_context": "这个片段在文档中的局部语义位置和必要上下文"}
"""


class ContextIndexingError(RuntimeError):
    """Context Indexing 失败，调用方应标记任务可重试。"""


class ContextIndexingService:
    """生成 child chunk 的 indexing_text。"""

    __slots__ = ("_client",)

    def __init__(self, *, client: QueryClient | None = None) -> None:
        # 允许注入 client 是为了单测时替换成 fake，生产路径按用途固定小模型配置。
        self._client = client or build_query_client(
            model=settings.QUERY_MODEL,
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
    """按缓存友好的顺序组织 Context Indexing 输入。"""
    section_path = " > ".join(payload.child_chunk.section_path) or "（无章节信息）"
    return "\n".join(
        (
            "<parent_text>",
            payload.parent_text.strip(),
            "</parent_text>",
            "",
            "<section_path>",
            section_path,
            "</section_path>",
            "",
            "<child_text>",
            payload.child_chunk.text.strip(),
            "</child_text>",
        )
    )


def _parse_llm_payload(content: str) -> str:
    """解析并校验 Context Indexing 小模型输出。"""
    # LLM 输出是外部边界，即使 prompt 要求 JSON，也必须做结构校验。
    payload = json.loads(content)
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
        ("章节", " > ".join(payload.child_chunk.section_path)),
        ("上下文补充", indexing_context),
        ("正文", payload.child_chunk.text),
    ]
    return "\n".join(
        f"{label}: {value.strip()}"
        for label, value in parts
        if value and value.strip()
    )