"""Offline synthetic fixtures verify pagination bounds and provider request budgets."""

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.services.openalex import OpenAlexService, retry_after_seconds


@pytest.mark.parametrize("status", [429, 503])
@pytest.mark.parametrize(
    "header,delay", [(None, 0.25), ("invalid", 0.25), ("1", 1.0), ("1.5", 1.5)]
)
def test_retry_after_is_honored_before_recovery(monkeypatch, status, header, delay):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", sleep)
    calls = []

    def handler(request):
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(status, headers={} if header is None else {"Retry-After": header})
        return httpx.Response(200, json={"id": "W123", "title": "Synthetic fixture"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result = await OpenAlexService(client, Settings(_env_file=None)).details("W123")
            assert result.id == "W123"

    asyncio.run(run())
    assert len(calls) == 2
    sleep.assert_awaited_once_with(delay)


@pytest.mark.parametrize("status", [429, 503])
def test_long_retry_after_fails_fast_without_early_retry(monkeypatch, status):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", sleep)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status, headers={"Retry-After": "3600"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ServiceError) as error:
                await OpenAlexService(client, Settings(_env_file=None)).details("W123")
            assert error.value.status_code == 503
            assert error.value.code == "openalex_unavailable"

    asyncio.run(run())
    assert len(calls) == 1
    sleep.assert_not_awaited()


@pytest.mark.parametrize(
    "header,expected",
    [
        (None, None),
        ("", None),
        ("nonsense", None),
        ("NaN", None),
        ("inf", None),
        ("-5", 0.0),
        ("0", 0.0),
        ("2", 2.0),
        ("Sat, 14 Nov 2026 12:00:01 GMT", 1.0),
        ("Sat, 14 Nov 2026 11:59:00 GMT", 0.0),
    ],
)
def test_retry_after_parser_handles_dates_and_bad_headers(monkeypatch, header, expected):
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 14, 12, tzinfo=UTC)

    monkeypatch.setattr("app.services.openalex.datetime", FrozenDateTime)
    assert retry_after_seconds(header) == expected


def test_final_failed_attempt_does_not_sleep(monkeypatch):
    sleep = AsyncMock()
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", sleep)
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(429, headers={"Retry-After": "1"})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ServiceError):
                await OpenAlexService(client, Settings(_env_file=None)).details("W123")

    asyncio.run(run())
    assert len(calls) == 3
    assert [call.args for call in sleep.await_args_list] == [(1.0,), (1.0,)]


def test_absolute_attempt_deadline_cancels_stalled_transport(monkeypatch):
    monkeypatch.setattr("app.services.openalex.REQUEST_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", AsyncMock())
    calls, cancellations = [], []

    async def handler(request):
        calls.append(request)
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancellations.append(request)
            raise

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            with pytest.raises(ServiceError) as error:
                await OpenAlexService(client, Settings(_env_file=None)).details("W123")
            assert error.value.status_code == 502
            assert error.value.code == "openalex_unavailable"

    asyncio.run(run())
    assert len(calls) == len(cancellations) == 3


def test_basic_search_boundary_and_provider_page_size(client, monkeypatch):
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [], "meta": {"count": 10_001}})

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client.app.state, "http", upstream)
    try:
        accepted = client.get("/api/v1/papers/search?q=test&page=400&per_page=25")
        assert accepted.status_code == 200
        assert calls[0].url.params["page"] == "400"
        assert calls[0].url.params["per-page"] == "25"
        rejected = client.get("/api/v1/papers/search?q=test&page=401&per_page=25")
        assert rejected.status_code == 422
        assert rejected.json()["error"]["code"] == "validation_error"
        assert len(calls) == 1
    finally:
        asyncio.run(upstream.aclose())


@pytest.mark.parametrize("operation", ["search", "references"])
def test_oversized_provider_pages_are_rejected(operation):
    def handler(request):
        if request.url.path == "/works/W123":
            return httpx.Response(200, json={"id": "W123", "referenced_works": ["W100"]})
        return httpx.Response(
            200,
            json={
                "results": [{"id": "W100"}, {"id": "W200"}],
                "meta": {"count": 2},
            },
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexService(client, Settings(_env_file=None))
            with pytest.raises(ServiceError) as error:
                if operation == "search":
                    await service.search("test", 1, 1)
                else:
                    await service.references("W123", limit=1)
            assert error.value.code == "openalex_invalid_response"

    asyncio.run(run())


def test_neighbor_directions_run_concurrently_with_one_seed_request():
    async def run():
        both_started = asyncio.Event()
        calls = []
        queries = []

        async def handler(request):
            calls.append(request)
            if request.url.path == "/works/W123":
                return httpx.Response(200, json={"id": "W123", "referenced_works": ["W100"]})
            queries.append(request)
            if len(queries) == 2:
                both_started.set()
            # Neither direction can finish until both are in flight.
            await both_started.wait()
            if request.url.params["filter"].startswith("ids.openalex:"):
                return httpx.Response(200, json={"results": [{"id": "W100"}]})
            return httpx.Response(
                200,
                json={
                    "results": [{"id": "W200"}],
                    "meta": {"next_cursor": None},
                },
            )

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexService(client, Settings(_env_file=None))
            result = await asyncio.wait_for(service.neighbors("W123", limit=2), timeout=2)
            assert len(calls) == 3
            assert len(result.citations) == 2
            assert result.has_more is False

    asyncio.run(run())


@pytest.mark.parametrize("cancel_caller", [False, True])
def test_failure_or_caller_cancellation_stops_sibling_requests(cancel_caller):
    async def run():
        both_started = asyncio.Event()
        started, cancelled = [], []

        async def handler(request):
            if request.url.path == "/works/W123":
                return httpx.Response(200, json={"id": "W123", "referenced_works": ["W100"]})
            started.append(request)
            if len(started) == 2:
                both_started.set()
            try:
                await both_started.wait()
                if not cancel_caller and request.url.params["filter"].startswith("ids.openalex:"):
                    return httpx.Response(403)
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                cancelled.append(request)
                raise

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexService(client, Settings(_env_file=None))
            task = asyncio.create_task(service.neighbors("W123", limit=2))
            await asyncio.wait_for(both_started.wait(), timeout=2)
            if cancel_caller:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
                assert len(cancelled) == 2
            else:
                with pytest.raises(ServiceError) as error:
                    await task
                assert error.value.code == "openalex_error"
                assert len(cancelled) == 1
            assert task.done()

    asyncio.run(run())
