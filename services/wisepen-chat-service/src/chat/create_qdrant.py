from __future__ import annotations

import argparse
import asyncio

from qdrant_client import AsyncQdrantClient, models

from chat.core.config.app_settings import settings

_DEFAULT_COLLECTION_NAME = "wisepen_rag_child_chunks"


async def create_collection(
        *,
        collection_name: str,
        dense_vector_name: str,
        dense_vector_size: int,
        sparse_vector_name: str,
) -> None:
    client = AsyncQdrantClient(
        host=settings.QDRANT_HOST.strip(),
        port=settings.QDRANT_PORT,
        https=False,
        api_key=settings.QDRANT_PASSWORD or None,
        check_compatibility=False,
    )

    try:
        if await client.collection_exists(collection_name):
            print(f"Collection already exists: {collection_name}")
            return

        await client.create_collection(
            collection_name=collection_name,
            vectors_config={
                dense_vector_name: models.VectorParams(
                    size=dense_vector_size,
                    distance=models.Distance.COSINE,
                ),
            },
            sparse_vectors_config={
                sparse_vector_name: models.SparseVectorParams(),
            },
        )

        print(
            f"Collection created: {collection_name}\n"
            f"  dense:  name={dense_vector_name}, size={dense_vector_size}, "
            f"distance=Cosine\n"
            f"  sparse: name={sparse_vector_name}"
        )
    finally:
        await client.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Create the WisePen child-chunk Qdrant collection.",
    )
    parser.add_argument(
        "--collection",
        default=_DEFAULT_COLLECTION_NAME,
    )
    parser.add_argument(
        "--dense-name",
        default="dense",
    )
    parser.add_argument(
        "--dense-size",
        type=int,
        required=True,
    )
    parser.add_argument(
        "--sparse-name",
        default="sparse",
    )
    args = parser.parse_args()

    asyncio.run(
        create_collection(
            collection_name=args.collection,
            dense_vector_name=args.dense_name,
            dense_vector_size=args.dense_size,
            sparse_vector_name=args.sparse_name,
        )
    )


if __name__ == "__main__":
    main()