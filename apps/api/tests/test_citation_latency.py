"""Offline latency experiments: virtual waits, synthetic S2, recorded BART XML."""

import asyncio
import json
import logging
import re
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.citation_contexts import CitationContexts, CitationPair
from app.services import citation_contexts as primary_module
from app.services import citation_timing, openalex_tei
from app.services.citation_contexts import CitationContextService, classify_contexts
from app.services.citation_identifiers import normalize_doi
from app.services.inference import InferenceService

FIXTURES = Path(__file__).parent / "fixtures/tei"
PAIR = CitationPair(citing_paper_id="W2982399380", cited_paper_id="W1614298861")
REAL_SLEEP = asyncio.sleep


class Clock:
    """Advance to the next pending timer only after draining runnable callbacks."""

    def __init__(self):
        self.now = 100.0
        self.timers = []

    async def sleep(self, seconds):
        if seconds <= 0:
            return await REAL_SLEEP(0)
        future = asyncio.get_running_loop().create_future()
        self.timers.append((self.now + seconds, future))
        await future

    async def run(self, coroutine):
        task = asyncio.create_task(coroutine)
        for _ in range(500):
            for _ in range(40):
                await REAL_SLEEP(0)
            if task.done():
                return await task
            timers = [(at, future) for at, future in self.timers if not future.done()]
            assert timers, "Experiment stalled without a timer"
            self.now = min(at for at, _ in timers)
            for at, future in timers:
                if at <= self.now:
                    future.set_result(None)
            self.timers = [(at, future) for at, future in timers if not future.done()]
        pytest.fail("Experiment exceeded bounded virtual timer steps")


