from __future__ import annotations


class DocumentParseError(Exception):
    """文档解析异常基类，携带原始异常。"""

    def __init__(
        self,
        message: str,
        *,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause


class DocumentParserError(DocumentParseError):
    """单个解析器或专用策略内部失败。"""


class DocumentParseFailedError(DocumentParseError):
    """通用解析链路整体失败。"""
