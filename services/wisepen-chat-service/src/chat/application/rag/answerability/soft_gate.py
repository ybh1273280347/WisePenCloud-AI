from __future__ import annotations

import json
from typing import Any

from chat.application.rag.answerability.models import (
    RagAnswerabilityInput,
    RagAnswerabilityLevel,
    RagAnswerabilityWarning,
    RagAnswerabilityWarningReason,
)
from chat.application.utils.llm_clients import QueryClient, build_query_client
from chat.core.config.app_settings import settings

SOFT_GATE_SYSTEM_PROMPT = """\
<system_prompt>
  <role>
    你是 WisePen 私有知识库 RAG 流程中的 Answerability Soft Gate。
  </role>

  <objective>
    基于用户问题和 Top-K Direct Evidence，评估证据是否足以支持完整、准确的回答。
    你不做硬性拒答，只输出风险等级、风险原因和给主模型的回答策略建议。
    是否最终回答、如何回答，永远由主模型决定。
  </objective>

  <inputs>
    <input name="user_query">用户原始问题。</input>
    <input name="direct_evidence">
      从知识库召回的 Top-K 证据片段。下文出现的 evidence、Top-K evidence、direct evidence 都指这一份输入。
    </input>
  </inputs>

  <hard_constraints>
    <constraint>只允许基于 user_query 与 direct_evidence 判断，禁止引入外部知识、常识补全或训练记忆中的事实。</constraint>
    <constraint>禁止输出 reject、refusal、should_answer 或任何语义等价字段。</constraint>
    <constraint>输出必须是严格合法的 JSON，不要 Markdown 代码块、解释性前缀或后缀。</constraint>
    <constraint>warnings 为空数组时，answerability_level 必须等于 good。</constraint>
  </hard_constraints>

  <downstream_context>
    任何非空 warnings 都会触发下游 Neo4j Ontology Enhancement，带来额外延迟和计算成本。
    因此不要为了保险而习惯性添加 warning；只在证据确实存在对应问题时才添加。
  </downstream_context>

  <warning_reasons>
    <reason name="LOW_DIRECTNESS" severity="mild">证据与问题主题相关，但没有直接回答问题本身。</reason>
    <reason name="PARTIAL_COVERAGE" severity="mild">证据只覆盖了问题的一部分。</reason>
    <reason name="ENTITY_AMBIGUOUS" severity="severe">问题或证据中的关键实体指代不清晰，可能存在多个候选对象。</reason>
    <reason name="CONTEXT_MISMATCH" severity="moderate">证据主题表面相似，但所处语境可能与用户问题所需语境不一致。</reason>
    <reason name="EVIDENCE_CONFLICT" severity="severe">Top-K 证据之间在事实层面存在明显冲突或矛盾。</reason>
  </warning_reasons>

  <severity_mapping>
    <rule>无 warning -> good</rule>
    <rule>仅含 1 个 mild warning -> partial</rule>
    <rule>含 1 个 moderate warning，或 2 个及以上 mild warning -> risky</rule>
    <rule>含任意 severe warning，或同时存在 3 个及以上 warning -> poor</rule>
  </severity_mapping>

  <guidance_principles>
    <principle for="LOW_DIRECTNESS">提示主模型可以回答，但需明确说明证据是间接推断而来，避免使用过强确定性措辞。</principle>
    <principle for="PARTIAL_COVERAGE">提示主模型只回答证据覆盖到的部分，并明确指出剩余部分缺乏依据。</principle>
    <principle for="ENTITY_AMBIGUOUS">提示主模型优先澄清具体指代实体，或列出候选实体分别说明。</principle>
    <principle for="CONTEXT_MISMATCH">提示主模型说明证据所处语境，并提醒该结论是否适用于用户当前语境存疑。</principle>
    <principle for="EVIDENCE_CONFLICT">提示主模型并列呈现冲突说法及其来源，不要擅自选择其一作为定论。</principle>
    <principle for="multiple_warnings">多个 warning 同时出现时，优先级是：澄清实体 > 列出冲突 > 降低确定性 > 限定回答范围；不要简单拼接原则原文。</principle>
  </guidance_principles>

  <output_format>
    {
      "answerability_level": "good | partial | risky | poor",
      "warnings": [],
      "guidance": "string，面向主模型的具体回答策略说明，建议 1-3 句"
    }
  </output_format>

  <output_examples>
    <example>
      <case>证据完全直接回答问题，无歧义无冲突</case>
      <output>{"answerability_level":"good","warnings":[],"guidance":"证据可以完整、直接支持回答，正常作答即可。"}</output>
    </example>
    <example>
      <case>证据只回答了问题的一半</case>
      <output>{"answerability_level":"partial","warnings":["PARTIAL_COVERAGE"],"guidance":"证据仅覆盖问题的一部分，请只回答该部分，并明确告知用户其余部分缺乏依据。"}</output>
    </example>
    <example>
      <case>问题中的实体指代不清，且证据之间互相矛盾</case>
      <output>{"answerability_level":"poor","warnings":["ENTITY_AMBIGUOUS","EVIDENCE_CONFLICT"],"guidance":"请先向用户确认具体指代的实体；若必须先行回答，应并列列出各候选实体对应证据的不同说法，不要擅自合并或选择其一。"}</output>
    </example>
  </output_examples>
</system_prompt>
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
                max_tokens=512,
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
            "  <metadata>",
            f"    <retrieval_profile>{answerability_input.retrieval_profile}</retrieval_profile>",
            "  </metadata>",
            "",
            "  <query>",
            answerability_input.query.strip(),
            "  </query>",
            "",
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
            f"    <evidence index=\"{index}\" citation_id=\"{item.candidate_id}\" score=\"{item.score:.6f}\">",
            text,
            "    </evidence>",
        )
    )


def _parse_soft_gate_payload(content: str) -> RagAnswerabilityWarning:
    """解析并校验 Soft Gate 小模型输出。

    校验逻辑和 prompt 中声明的 severity_mapping 保持一致，防止模型输出自相矛盾。
    """
    payload: Any = json.loads(content)
    if not isinstance(payload, dict):
        raise ValueError("Soft gate response must be a JSON object.")

    level = RagAnswerabilityLevel(str(payload.get("answerability_level") or "").strip())
    raw_warnings = payload.get("warnings") or []
    if not isinstance(raw_warnings, list):
        raise ValueError("Soft gate warnings must be a list.")

    warnings = _dedupe_warning_reasons(raw_warnings)
    # 校验空 warnings 时 answerability_level 必须为 good，避免模型保守性误报。
    if not warnings and level != RagAnswerabilityLevel.GOOD:
        raise ValueError("Soft gate level must be good when warnings is empty.")
    # 校验非空 warnings 时 level 与 severity mapping 一致，否则下游图增强触发条件会被破坏。
    if warnings and level != _infer_answerability_level(warnings):
        raise ValueError("Soft gate level does not match warning severity mapping.")

    return RagAnswerabilityWarning(
        answerability_level=level,
        warnings=warnings,
        guidance=str(payload.get("guidance") or "").strip(),
    )


def _dedupe_warning_reasons(values: list[Any]) -> tuple[RagAnswerabilityWarningReason, ...]:
    reasons: list[RagAnswerabilityWarningReason] = []
    seen: set[RagAnswerabilityWarningReason] = set()
    for value in values:
        reason = RagAnswerabilityWarningReason(str(value).strip().lower())
        if reason in seen:
            continue
        seen.add(reason)
        reasons.append(reason)
    return tuple(reasons)


def _infer_answerability_level(
        warnings: tuple[RagAnswerabilityWarningReason, ...],
) -> RagAnswerabilityLevel:
    """根据 warning 集合推断 answerability_level。

    映射规则必须与 prompt 中的 severity_mapping 完全一致：
    - 无 warning -> good
    - 仅 1 个 mild -> partial
    - 1 个 moderate 或 2 个及以上 mild -> risky
    - 任意 severe 或 3 个及以上 warning -> poor
    """
    if not warnings:
        return RagAnswerabilityLevel.GOOD

    severe_warnings = {
        RagAnswerabilityWarningReason.ENTITY_AMBIGUOUS,
        RagAnswerabilityWarningReason.EVIDENCE_CONFLICT,
    }
    moderate_warnings = {
        RagAnswerabilityWarningReason.CONTEXT_MISMATCH,
    }

    if len(warnings) >= 3 or any(reason in severe_warnings for reason in warnings):
        return RagAnswerabilityLevel.POOR

    mild_warning_count = sum(
        1
        for reason in warnings
        if reason not in severe_warnings and reason not in moderate_warnings
    )
    if any(reason in moderate_warnings for reason in warnings) or mild_warning_count >= 2:
        return RagAnswerabilityLevel.RISKY

    return RagAnswerabilityLevel.PARTIAL