def experiment(monkeypatch, scenario):
    clock = Clock()
    monkeypatch.setattr(primary_module, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(openalex_tei, "time", SimpleNamespace(monotonic=lambda: clock.now))
    monkeypatch.setattr(primary_module.asyncio, "sleep", clock.sleep)
    monkeypatch.setattr(primary_module.random, "uniform", lambda low, high: 0)
    works = json.loads((FIXTURES / "works.json").read_text(encoding="utf-8"))
    ids = {wid: f"{index + 1:040x}" for index, wid in enumerate(works)}
    calls = []
    semantic_count = 0

    async def parse(function, *args):
        await clock.sleep(0.05)
        return function(*args)

    monkeypatch.setattr(openalex_tei, "run_in_threadpool", parse)

    async def handler(request):
        nonlocal semantic_count
        calls.append((clock.now, request.url.host, request.url.path))
        if request.url.host == "api.semanticscholar.org":
            assert request.headers["x-api-key"] == "synthetic-s2-private"
            semantic_count += 1
            await clock.sleep(9 if scenario == "slow_throttled" else 0.1)
            if (
                scenario in {"throttled", "both_unavailable"}
                or (scenario in {"recovers", "resumed", "fallback_miss"} and semantic_count == 1)
                or (scenario == "slow_throttled" and semantic_count != 3)
            ):
                return httpx.Response(
                    429, headers={"Retry-After": "1" if scenario == "resumed" else "4"}
                )
            if request.url.path.endswith("/references"):
                return httpx.Response(
                    200,
                    json={
                        "offset": 0,
                        "data": [
                            {
                                "citedPaper": {
                                    "paperId": ids[wid],
                                    "externalIds": {"DOI": normalize_doi(work["doi"])},
                                },
                                "contexts": ["Synthetic latency-test citation [1]."],
                            }
                            for wid, work in works.items()
                            if wid != PAIR.citing_paper_id and work.get("doi")
                        ],
                    },
                )
            kind, value = request.url.path.split("/paper/", 1)[1].split(":", 1)
            for wid, work in works.items():
                if kind == "DOI" and work.get("doi") and normalize_doi(work["doi"]) == value:
                    return httpx.Response(
                        200, json={"paperId": ids[wid], "externalIds": {"DOI": value}}
                    )
            return httpx.Response(404)
        assert request.headers["Authorization"] == "Bearer synthetic-oa-private"
        if request.url.host == "content.openalex.org":
            await clock.sleep(
                10
                if scenario == "recovers"
                else 4
                if scenario == "resumed"
                else 8
                if scenario == "slow_throttled"
                else 0.4
            )
            return httpx.Response(200, content=(FIXTURES / "bart.xml").read_bytes())
        await clock.sleep(2 if scenario == "slow_throttled" else 0.2)
        wid = request.url.path.rsplit("/", 1)[-1]
        work = works[wid]
        if scenario in {"both_unavailable", "fallback_miss"}:
            work = {**work, "has_content": {"grobid_xml": False}}
        return httpx.Response(200, json=work)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            settings = Settings(
                _env_file=None,
                semantic_scholar_enabled=scenario != "tei_only",
                semantic_scholar_api_key="synthetic-s2-private",
                openalex_api_key="synthetic-oa-private",
            )
            service = CitationContextService(client, settings)
            service._examples = {}
            if scenario in {"cooldown", "expired_cooldown", "normal_pacing"}:
                service._next_semantic_request = clock.now + (
                    4 if scenario == "cooldown" else 1.5 if scenario == "normal_pacing" else -1
                )
                service._semantic_cooldown_until = (
                    service._next_semantic_request if scenario != "normal_pacing" else 0
                )
                if hasattr(service, "_semantic_cooldown"):
                    service._semantic_cooldown.set()
            inference = InferenceService(settings.model_artifact_dir)

            async def classify(pair=PAIR):
                result = await service.retrieve_for_classification(pair)
                await clock.sleep(0.02)  # Controlled inference wait, not a real CPU benchmark.
                return classify_contexts(result, inference)

            if scenario == "cached":
                await classify()
                calls.clear()
            started = clock.now
            if scenario == "shared":
                other = next(
                    wid
                    for wid, work in works.items()
                    if wid not in PAIR.model_dump().values() and work.get("doi")
                )
                pairs = [
                    PAIR,
                    CitationPair(citing_paper_id=PAIR.citing_paper_id, cited_paper_id=other),
                ]
                results = await asyncio.gather(*(classify(pair) for pair in pairs * 10))
                assert all(result.available for result in results)
                assert sum(path.endswith("/references") for _, _, path in calls) == 1
                assert service._pairs.coalesced >= 18
                result = results[0]
            else:
                result = await classify()
            return result, round(clock.now - started, 6), calls

    return asyncio.run(clock.run(run()))


@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "throttled",
        "slow_throttled",
        "resumed",
        "cooldown",
        "expired_cooldown",
        "normal_pacing",
        "tei_only",
        "both_unavailable",
        "cached",
        "recovers",
        "fallback_miss",
        "shared",
    ],
)
def test_measurements(monkeypatch, scenario):
    result, seconds, calls = experiment(monkeypatch, scenario)
    print(
        json.dumps(
            {
                "scenario": scenario,
                "seconds": seconds,
                "source": result.source,
                "available": result.available,
                "requests": len(calls),
            }
        )
    )
    assert result.available == (scenario != "both_unavailable")
    if result.source == "openalex_tei":
        assert result.contexts[0].classification.intent == "background"
        assert result.contexts[0].classification.confidence == pytest.approx(0.8843842684202584)
    if scenario == "cached":
        assert calls == [] and seconds == pytest.approx(0.02)
    expected = {
        "success": (3.32, 5),
        "throttled": (1.17, 5),
        "slow_throttled": (24.02, 6),
        "resumed": (7.17, 9),
        "cooldown": (0.87, 4),
        "expired_cooldown": (3.32, 5),
        "normal_pacing": (4.62, 5),
        "tei_only": (0.87, 3),
        "both_unavailable": (8.52, 6),
        "cached": (0.02, 0),
        "recovers": (8.92, 9),
        "fallback_miss": (8.92, 8),
        "shared": (4.82, 7),
    }
    assert seconds == pytest.approx(expected[scenario][0])
    assert len(calls) == expected[scenario][1]
    if scenario in {
        "resumed",
        "success",
        "expired_cooldown",
        "normal_pacing",
        "recovers",
        "fallback_miss",
        "shared",
    }:
        assert result.source == "semantic_scholar"
    if scenario == "both_unavailable":
        assert result.status == "provider_unavailable"
        assert result.reason == "semantic_scholar_rate_limited"
        assert result.fallback_reason == "openalex_tei_content_unavailable"


