from __future__ import annotations

import asyncio
import httpx
import re
import time
from pathlib import Path

from chat.application.tools.document_tools.document_parse.converters.pdf.mineru_converter import (
    MinerUConverter,
)

PDF_PATH = Path(r"C:\Users\12732\Downloads\2607.05577v1.pdf")
OUTPUT_PATH = Path(r"D:\WisePenCloud-AI\WisePenCloud-AI-new\benchmark_output\test_mineru.md")

_PAGE_MARKER_PATTERN = re.compile(r"<!-- page (\d+) -->")


async def main() -> None:
    if not PDF_PATH.is_file():
        raise FileNotFoundError(PDF_PATH)

    started_at = time.perf_counter()

    async with httpx.AsyncClient(trust_env=False) as http_client:
        converter = MinerUConverter(
            http_client=http_client,
            api_url="http://wisepen-dev-server:8000/file_parse",
        )
        result = await converter.convert(
            PDF_PATH,
            file_name=PDF_PATH.name,
            mime_type="application/pdf",
        )

    elapsed_seconds = time.perf_counter() - started_at
    page_numbers = [
        int(value)
        for value in _PAGE_MARKER_PATTERN.findall(result.markdown)
    ]

    if not page_numbers:
        raise RuntimeError(
            "MinerU conversion succeeded, but no page markers were inserted."
        )

    if page_numbers != sorted(set(page_numbers)):
        raise RuntimeError(
            f"Page markers are duplicated or out of order: {page_numbers}."
        )

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(result.markdown, encoding="utf-8")

    print(f"输入文件：{PDF_PATH}")
    print(f"输出文件：{OUTPUT_PATH}")
    print(f"Markdown：{len(result.markdown.encode('utf-8'))} bytes")
    print(f"页码标记：{len(page_numbers)} 个")
    print(f"页码范围：{page_numbers[0]} - {page_numbers[-1]}")
    print(f"总耗时：{elapsed_seconds:.3f}s")


if __name__ == "__main__":
    asyncio.run(main())
