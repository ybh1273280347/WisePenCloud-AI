from __future__ import annotations

import json
from typing import Any

from chat.application.rag.answerability.models import (
    RagAnswerabilityInput,
    RagAnswerabilityWarning,
    RagAnswerabilityWarningReason,
)
from chat.application.utils.llm_clients import QueryClient, build_query_client
from chat.application.utils.xml_markup import xml_attr, xml_cdata, xml_text
from chat.core.config.app_settings import settings

SOFT_GATE_SYSTEM_PROMPT = """\
# 角色

你是 RAG 证据风险检查器。

# 任务

只根据用户问题和 `direct_evidence`，输出给主模型的证据风险提示。

# 输入

运行期输入是 XML：

- `<retrieval_profile>` 是检索画像。
- `<user_query>` 是用户问题。
- `<direct_evidence>` 是 Top-K 证据列表。
- `<evidence>` 的 `citation_id` 和 `score` 只用于定位证据，不代表你可以引入外部事实。

# 基本规则

- 不使用外部知识、常识或训练记忆。
- 不决定是否回答，不拒答，不输出 `reject`、`refusal` 或 `should_answer`。
- 非空 `warnings` 会触发额外图增强；不要为了保险添加 warning。
- 只输出严格 JSON，不要 Markdown 或解释。

# 决策顺序

- 若证据显式包含完整答案，且无需补全、无歧义、无冲突，必须返回空 `warnings`。
- 若问题包含多个明确子项，证据缺失任一子项，使用 `PARTIAL_COVERAGE`，优先于 `LOW_DIRECTNESS`。
- 其余情况再按 warning 定义选择；可以返回多个 warning。

# Warning 定义

`warnings` 数组只能包含下面 5 个枚举值，必须保持枚举名原文，不要创造新 warning：

- `LOW_DIRECTNESS`：需两步以上推理才能得出答案，或只给背景，未包含答案所需的具体数值、实体或结论。
- `PARTIAL_COVERAGE`：问题有多个明确子项，证据缺失至少一个子项。
- `ENTITY_AMBIGUOUS`：同一证据内或跨证据间，同一字符串指代两个不同且无法区分的实体。
- `CONTEXT_MISMATCH`：证据的时间、地域、假设前提或数据口径，与问题的明确限定条件冲突。
- `EVIDENCE_CONFLICT`：Top-K 证据之间存在事实冲突。

不允许输出其他 warning；其他值不会被下游当作有效 warning。

# 输出格式

只输出一个 JSON 对象，结构为 `{"warnings":[],"guidance":"给主模型的一句简短回答建议"}`。
"""


class AnswerabilitySoftGateError(RuntimeError):
    """Soft Gate 小模型输出不可用。"""


class AnswerabilitySoftGate:
    """判断 direct evidence 风险，并触发后续图增强。"""

    __slots__ = ("_client",)

    def __init__(self, *, client: QueryClient | None = None) -> None:
        self._client = client or build_query_client(model=settings.QUERY_MODEL)

    async def evaluate(
            self,
            answerability_input: RagAnswerabilityInput,
    ) -> RagAnswerabilityWarning:
        try:
            response = await self._client.aquery(
                prompt=_build_soft_gate_prompt(answerability_input),
                system_prompt=SOFT_GATE_SYSTEM_PROMPT,
                max_tokens=256,
            )
            return _parse_soft_gate_payload(response.content)
        except Exception as exc:
            raise AnswerabilitySoftGateError("Answerability soft gate LLM call failed.") from exc


def _build_soft_gate_prompt(answerability_input: RagAnswerabilityInput) -> str:
    evidence_blocks = [
        _format_evidence_block(index=index, item=item)
        for index, item in enumerate(answerability_input.ranked[:8], start=1)
    ]
    return "\n".join(
        (
            "<answerability_soft_gate_input>",
            f"  <retrieval_profile>{xml_text(answerability_input.retrieval_profile)}</retrieval_profile>",
            f"  <user_query>{xml_cdata(answerability_input.query.strip())}</user_query>",
            "  <direct_evidence>",
            *evidence_blocks,
            "  </direct_evidence>",
            "</answerability_soft_gate_input>",
        )
    )


def _format_evidence_block(*, index: int, item: Any) -> str:
    text = item.candidate.text.strip()
    if len(text) > 1200:
        text = f"{text[:1200]}..."

    return "\n".join(
        (
            (
                f"    <evidence index=\"{index}\" "
                f"citation_id=\"{xml_attr(item.candidate_id)}\" "
                f"score=\"{item.score:.6f}\">"
            ),
            f"      <text>{xml_cdata(text)}</text>",
            "    </evidence>",
        )
    )


def _parse_soft_gate_payload(content: str) -> RagAnswerabilityWarning:
    """解析 Soft Gate 小模型输出。"""
    payload: Any = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Soft gate response must be a JSON object.")

    raw_warnings = payload.get("warnings") or []
    if not isinstance(raw_warnings, list):
        raise ValueError("Soft gate warnings must be a list.")

    warnings = _dedupe_warning_reasons(raw_warnings)
    return RagAnswerabilityWarning(
        warnings=warnings,
        guidance=str(payload.get("guidance") or "").strip(),
    )


def _dedupe_warning_reasons(values: list[Any]) -> tuple[RagAnswerabilityWarningReason, ...]:
    reasons: list[RagAnswerabilityWarningReason] = []
    seen: set[RagAnswerabilityWarningReason] = set()
    for value in values:
        try:
            reason = RagAnswerabilityWarningReason(str(value).strip().lower())
        except ValueError:
            continue
        if reason in seen:
            continue
        seen.add(reason)
        reasons.append(reason)
    return tuple(reasons)
