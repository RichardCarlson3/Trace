"""Opt-in INFO timings: opaque correlation IDs, fixed stages, no request content."""

import asyncio
import inspect
import logging
import time
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from uuid import uuid4

logger = logging.getLogger(__name__)
_trace: ContextVar[str | None] = ContextVar("citation_timing_trace", default=None)


def record_timing(stage, started, **metrics):
    logger.info(
        "citation_timing trace=%s stage=%s elapsed_ms=%.3f metrics=%s",
        _trace.get(),
        stage,
        (time.perf_counter() - started) * 1000,
        metrics,
    )


@contextmanager
def timing(stage, **metrics):
    token = _trace.set(uuid4().hex) if _trace.get() is None else None
    started = time.perf_counter()
    metrics["outcome"] = "success"
    try:
        yield
    except BaseException as exc:
        metrics["outcome"] = "cancelled" if isinstance(exc, asyncio.CancelledError) else "error"
        raise
    finally:
        record_timing(stage, started, **metrics)
        if token is not None:
            _trace.reset(token)


def timed(stage):
    def decorate(function):
        if inspect.iscoroutinefunction(function):

            @wraps(function)
            async def asynchronous(*args, **kwargs):
                with timing(stage):
                    return await function(*args, **kwargs)

            return asynchronous

        @wraps(function)
        def synchronous(*args, **kwargs):
            with timing(stage):
                return function(*args, **kwargs)

        return synchronous

    return decorate
