"""Offline tests for shared lookups, bounded storage and cancellation semantics."""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.core.errors import ServiceError
from app.services.resource_cache import ResourceCache


def test_coalesces_concurrent_lookups_and_copies_values():
    async def run():
        cache = ResourceCache(2, 60)
        load = AsyncMock(return_value={"passages": ["synthetic"]})
        values = await asyncio.gather(*(cache.get("a", load) for _ in range(20)))
        load.assert_awaited_once()
        values[0][0]["passages"].clear()
        cached, hit = await cache.get("a", load)
        assert hit and cached["passages"] == ["synthetic"]
        assert cache.coalesced == 19

    asyncio.run(run())


def test_ttl_eviction_and_failures_are_not_cached():
    async def run():
        cache = ResourceCache(1, 60)
        load = AsyncMock(return_value="value")
        await cache.get("a", load)
        await cache.get("b", load)
        assert list(cache._values) == ["b"]
        cache._values["b"] = (0, "expired")
        await cache.get("b", load)
        assert load.await_count == 3
        failure = AsyncMock(side_effect=ValueError("synthetic failure"))
        for _ in range(2):
            with pytest.raises(ValueError):
                await cache.get("failure", failure)
        assert failure.await_count == 2 and not cache._pending

    asyncio.run(run())


def test_cancelling_one_waiter_preserves_the_other_request():
    async def run():
        cache = ResourceCache(2, 60)
        started, release = asyncio.Event(), asyncio.Event()
        calls = 0

        async def load():
            nonlocal calls
            calls += 1
            started.set()
            await release.wait()
            return "completed"

        first = asyncio.create_task(cache.get("a", load))
        await started.wait()
        second = asyncio.create_task(cache.get("a", load))
        await asyncio.sleep(0)
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert (await second)[0] == "completed" and calls == 1
        assert not cache._pending

    asyncio.run(run())


def test_last_cancelled_waiter_stops_loader_and_pending_count_is_bounded():
    async def run():
        cache = ResourceCache(2, 60, max_pending=1)
        started, cancelled = asyncio.Event(), asyncio.Event()

        async def load():
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

        task = asyncio.create_task(cache.get("a", load))
        await started.wait()
        with pytest.raises(ServiceError) as exc:
            await cache.get("b", load)
        assert exc.value.code == "citation_context_busy"
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.wait_for(cancelled.wait(), 1)
        assert not cache._pending and not cache._values

    asyncio.run(run())
