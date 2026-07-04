from __future__ import annotations


def source_scope_from_metadata(metadata: dict[str, object]) -> str | None:
    value = metadata.get("source_scope")
    return str(value) if isinstance(value, str) and value else None


def string_metadata(metadata: dict[str, object], key: str) -> str | None:
    value = metadata.get(key)
    return str(value) if isinstance(value, str) and value else None
