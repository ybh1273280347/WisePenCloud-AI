import os
import subprocess
import sys
from types import SimpleNamespace

import pytest
from common.core.exceptions import ServiceException
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

import rag.main as service
from rag.core.config import AppSettings
from rag.domain.error_codes import RagErrorCode


class _Closable:
    def __init__(self, name, events) -> None:
        self.name = name
        self.events = events

    async def close(self):
        self.events.append(f"close:{self.name}")

    async def aclose(self):
        self.events.append(f"close:{self.name}")


class _Mongo(_Closable):
    def __getitem__(self, database_name):
        return {"database": database_name}


class _Neo4j(_Closable):
    async def verify_connectivity(self):
        self.events.append("verify:neo4j")


class _Writer:
    def __init__(self, name, events, *, error=None) -> None:
        self.name = name
        self.events = events
        self.error = error

    async def initialize(self):
        self.events.append(f"initialize:{self.name}")
        if self.error is not None:
            raise self.error

    async def ensure_collection(self):
        self.events.append(f"initialize:{self.name}")
        if self.error is not None:
            raise self.error


class _Consumer:
    def __init__(self, name, events) -> None:
        self.name = name
        self.events = events

    async def start(self):
        self.events.append(f"start:{self.name}")

    async def stop(self):
        self.events.append(f"stop:{self.name}")


class _Nacos:
    def __init__(self, events) -> None:
        self.events = events

    async def register_instance(self):
        self.events.append("register:nacos")

    async def deregister_instance(self):
        self.events.append("deregister:nacos")


class _Container:
    def __init__(self, events, *, schema_error=None) -> None:
        self.events = events
        self._mongo = _Mongo("mongo", events)
        self._redis = _Closable("redis", events)
        self._qdrant = _Closable("qdrant", events)
        self._neo4j = _Neo4j("neo4j", events)
        self._zero = _Closable("zero", events)
        self._embedding = _Closable("embedding", events)
        self._context = _Closable("context", events)
        self._graph_query = _Closable("graph-query", events)
        self._retrieval = _Writer("qdrant", events, error=schema_error)
        self._graph = _Writer("graph", events)
        self._graph_acl = _Writer("graph-acl", events)
        self._consumers = [
            _Consumer("document", events),
            _Consumer("acl", events),
            _Consumer("destroy", events),
        ]

    def mongo_client(self):
        return self._mongo

    def redis_client(self):
        return self._redis

    def qdrant_client(self):
        return self._qdrant

    def neo4j_driver(self):
        return self._neo4j

    def zero_entropy_client(self):
        return self._zero

    def embedding_client(self):
        return self._embedding

    def contextual_text_client(self):
        return self._context

    def graph_query_client(self):
        return self._graph_query

    def retrieval_index_writer(self):
        return self._retrieval

    def knowledge_graph_repository(self):
        return self._graph

    def graph_acl_writer(self):
        return self._graph_acl

    def document_ready_consumer(self):
        return self._consumers[0]

    def acl_recalculate_consumer(self):
        return self._consumers[1]

    def resource_destroy_consumer(self):
        return self._consumers[2]


def _settings():
    return SimpleNamespace(
        MONGODB_DB_NAME="rag-v2",
        FROM_SOURCE_SECRET="secret",
    )


def _patch_lifecycle(monkeypatch, events, *, schema_error=None):
    fake_container = _Container(events, schema_error=schema_error)
    nacos = _Nacos(events)
    monkeypatch.setattr(service, "container", fake_container)
    monkeypatch.setattr(service, "configure_container", lambda *args: None)
    monkeypatch.setattr(
        service,
        "load_bootstrap_settings",
        lambda: SimpleNamespace(
            LOG_LEVEL="INFO",
            SERVICE_NAME="wisepen-rag-service-v2",
            PROFILE="test",
        ),
    )
    monkeypatch.setattr(service, "build_nacos_client_manager", lambda value: nacos)

    async def load_settings(nacos):
        return _settings()

    async def init_beanie(**kwargs):
        events.append("initialize:mongo")

    monkeypatch.setattr(service, "load_settings", load_settings)
    monkeypatch.setattr(service, "init_beanie", init_beanie)
    monkeypatch.setattr(service, "setup_logging_intercept", lambda *args: None)
    monkeypatch.setattr(service, "setup_observability", lambda **kwargs: None)
    return fake_container


def test_app_settings_reject_missing_required_runtime_configuration() -> None:
    with pytest.raises(ValidationError):
        AppSettings.model_validate({})


def test_import_does_not_require_nacos_environment() -> None:
    env = os.environ.copy()
    env.pop("NACOS_SERVER_ADDR", None)

    result = subprocess.run(
        [sys.executable, "-c", "import rag.main; print('ok')"],
        capture_output=True,
        check=False,
        env=env,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "ok"


@pytest.mark.asyncio
async def test_health_contract_without_starting_external_dependencies() -> None:
    app = service.create_app()
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "wisepen-rag-service-v2",
    }


@pytest.mark.asyncio
async def test_http_preserves_rag_business_error_code() -> None:
    app = service.create_app()

    @app.get("/test-error")
    async def test_error() -> None:
        raise ServiceException(RagErrorCode.RESOURCE_CONTENT_NOT_FOUND)

    transport = ASGITransport(app=app, raise_app_exceptions=False)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/test-error")

    assert response.status_code == 200
    assert response.json() == {
        "code": RagErrorCode.RESOURCE_CONTENT_NOT_FOUND.code,
        "msg": RagErrorCode.RESOURCE_CONTENT_NOT_FOUND.msg,
        "data": None,
    }


@pytest.mark.asyncio
async def test_lifecycle_initializes_starts_and_closes_in_reverse_order(
    monkeypatch,
) -> None:
    events = []
    _patch_lifecycle(monkeypatch, events)
    app = FastAPI()

    async with service.lifespan(app):
        assert app.state.from_source_secret == "secret"
        assert events[:8] == [
            "initialize:mongo",
            "initialize:qdrant",
            "initialize:graph",
            "initialize:graph-acl",
            "verify:neo4j",
            "start:document",
            "start:acl",
            "start:destroy",
        ]

    assert events[8:12] == [
        "register:nacos",
        "stop:destroy",
        "stop:acl",
        "stop:document",
    ]
    assert events[-1] == "deregister:nacos"


@pytest.mark.asyncio
async def test_schema_failure_prevents_consumers_and_closes_clients(
    monkeypatch,
) -> None:
    events = []
    _patch_lifecycle(
        monkeypatch,
        events,
        schema_error=RuntimeError("schema failed"),
    )

    with pytest.raises(RuntimeError, match="schema failed"):
        async with service.lifespan(FastAPI()):
            pass

    assert not any(event.startswith("start:") for event in events)
    assert "close:mongo" in events
    assert events[-1] == "deregister:nacos"
