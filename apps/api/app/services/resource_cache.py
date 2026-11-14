"""Bounded event-loop-local TTL cache with cancellation-aware request coalescing."""

import asyncio
import copy
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from dataclasses import dataclass

from app.core.errors import ServiceError


@dataclass
class _Flight[T]:
    task: asyncio.Task[T]
    waiters: int = 0


class ResourceCache[T]:
    """One instance belongs to one service/event loop; errors are never cached."""

    def __init__(self, entries: int, seconds: float, max_pending: int = 128):
        self.entries = entries
        self.seconds = seconds
        self.max_pending = max_pending
        self._values: OrderedDict[Hashable, tuple[float, T]] = OrderedDict()
        self._pending: dict[Hashable, _Flight[T]] = {}
        self.hits = 0
        self.misses = 0
        self.coalesced = 0

    def contains(self, key: Hashable) -> bool:
        """Whether an unexpired value is stored; never loads or changes recency."""
        cached = self._values.get(key)
        return cached is not None and cached[0] > time.monotonic()

    async def get(
        self,
        key: Hashable,
        load: Callable[[], Awaitable[T]],
        lifetime: Callable[[T], float] | None = None,
    ) -> tuple[T, bool]:
        cached = self._values.get(key)
        if cached is not None:
            expires, value = cached
            if expires > time.monotonic():
                self._values.move_to_end(key)
                self.hits += 1
                return copy.deepcopy(value), True
            del self._values[key]
        flight = self._pending.get(key)
        reused = flight is not None
        if flight is None:
            if len(self._pending) >= self.max_pending:
                raise ServiceError(503, "citation_context_busy", "Citation retrieval is busy")

            async def populate():
                value = await load()
                seconds = lifetime(value) if lifetime else self.seconds
                if seconds > 0:
                    self._values[key] = (time.monotonic() + seconds, copy.deepcopy(value))
                    self._values.move_to_end(key)
                    while len(self._values) > self.entries:
                        self._values.popitem(last=False)
                return value

            flight = _Flight(asyncio.create_task(populate()))
            self._pending[key] = flight
            self.misses += 1
        else:
            self.coalesced += 1
        flight.waiters += 1
        try:
            # One cancelled caller must not cancel the other callers' shared I/O.
            value = await asyncio.shield(flight.task)
            return copy.deepcopy(value), reused
        finally:
            flight.waiters -= 1
            if flight.waiters == 0:
                if self._pending.get(key) is flight:
                    del self._pending[key]
                # No callers left: stop queued requests and any retry loop.
                if not flight.task.done():
                    flight.task.cancel()
                else:
                    # Retrieve exceptions even if cancellation raced with completion.
                    if not flight.task.cancelled():
                        flight.task.exception()
