from __future__ import annotations

import json
import zipfile
from pathlib import Path, PurePosixPath

from chat.application.tools.document_tools.document_parse.core.errors import (
    DocumentTooLargeError,
    RemoteParserError,
)
from .page_markers import insert_page_markers
from ..utils import decode_text


def extract_mineru_markdown(
        zip_path: Path,
        *,
        file_name: str,
        max_output_bytes: int,
) -> str:
    """从 MinerU ZIP 中读取 Markdown，并根据 content list 插入页码。"""
    try:
        with zipfile.ZipFile(zip_path) as archive:
            members = [
                info
                for info in archive.infolist()
                if not info.is_dir()
            ]
            markdown_info = _select_markdown(
                members,
                file_name=file_name,
            )
            content_list_info = _select_content_list(
                members,
                file_name=file_name,
            )

            for info in (markdown_info, content_list_info):
                if info.file_size > max_output_bytes:
                    raise DocumentTooLargeError(
                        f"MinerU ZIP member {info.filename} for "
                        f"{file_name} exceeds {max_output_bytes} bytes."
                    )

            markdown = decode_text(
                archive.read(markdown_info),
                file_name=PurePosixPath(markdown_info.filename).name,
            ).strip()

            try:
                content_list = json.loads(
                    decode_text(
                        archive.read(content_list_info),
                        file_name=PurePosixPath(
                            content_list_info.filename
                        ).name,
                    )
                )
            except (ValueError, UnicodeError) as exc:
                raise RemoteParserError(
                    f"MinerU content list for {file_name} "
                    "is not valid JSON."
                ) from exc

            return insert_page_markers(markdown, content_list)

    except (RemoteParserError, DocumentTooLargeError):
        raise
    except zipfile.BadZipFile as exc:
        raise RemoteParserError(
            f"MinerU result for {file_name} is not a valid ZIP archive."
        ) from exc
    except Exception as exc:
        raise RemoteParserError(
            f"Failed to read MinerU result for {file_name}."
        ) from exc


def _select_markdown(
        members: list[zipfile.ZipInfo],
        *,
        file_name: str,
) -> zipfile.ZipInfo:
    markdown_files = [
        info
        for info in members
        if PurePosixPath(info.filename).suffix.lower() == ".md"
    ]
    selected = next(
        (
            info
            for info in markdown_files
            if PurePosixPath(info.filename).name.lower() == "full.md"
        ),
        None,
    ) or (
        markdown_files[0]
        if len(markdown_files) == 1
        else None
    )

    if selected is None:
        raise RemoteParserError(
            f"MinerU result for {file_name} "
            "does not contain unique final Markdown."
        )

    return selected


def _select_content_list(
        members: list[zipfile.ZipInfo],
        *,
        file_name: str,
) -> zipfile.ZipInfo:
    content_lists = [
        info
        for info in members
        if PurePosixPath(info.filename).name.lower().endswith(
            "_content_list.json"
        )
    ]

    if len(content_lists) != 1:
        raise RemoteParserError(
            f"MinerU result for {file_name} "
            "does not contain unique content_list JSON."
        )

    return content_lists[0]