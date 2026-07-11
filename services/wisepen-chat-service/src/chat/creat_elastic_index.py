from __future__ import annotations

import asyncio

from elasticsearch import AsyncElasticsearch

from chat.core.config.app_settings import settings


async def main() -> None:
    index_name = settings.ELASTIC_SEARCH_RAG_INDEX_NAME

    client = AsyncElasticsearch(
        settings.ELASTIC_SEARCH_BASE_URL,
        basic_auth=(
            settings.ELASTIC_SEARCH_USERNAME,
            settings.ELASTIC_SEARCH_PASSWORD,
        ),
        request_timeout=10,
    )

    try:
        info = await client.info()
        print(
            f"Connected to Elasticsearch "
            f"{info['version']['number']} / cluster={info['cluster_name']}"
        )

        if await client.indices.exists(index=index_name):
            print(f"Index already exists: {index_name}")
            return

        await client.indices.create(
            index=index_name,
            settings={
                "number_of_shards": 1,
                "number_of_replicas": 0,
            },
            mappings={
                "dynamic": "strict",
                "properties": {
                    # 主键与版本字段：只做精确过滤、替换和引用。
                    "chunk_id": {
                        "type": "keyword",
                    },
                    "parent_chunk_id": {
                        "type": "keyword",
                    },
                    "resource_id": {
                        "type": "keyword",
                    },
                    "document_version": {
                        "type": "keyword",
                    },
                    "corpus_version": {
                        "type": "keyword",
                    },
                    "content_hash": {
                        "type": "keyword",
                    },

                    # ES strict lexical prefilter 的唯一内容检索字段。
                    "indexing_text": {
                        "type": "text",
                    },

                    # 仅从 _source 返回，不参与倒排索引。
                    "evidence_text": {
                        "type": "text",
                        "index": False,
                    },

                    # 定位和引用元数据。
                    "page_label": {
                        "type": "keyword",
                    },
                    "section_path": {
                        "type": "keyword",
                    },
                    "section_path_text": {
                        "type": "text",
                        "index": False,
                    },
                    "anchor_labels": {
                        "type": "keyword",
                    },
                    "start_offset": {
                        "type": "integer",
                    },
                    "end_offset": {
                        "type": "integer",
                    },

                    # 资源级 ACL。
                    "owner_id": {
                        "type": "keyword",
                    },
                    "readable_users": {
                        "type": "keyword",
                    },

                    # 必须是 nested，保证同一条 ACL 记录内的条件关联。
                    "computed_group_acls": {
                        "type": "nested",
                        "properties": {
                            "group_id": {
                                "type": "keyword",
                            },
                            "is_readable": {
                                "type": "boolean",
                            },
                            "readable_users": {
                                "type": "keyword",
                            },
                            "excluded_read_users": {
                                "type": "keyword",
                            },
                        },
                    },
                },
            },
        )

        print(f"Index created: {index_name}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())