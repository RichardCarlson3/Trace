import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.services.openalex import OpenAlexService


def test_bounded_rate_limit_retries(monkeypatch):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429)

    monkeypatch.setattr("app.services.openalex.asyncio.sleep", AsyncMock())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexService(client, Settings(_env_file=None))
            with pytest.raises(ServiceError) as error:
                await service.search("test", 1, 10)
            assert error.value.status_code == 503

    asyncio.run(run())
    assert len(calls) == 3


def test_transient_failure_recovers(monkeypatch, openalex_fixture):
    calls = []

    def handler(request):
        calls.append(request)
        return (
            httpx.Response(500) if len(calls) == 1 else httpx.Response(200, json=openalex_fixture)
        )

    monkeypatch.setattr("app.services.openalex.asyncio.sleep", AsyncMock())

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            settings = Settings(_env_file=None, openalex_api_key="test-only-key")
            result = await OpenAlexService(client, settings).search("test", 1, 10)
            assert result.papers[0].id == "W123"

    asyncio.run(run())
    assert len(calls) == 2
    assert calls[0].headers["Authorization"] == "Bearer test-only-key"
    assert "api_key" not in calls[0].url.params


@pytest.mark.parametrize("status,payload", [(401, {}), (200, {"unexpected": []})])
def test_provider_errors_are_clear(status, payload):
    async def run():
        transport = httpx.MockTransport(lambda request: httpx.Response(status, json=payload))
        async with httpx.AsyncClient(transport=transport) as client:
            with pytest.raises(ServiceError) as error:
                await OpenAlexService(client, Settings(_env_file=None)).search("test", 1, 10)
            assert error.value.status_code == 502

    asyncio.run(run())
