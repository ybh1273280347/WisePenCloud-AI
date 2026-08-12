"""RAG v2 对外服务错误码。"""

from common.core.domain import IErrorCode


class RagErrorCode(IErrorCode):
    RESOURCE_CONTENT_NOT_FOUND = (42004, "资源内容不存在或不可访问")
    RESOURCE_READ_FAILED = (52002, "资源读取服务不可用")
