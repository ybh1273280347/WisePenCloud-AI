import threading

import pytest

from chat.application.tools.utils.url import security


@pytest.mark.asyncio
async def test_async_url_validation_runs_sync_dns_validation_in_worker_thread(
        monkeypatch: pytest.MonkeyPatch,
) -> None:
    event_loop_thread = threading.get_ident()
    validation_threads: list[int] = []

    def fake_validate(
            url: str,
            *,
            doh_servers: object,
    ) -> str:
        validation_threads.append(threading.get_ident())
        return url

    monkeypatch.setattr(security, "validate_public_http_url", fake_validate)

    result = await security.validate_public_http_url_async(
        "https://example.com/document.pdf"
    )

    assert result == "https://example.com/document.pdf"
    assert validation_threads
    assert validation_threads[0] != event_loop_thread
