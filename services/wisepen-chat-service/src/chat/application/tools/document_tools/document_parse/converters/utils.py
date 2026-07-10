from __future__ import annotations

import codecs
from typing import Any

from charset_normalizer import from_bytes as detect_encoding
from docling_core.types.doc import ImageRefMode

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentDecodeError,
)

_ALLOWED_CONTROL_BYTES = frozenset({8, 9, 10, 12, 13})
_BINARY_SAMPLE_BYTES = 65_536
_BINARY_CONTROL_RATIO = 0.02

_BOM_ENCODINGS = (
    (codecs.BOM_UTF8, "utf-8-sig"),
    # UTF-32 BOM 必须先于 UTF-16 判断，因为二者前缀重叠。
    (codecs.BOM_UTF32_LE, "utf-32"),
    (codecs.BOM_UTF32_BE, "utf-32"),
    (codecs.BOM_UTF16_LE, "utf-16"),
    (codecs.BOM_UTF16_BE, "utf-16"),
)


def decode_text(raw: bytes, *, file_name: str) -> str:
    """严格解码文本，并拒绝具有明显二进制特征的内容。"""
    error_prefix = f"Failed to decode {file_name}"

    for bom, encoding in _BOM_ENCODINGS:
        if not raw.startswith(bom):
            continue
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError as exc:
            raise DocumentDecodeError(f"{error_prefix}: {exc}.") from exc

    if has_binary_characteristics(raw):
        raise DocumentDecodeError(f"{error_prefix}: content appears to be binary.")

    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        match = detect_encoding(raw).best()

    if match is None or match.chaos > 0.2:
        raise DocumentDecodeError(f"{error_prefix}: encoding is not reliable.")

    text = str(match)
    if "\ufffd" in text:
        raise DocumentDecodeError(f"{error_prefix}: invalid byte sequence.")

    return text


def has_binary_characteristics(raw: bytes) -> bool:
    """通过 NUL 字节和异常控制字符比例判断内容是否具有二进制特征。"""
    if not raw:
        return False

    if b"\x00" in raw:
        return True

    sample = raw[:_BINARY_SAMPLE_BYTES]
    control_count = sum(
        byte < 32 and byte not in _ALLOWED_CONTROL_BYTES
        for byte in sample
    )
    return control_count > len(sample) * _BINARY_CONTROL_RATIO


def export_docling_markdown(document: Any) -> str:
    return str(
        document.export_to_markdown(
            image_mode=ImageRefMode.EMBEDDED,
            traverse_pictures=True,
        ) or ""
    ).strip()