def recorded_result():
    path = Path(__file__).resolve().parents[3] / "docs/reports/openalex_fallback_live.json"
    payload = json.loads(path.read_text(encoding="utf-8"))["response"]
    payload.pop("available")  # Computed response field, not a validation input.
    return CitationContexts.model_validate(payload)


@pytest.mark.parametrize("phase", ["primary", "fallback"])
@pytest.mark.parametrize("cancel_all", [False, True])
def test_cancelled_api_waiters_preserve_shared_work_or_stop_last_loader(client, phase, cancel_all):
    async def run():
        entered, release, cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()

        async def load(*args):
            entered.set()
            try:
                await release.wait()
                result = recorded_result()
                return (result, None) if phase == "fallback" else result
            except asyncio.CancelledError:
                cancelled.set()
                raise

        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected network"))
        ) as upstream:
            settings = Settings(
                _env_file=None, semantic_scholar_enabled=True, openalex_api_key="synthetic-private"
            )
            service = CitationContextService(upstream, settings)
            service._examples = {}
            if phase == "primary":
                service._retrieve_live = load
                service.tei.retrieve = AsyncMock(side_effect=AssertionError("Unnecessary fallback"))
            else:
                service._semantic_cooldown_until = primary_module.time.monotonic() + 60
                service._semantic_cooldown.set()

                # An async primary loader must stay pending until cancellation.
                async def pending(pair):
                    await asyncio.Event().wait()

                service._retrieve_live = pending
                service.tei.retrieve = load
            client.app.state.citation_contexts = service
            client.app.state.inference = InferenceService(settings.model_artifact_dir)
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=client.app), base_url="http://offline.test"
            ) as frontend:
                first = asyncio.create_task(
                    frontend.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump())
                )
                second = asyncio.create_task(
                    frontend.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump())
                )
                await asyncio.wait_for(entered.wait(), 1)
                for _ in range(10):
                    await REAL_SLEEP(0)
                first.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await first
                assert not cancelled.is_set()
                if cancel_all:
                    second.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await second
                    await asyncio.wait_for(cancelled.wait(), 1)
                else:
                    release.set()
                    response = await asyncio.wait_for(second, 3)
                    assert response.status_code == 200
                    assert response.json()["contexts"][0]["classification"][
                        "confidence"
                    ] == pytest.approx(0.8843842684202584)
                    assert not cancelled.is_set()
                assert service._pairs.coalesced == 1
                assert not service._pairs._pending and not service._tei_pairs._pending
                assert not service._semantic_cooldown._waiters

    asyncio.run(run())


