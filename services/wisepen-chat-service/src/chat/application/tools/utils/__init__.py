from __future__ import annotations

from .batching import batched
from .file_type_detect import (
    FileType,
    detect_file_type,
    detect_file_type_from_bytes,
    detect_mime_type,
)

__all__ = [
    "FileType",
    "batched",
    "detect_file_type",
    "detect_file_type_from_bytes",
    "detect_mime_type",
]