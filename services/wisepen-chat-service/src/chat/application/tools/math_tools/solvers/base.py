from __future__ import annotations

from typing import Any, Protocol


class MathSolver(Protocol):
    async def solve(self, task: str, payload: dict[str, Any]) -> Any:
        ...