def test_negative_pair_cache_keeps_original_expiry(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(primary_module, "time", SimpleNamespace(monotonic=lambda: now[0]))

    async def run():
        async with httpx.AsyncClient() as upstream:
            service = CitationContextService(
                upstream, Settings(_env_file=None, openalex_api_key="synthetic-private")
            )
            service.tei.retrieve = AsyncMock(
                return_value=(None, "openalex_tei_content_unavailable")
            )
            first = await service.retrieve_for_classification(PAIR)
            key = (PAIR.citing_paper_id, PAIR.cited_paper_id)
            expiry = service._cache[key][0]
            for _ in range(3):
                now[0] += 20
                cached = await service.retrieve_for_classification(PAIR)
                assert cached.status == first.status and cached.reason == first.reason
                assert service._cache[key][0] == expiry
            assert service.tei.retrieve.await_count == 1

    asyncio.run(run())


def test_early_capacity_rejection_retains_late_fallback_opportunity():
    async def run():
        release = asyncio.Event()
        async with httpx.AsyncClient() as upstream:
            service = CitationContextService(
                upstream,
                Settings(
                    _env_file=None,
                    semantic_scholar_enabled=True,
                    openalex_api_key="synthetic-private",
                ),
            )
            service._semantic_cooldown_until = primary_module.time.monotonic() + 60
            service._semantic_cooldown.set()

            async def primary(pair, mode):
                await release.wait()
                return service._unavailable(
                    pair, "provider_unavailable", "semantic_scholar_rate_limited"
                )

            async def fallback(*args):
                release.set()
                if fallback_mock.await_count == 1:
                    raise ServiceError(503, "citation_context_busy", "Busy")
                return (recorded_result(), None), False

            fallback_mock = AsyncMock(side_effect=fallback)
            service.retrieve = primary
            service._tei_pairs.get = fallback_mock
            result = await service.retrieve_for_classification(PAIR)
            assert result.available and fallback_mock.await_count == 2

    asyncio.run(run())


def test_cached_semantic_success_wins_even_during_cooldown():
    path = Path(__file__).resolve().parents[1] / "app/examples/citation_contexts.json"
    result = CitationContexts.model_validate(
        json.loads(path.read_text(encoding="utf-8"))["examples"][0]
    )
    pair = CitationPair(
        citing_paper_id=result.citing_paper_id, cited_paper_id=result.cited_paper_id
    )

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda r: pytest.fail("Unexpected network"))
        ) as client:
            service = CitationContextService(
                client,
                Settings(
                    _env_file=None,
                    semantic_scholar_enabled=True,
                    openalex_api_key="synthetic-private",
                ),
            )
            service._remember((pair.citing_paper_id, pair.cited_paper_id), result)
            service._semantic_cooldown_until = primary_module.time.monotonic() + 60
            service._semantic_cooldown.set()
            service.tei.retrieve = AsyncMock(side_effect=AssertionError("Unnecessary fallback"))
            cached = await service.retrieve_for_classification(pair)
            assert cached.source == "semantic_scholar" and cached.origin == "memory_cache"
            assert cached.contexts == result.contexts
            service.tei.retrieve.assert_not_called()

    asyncio.run(run())


def test_timing_trace_is_correlated_and_contains_no_credentials_or_contexts(client, caplog):
    caplog.set_level(logging.INFO, logger=citation_timing.__name__)
    works = json.loads((FIXTURES / "works.json").read_text(encoding="utf-8"))

    def handler(request):
        if request.url.host == "content.openalex.org":
            return httpx.Response(200, content=(FIXTURES / "bart.xml").read_bytes())
        return httpx.Response(200, json=works[request.url.path.rsplit("/", 1)[-1]])

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        _env_file=None,
        semantic_scholar_api_key="private-s2-timing",
        openalex_api_key="private-oa-timing",
    )
    client.app.state.citation_contexts = CitationContextService(upstream, settings)
    client.app.state.inference = InferenceService(settings.model_artifact_dir)
    response = client.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump())
    assert response.status_code == 200 and response.json()["available"]
    records = [record for record in caplog.records if record.name == citation_timing.__name__]
    assert len({record.args[0] for record in records}) == 1
    assert all(re.fullmatch(r"[0-9a-f]{32}", record.args[0]) for record in records)
    stages = {record.args[1] for record in records}
    assert {
        "classification_total",
        "classification_retrieval",
        "tei_metadata",
        "tei_xml_retrieval",
        "tei_parse",
        "model_inference",
    } <= stages
    text = "\n".join(record.getMessage() for record in records)
    for sensitive in [
        "private-s2-timing",
        "private-oa-timing",
        PAIR.citing_paper_id,
        "https://",
        response.json()["contexts"][0]["context_text"],
    ]:
        assert sensitive not in text
    asyncio.run(upstream.aclose())
