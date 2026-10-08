
"""TypeSafe JEV 异步决策客户端。"""

from collections.abc import Mapping

from typesafe_sdk import (
    AsyncTypeSafeClient,
    Choice,
    ChoiceAnswer,
    JSONContent,
    Noul,
    Question,
    SystemOneResponse,
)


class DecisionClient:
    """封装 JEV 的单选决策、二元判断和复合决策能力。"""

    def __init__(self, client: AsyncTypeSafeClient) -> None:
        self._client = client

    async def choose(
        self,
        *,
        state: JSONContent,
        instructions: str,
        choices: dict[str, str | None],
    ) -> ChoiceAnswer:
        """从多个候选选项中选择最符合条件的一项。

        choices 的键为选项名称，值为选项描述，可设为 None。
        返回 ChoiceAnswer，包含 choice、confidence 和 probabilities。

        示例：
            result = await decision.choose(
                state={"query": "搜索最新的 AI 论文"},
                instructions="选择最合适的工具",
                choices={
                    "web": "需要搜索互联网",
                    "rag": "需要检索内部知识库",
                    "direct": "不需要调用工具",
                },
            )

            selected = result.choice
            confidence = result.confidence
        """
        response = await self._client.system_one(
            state=state,
            questions={
                "decision": Choice(
                    instructions=instructions,
                    criteria=choices,
                ),
            },
        )
        return response.choices["decision"]

    async def judge(
        self,
        *,
        state: JSONContent,
        instructions: str,
        threshold: float = 0.5,
    ) -> bool:
        """判断条件是否成立，根据概率阈值返回布尔值。

        JEV Noul 返回条件成立的概率，范围为 [0, 1]。
        当概率 >= threshold 时返回 True，否则返回 False。

        示例：
            should_search = await decision.judge(
                state={
                    "query": "2026 年最新的 Agent Memory 研究"
                },
                instructions="回答该问题是否需要联网搜索？",
                threshold=0.8,
            )

            if should_search:
                print("需要联网搜索")
        """
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")

        response = await self._client.system_one(
            state=state,
            questions={
                "decision": Noul(instructions=instructions),
            },
        )
        return response.nouls["decision"].noul >= threshold

    async def decide(
        self,
        *,
        state: JSONContent,
        questions: Mapping[str, Question],
    ) -> SystemOneResponse:
        """一次执行多个具名决策，返回完整的 SDK 响应。

        支持 Choice、Noul、Score 任意组合。
        所有问题共享同一个 state。

        示例：
            response = await decision.decide(
                state={"query": "删除旧知识库中的所有文档"},
                questions={
                    "intent": Choice(
                        instructions="判断操作类型",
                        criteria={
                            "read": "读取数据",
                            "write": "修改数据",
                            "delete": "删除数据",
                        },
                    ),
                    "destructive": Noul(
                        instructions="该操作是否具有破坏性？"
                    ),
                },
            )

            intent = response.choices["intent"].choice
            risk = response.nouls["destructive"].noul
        """
        return await self._client.system_one(
            state=state,
            questions=questions,
        )
