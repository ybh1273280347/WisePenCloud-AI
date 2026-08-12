"""RAG v2 FastAPI 服务入口与显式运行生命周期。"""

from contextlib import asynccontextmanager

from beanie import init_beanie
from common.core.constants import SecurityConstants
from common.logger import info, setup_logging_intercept
from common.observability import instrument_fastapi_app, setup_observability
from common.security import SecurityContextHolder
from common.security.context import _security_context
from common.web.exception_handlers import setup_global_exception_handlers
from fastapi import FastAPI, Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from rag.api.endpoints import navigation as navigation_endpoints
from rag.api.endpoints import resources as resources_endpoints
from rag.api.exception_handlers import setup_rag_exception_handler
from rag.api.router import api_router
from rag.container import configure_container, container
from rag.core.config import load_bootstrap_settings, load_settings
from rag.core.config.nacos import build_nacos_client_manager
from rag.domain.entities import (
    ContentRevisionEntity,
    GenerationCacheEntity,
    ReadingBlockEntity,
    ResourceAclEntity,
    ResourceIndexStateEntity,
    SectionEntity,
    SourcePartEntity,
    SourceRefEntity,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    bootstrap = load_bootstrap_settings()
    setup_logging_intercept(bootstrap.LOG_LEVEL)
    setup_observability(
        service_name=bootstrap.SERVICE_NAME,
        environment=bootstrap.PROFILE,
    )
    nacos = build_nacos_client_manager(bootstrap)
    settings = await load_settings(nacos)
    configure_container(container, settings)
    app.state.from_source_secret = settings.FROM_SOURCE_SECRET

    mongo_client = container.mongo_client()
    redis_client = container.redis_client()
    qdrant_client = container.qdrant_client()
    neo4j_driver = container.neo4j_driver()
    zero_entropy_client = container.zero_entropy_client()
    embedding_client = container.embedding_client()
    contextual_text_client = container.contextual_text_client()
    graph_query_client = container.graph_query_client()
    started = []
    try:
        await init_beanie(
            database=mongo_client[settings.MONGODB_DB_NAME],
            document_models=[
                ResourceIndexStateEntity,
                ContentRevisionEntity,
                SourcePartEntity,
                SectionEntity,
                ReadingBlockEntity,
                SourceRefEntity,
                ResourceAclEntity,
                GenerationCacheEntity,
            ],
        )
        await container.retrieval_index_writer().ensure_collection()
        await container.knowledge_graph_writer().initialize()
        await container.graph_acl_writer().initialize()
        await neo4j_driver.verify_connectivity()

        consumers = (
            container.document_ready_consumer(),
            container.acl_recalculate_consumer(),
            container.resource_destroy_consumer(),
        )
        for consumer in consumers:
            await consumer.start()
            started.append(consumer)
        await nacos.register_instance()
        info("rag v2 service ready.", service=bootstrap.SERVICE_NAME)
        yield
    finally:
        for consumer in reversed(started):
            await consumer.stop()
        await contextual_text_client.close()
        await graph_query_client.close()
        await embedding_client.close()
        await zero_entropy_client.close()
        await redis_client.aclose()
        await qdrant_client.close()
        await neo4j_driver.close()
        await mongo_client.close()
        await nacos.deregister_instance()


class RuntimeSecurityHeaderMiddleware(BaseHTTPMiddleware):
    """使用 lifespan 加载的密钥校验内部来源并填充请求安全上下文。"""

    async def dispatch(self, request: Request, call_next):
        expected = getattr(request.app.state, "from_source_secret", None)
        if request.headers.get(SecurityConstants.HEADER_FROM_SOURCE) != expected:
            return Response(status_code=404, content="Not Found")

        user_id = request.headers.get(SecurityConstants.HEADER_USER_ID)
        if user_id:
            SecurityContextHolder.set_user_id(user_id)
            identity_type = request.headers.get(
                SecurityConstants.HEADER_IDENTITY_TYPE
            )
            group_roles = request.headers.get(
                SecurityConstants.HEADER_GROUP_ROLE_MAP
            )
            if identity_type:
                SecurityContextHolder.set_identity_type(int(identity_type))
            if group_roles:
                SecurityContextHolder.set_group_role_map(group_roles)
        try:
            return await call_next(request)
        finally:
            _security_context.set({})


def create_app() -> FastAPI:
    app = FastAPI(
        title="WisePen RAG Service v2",
        docs_url="/docs",
        lifespan=lifespan,
    )
    instrument_fastapi_app(app)
    app.add_middleware(RuntimeSecurityHeaderMiddleware)
    setup_global_exception_handlers(app)
    setup_rag_exception_handler(app)
    app.include_router(api_router, prefix="/internal/rag")
    container.wire(modules=[navigation_endpoints, resources_endpoints])

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "service": "wisepen-rag-service-v2"}

    return app


app = create_app()
