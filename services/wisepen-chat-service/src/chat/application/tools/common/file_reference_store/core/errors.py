class FileReferenceStoreError(Exception):
    """文件引用存储的基础异常。"""


class InvalidFileReferenceError(FileReferenceStoreError):
    """传入的文件引用格式非法，或不属于当前用户/会话作用域。"""


class ReferencedFileNotFoundError(FileReferenceStoreError):
    """文件引用不存在、已过期，或指向的文件已经被清理。"""


class ReferencedFileUnreadableError(FileReferenceStoreError):
    """引用文件存在，但无法安全读取或校验失败。"""


class FileReferenceWriteError(FileReferenceStoreError):
    """发布文件或创建暂存目录失败。"""


def file_reference_error_reason(
        error: BaseException,
        *,
        default: str = "file_ref_unavailable",
) -> str:
    """将文件引用异常映射为稳定的模型可见 reason。"""
    if isinstance(error, InvalidFileReferenceError):
        return "invalid_file_ref"
    if isinstance(error, ReferencedFileNotFoundError):
        return "file_ref_unavailable"
    if isinstance(error, ReferencedFileUnreadableError):
        return "file_unreadable"
    return default
