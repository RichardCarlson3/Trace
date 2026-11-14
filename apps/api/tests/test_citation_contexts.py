"""Synthetic provider fixtures exercise context retrieval without external requests."""

import asyncio
import json
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.citation_contexts import CitationPair
from app.schemas.contracts import Classification
from app.services import citation_contexts as module
from app.services.citation_contexts import CitationContextService, classify_contexts, normalize_doi

CITING = "a" * 40
CITED = "b" * 40
PAIR = CitationPair(citing_paper_id="W100", cited_paper_id="W200")


@pytest.fixture
def provider(monkeypatch):
    # All titles, passages and identifiers in this fixture are synthetic test data.
    state = SimpleNamespace(
        calls=[],
        override=None,
        works={
            "W100": {
                "id": "https://openalex.org/W100",
                "title": "Citing fixture",
                "doi": "https://doi.org/10.1000/CITING",
                "ids": {"doi": "10.1000/citing"},
            },
            "W200": {
                "id": "https://openalex.org/W200",
                "title": "Cited fixture",
                "doi": "10.1000/cited",
                "ids": {},
            },
        },
        papers={
            "10.1000/citing": {"paperId": CITING, "externalIds": {"DOI": "10.1000/citing"}},
            "10.1000/cited": {
                "paperId": CITED,
                "externalIds": {"DOI": "https://doi.org/10.1000/CITED"},
            },
        },
        pages={
            0: {
                "offset": 0,
                "data": [
                    {
                        "citedPaper": {
                            "paperId": "c" * 40,
                            "title": "Cited fixture",
                            "externalIds": {"DOI": "10.1000/distractor"},
                        },
                        "contexts": ["Unrelated synthetic context."],
                    },
                    {
                        "citedPaper": {"paperId": CITED, "externalIds": {"DOI": "10.1000/cited"}},
                        "contexts": [
                            " Original synthetic context [1].\n",
                            "Second synthetic passage [1].",
                        ],
                    },
                ],
            }
        },
    )

    def handler(request):
        if request.url.path.endswith("/paper/batch"):
            return batch(request)
        state.calls.append(request)
        if state.override:
            response = state.override(request)
            if response is not None:
                return response
        if request.url.host == "api.openalex.org":
            work = state.works.get(request.url.path.rsplit("/", 1)[-1])
            return httpx.Response(200, json=work) if work else httpx.Response(404)
        if request.url.path.endswith("/references"):
            assert f"/paper/{CITING}/references" in request.url.path
            return httpx.Response(200, json=state.pages[int(request.url.params["offset"])])
        doi = request.url.path.split("/paper/DOI:", 1)[-1]
        paper = state.papers.get(doi)
        return httpx.Response(200, json=paper) if paper else httpx.Response(404)

    def batch(request):
        # Answer each id exactly as the single-lookup route (including overrides);
        # the batch is one recorded request, and any non-404 error is its status.
        assert request.method == "POST"
        state.calls.append(request)
        if state.override:
            response = state.override(request)
            if response is not None:
                return response
        recorded = len(state.calls)
        singles = [
            handler(
                httpx.Request(
                    "GET", f"{request.url.scheme}://{request.url.host}/graph/v1/paper/{i}"
                )
            )
            for i in json.loads(request.content)["ids"]
        ]
        del state.calls[recorded:]
        failure = next((r for r in singles if r.status_code not in (200, 404)), None)
        if failure is not None:
            return failure
        return httpx.Response(
            200, json=[r.json() if r.status_code == 200 else None for r in singles]
        )

    state.handler = handler
    monkeypatch.setattr(module, "SEMANTIC_INTERVAL_SECONDS", 0)
    monkeypatch.setattr(module.asyncio, "sleep", AsyncMock())
    return state


def settings(**overrides):
    return Settings(_env_file=None, semantic_scholar_enabled=True, **overrides)


def retrieve(provider, mode="live"):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            service._examples = {}
            return await service.retrieve(PAIR, mode=mode)

    return asyncio.run(run())


@pytest.mark.parametrize(
    "value",
    [
        "10.1000/ABC",
        " DOI:10.1000/ABC ",
        "https://doi.org/10.1000/ABC",
        "http://dx.doi.org/10.1000%2FABC?tracking=1#fragment",
    ],
)
def test_doi_normalization(value):
    assert normalize_doi(value) == "10.1000/abc"


@pytest.mark.parametrize(
    "value",
    [None, 3, "", "not-a-doi", "https://example.test/10.1000/abc", "10.1000/has whitespace"],
)
def test_invalid_dois_are_rejected(value):
    with pytest.raises(ValueError):
        normalize_doi(value)


def test_verified_mapping_direction_multiple_passages_and_attribution(provider):
    result = retrieve(provider)
    assert result.status == "available" and result.available
    assert result.citing_paper_id == "W100" and result.cited_paper_id == "W200"
    assert result.citing_mapping.semantic_scholar_paper_id == CITING
    assert result.cited_mapping.semantic_scholar_paper_id == CITED
    assert result.citing_mapping.verified and result.cited_mapping.verified
    assert result.citing_mapping.doi == "10.1000/citing"
    assert [context.context_text for context in result.contexts] == [
        " Original synthetic context [1].\n",
        "Second synthetic passage [1].",
    ]
    assert result.observed_context_count == 2
    assert all(
        context.source_url.endswith(CITING) and context.source_url_scope == "paper"
        for context in result.contexts
    )
    assert all(
        context.source == "semantic_scholar" and context.classification is None
        for context in result.contexts
    )
    assert result.origin == "live" and result.retrieved_at is not None
    assert "/references?" in result.evidence_urls[0]


@pytest.mark.parametrize("contexts", [None, [], [" ", "\n"]])
def test_matching_reference_without_context_keeps_relationship(provider, contexts):
    provider.pages[0]["data"][1]["contexts"] = contexts
    result = retrieve(provider)
    assert result.status == "no_context"
    assert result.relationship_found is True and result.reference_scan_complete
    assert not result.available and result.contexts == []


def test_absent_context_field_is_unavailable_evidence(provider):
    del provider.pages[0]["data"][1]["contexts"]
    assert retrieve(provider).status == "no_context"


def test_same_title_does_not_match_the_wrong_paper(provider):
    provider.pages[0]["data"] = provider.pages[0]["data"][:1]
    result = retrieve(provider)
    assert result.status == "relationship_not_found"
    assert result.relationship_found is False and result.reference_scan_complete


@pytest.mark.parametrize(
    "problem,reason",
    [
        ("missing_doi", "missing_doi"),
        ("conflicting_doi", "ambiguous_openalex_doi"),
        ("missing_work", "openalex_work_not_found"),
        ("missing_semantic", "semantic_scholar_work_not_found"),
        ("mismatch", "semantic_scholar_doi_mismatch"),
        ("unverified", "unverified_semantic_scholar_doi"),
    ],
)
def test_unresolved_identifiers_are_explicit(provider, problem, reason):
    if problem == "missing_doi":
        provider.works["W100"].update(doi=None, ids={})
    elif problem == "conflicting_doi":
        provider.works["W100"]["ids"]["doi"] = "10.1000/conflict"
    elif problem == "missing_work":
        del provider.works["W100"]
    elif problem == "missing_semantic":
        del provider.papers["10.1000/citing"]
    elif problem == "mismatch":
        provider.papers["10.1000/citing"]["externalIds"]["DOI"] = "10.1000/different"
    else:
        provider.papers["10.1000/citing"]["externalIds"] = {}
    result = retrieve(provider)
    assert result.status == "unresolved_identifiers" and not result.available
    assert not result.citing_mapping.verified and result.citing_mapping.reason == reason
    assert result.relationship_found is None
    assert not any(request.url.path.endswith("/references") for request in provider.calls)


@pytest.mark.parametrize("change", ["wrong_doi", "different_semantic_id", "same_paper_pair"])
def test_ambiguous_mappings_do_not_produce_evidence(provider, change):
    target = provider.pages[0]["data"][1]["citedPaper"]
    if change == "wrong_doi":
        target["externalIds"]["DOI"] = "10.1000/different"
    elif change == "different_semantic_id":
        target["paperId"] = "d" * 40
    else:
        provider.papers["10.1000/cited"]["paperId"] = CITING
    result = retrieve(provider)
    assert result.status == "unresolved_identifiers" and not result.available
    assert result.reason in ("ambiguous_reference_identity", "ambiguous_paper_pair")


def test_reference_can_match_by_verified_doi_when_semantic_id_is_missing(provider):
    provider.pages[0]["data"][1]["citedPaper"]["paperId"] = None
    assert retrieve(provider).available


def test_paginated_reference_list_and_duplicate_passages(provider):
    matching = provider.pages[0]["data"].pop()
    matching["contexts"].append(matching["contexts"][0])
    provider.pages[0]["next"] = 100
    provider.pages[100] = {"offset": 100, "data": [matching]}
    result = retrieve(provider)
    assert len(result.contexts) == 2 and result.reference_scan_complete
    assert [
        request.url.params["offset"]
        for request in provider.calls
        if request.url.path.endswith("/references")
    ] == ["0", "100"]


def test_scan_limit_is_not_reported_as_no_relationship(provider, monkeypatch):
    provider.pages[0] = {"offset": 0, "next": 100, "data": []}
    provider.pages[100] = {"offset": 100, "next": 200, "data": []}
    monkeypatch.setattr(module, "MAX_REFERENCE_PAGES", 2)
    result = retrieve(provider)
    assert result.status == "incomplete" and result.relationship_found is None
    assert not result.reference_scan_complete and not result.available


@pytest.mark.parametrize(
    "response_status,expected_code",
    [(429, "semantic_scholar_rate_limited"), (503, "semantic_scholar_unavailable")],
)
def test_bounded_semantic_scholar_retries(provider, response_status, expected_code):
    provider.override = lambda request: (
        httpx.Response(response_status) if request.url.host == "api.semanticscholar.org" else None
    )
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.status_code == 503 and error.value.code == expected_code
    assert (
        len(
            [request for request in provider.calls if request.url.host == "api.semanticscholar.org"]
        )
        == 3
    )


def test_long_retry_after_is_respected_without_early_retry(provider):
    provider.override = lambda request: (
        httpx.Response(429, headers={"Retry-After": "60"})
        if request.url.host == "api.semanticscholar.org"
        else None
    )
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.status_code == 503
    assert (
        len(
            [request for request in provider.calls if request.url.host == "api.semanticscholar.org"]
        )
        == 1
    )


def test_retry_after_http_date():
    from app.services.citation_contexts import _retry_delay

    value = format_datetime(datetime.now(UTC) + timedelta(seconds=4))
    assert 0 < _retry_delay(httpx.Response(429, headers={"Retry-After": value}), 0) <= 4


def test_timeouts_use_bounded_retries(provider):
    def timeout(request):
        if request.url.host == "api.semanticscholar.org":
            raise httpx.ReadTimeout("private diagnostic", request=request)

    provider.override = timeout
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.status_code == 502
    assert (
        len(
            [request for request in provider.calls if request.url.host == "api.semanticscholar.org"]
        )
        == 3
    )


@pytest.mark.parametrize(
    "problem", ["invalid_json", "not_object", "invalid_contexts", "repeated_page"]
)
def test_invalid_provider_data_is_an_error(provider, problem):
    if problem == "invalid_json":
        provider.override = lambda request: (
            httpx.Response(200, text="bad JSON")
            if request.url.host == "api.semanticscholar.org"
            else None
        )
    elif problem == "not_object":
        provider.override = lambda request: (
            httpx.Response(200, json=[]) if request.url.host == "api.semanticscholar.org" else None
        )
    elif problem == "invalid_contexts":
        provider.pages[0]["data"][1]["contexts"] = {"abstract": "Not a citation passage"}
    else:
        provider.pages[0]["next"] = 0
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.status_code == 502


def test_classification_uses_only_retrieved_passages(provider):
    result = retrieve(provider)
    inference = Mock()
    inference.classify.return_value = Classification(
        intent="method", confidence=0.75, model_version="fixture-v1"
    )
    classified = classify_contexts(result, inference)
    assert [call.args[0] for call in inference.classify.call_args_list] == [
        context.context_text for context in result.contexts
    ]
    assert all(context.classification.intent == "method" for context in classified.contexts)
    assert all(context.classification is None for context in result.contexts)
    assert classified.contexts[0].source_url == result.contexts[0].source_url


def test_no_context_never_calls_inference(provider):
    provider.pages[0]["data"][1]["contexts"] = []
    inference = Mock()
    result = classify_contexts(retrieve(provider), inference)
    inference.classify.assert_not_called()
    assert not result.available and result.status == "no_context"


def test_long_context_is_preserved_and_left_unclassified(provider):
    provider.pages[0]["data"][1]["contexts"] = ["x" * 20001]
    inference = Mock()
    result = classify_contexts(retrieve(provider), inference)
    inference.classify.assert_not_called()
    assert result.contexts[0].classification_unavailable_reason == "context_too_long"
    assert len(result.contexts[0].context_text) == 20001


def test_unverified_evidence_is_never_classified(provider):
    result = retrieve(provider)
    result.citing_mapping.verified = False
    inference = Mock()
    with pytest.raises(ServiceError):
        classify_contexts(result, inference)
    inference.classify.assert_not_called()


def test_api_keys_stay_in_provider_headers(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(
                client,
                settings(openalex_api_key="oa-fixture", semantic_scholar_api_key="ss-fixture"),
            )
            return await service.retrieve(PAIR, mode="live")

    assert asyncio.run(run()).available
    for request in provider.calls:
        assert "fixture" not in str(request.url)
        if request.url.host == "api.semanticscholar.org":
            assert request.headers["x-api-key"] == "ss-fixture"
        else:
            assert request.headers["Authorization"] == "Bearer oa-fixture"


def test_memory_cache_avoids_requests_and_isolation_prevents_mutation(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            service._examples = {}
            first = await service.retrieve(PAIR)
            calls = len(provider.calls)
            first.contexts[0].context_text = "Changed by caller"
            cached = await service.retrieve(PAIR)
            assert cached.origin == "memory_cache" and len(provider.calls) == calls
            assert cached.contexts[0].context_text != "Changed by caller"
            service._cache[tuple(PAIR.model_dump().values())] = (0, cached)
            refreshed = await service.retrieve(PAIR)
            assert refreshed.origin == "memory_cache" and len(provider.calls) == calls
            assert refreshed.retrieved_at == cached.retrieved_at

    asyncio.run(run())


def test_disabled_optional_provider_never_uses_network(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, Settings(_env_file=None))
            service._examples = {}
            result = await service.retrieve(PAIR)
            assert result.status == "provider_unavailable" and result.origin == "unavailable"
            assert not result.available and not provider.calls
            with pytest.raises(ServiceError) as error:
                await service.retrieve(PAIR, mode="live")
            assert error.value.code == "semantic_scholar_disabled"

    asyncio.run(run())


def test_auto_mode_gracefully_reports_rate_limit(provider):
    provider.override = lambda request: (
        httpx.Response(429) if request.url.host == "api.semanticscholar.org" else None
    )
    result = retrieve(provider, mode="auto")
    assert result.status == "provider_unavailable" and not result.available
    assert result.reason == "semantic_scholar_rate_limited"


def test_live_mode_excludes_examples_but_reuses_provider_resources(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            service._examples = {}
            await service.retrieve(PAIR, mode="live")
            count = len(provider.calls)
            second = await service.retrieve(PAIR, mode="live")
            assert second.origin == "memory_cache" and len(provider.calls) == count

    asyncio.run(run())


def test_cache_size_is_bounded(provider, monkeypatch):
    monkeypatch.setattr(module, "CONTEXT_CACHE_ENTRIES", 1)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            service._examples = {}
            await service.retrieve(PAIR, mode="live")
            await service.retrieve(
                CitationPair(citing_paper_id="W100", cited_paper_id="W300"), mode="live"
            )
            assert len(service._cache) == 1
            assert ("W100", "W200") not in service._cache

    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 403])
def test_provider_access_errors_are_not_retried(provider, status):
    provider.override = lambda request: (
        httpx.Response(status) if request.url.host == "api.semanticscholar.org" else None
    )
    result = retrieve(provider, mode="auto")
    assert result.status == "provider_unavailable" and not result.available
    assert result.reason == "semantic_scholar_access_denied"
    assert (
        len(
            [request for request in provider.calls if request.url.host == "api.semanticscholar.org"]
        )
        == 1
    )


@pytest.mark.parametrize("value", [{}, "", 0])
def test_malformed_empty_context_types_are_not_missing_evidence(provider, value):
    provider.pages[0]["data"][1]["contexts"] = value
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.status_code == 502


@pytest.fixture
def context_api(client, provider):
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(provider.handler))
    service = CitationContextService(upstream, settings())
    service._examples = {}
    client.app.state.citation_contexts = service
    client.app.state.inference = Mock()
    client.app.state.inference.classify.return_value = Classification(
        intent="method", confidence=0.75, model_version="fixture-v1"
    )
    yield client
    asyncio.run(upstream.aclose())


def test_get_and_classify_api_contract(context_api):
    query = {**PAIR.model_dump(), "mode": "live"}
    response = context_api.get("/api/v1/citation-contexts", params=query)
    assert response.status_code == 200
    assert response.json()["available"] and response.json()["origin"] == "live"
    assert response.json()["contexts"][0]["classification"] is None
    context_api.app.state.inference.classify.assert_not_called()
    response = context_api.post("/api/v1/citation-contexts/classify", json=query)
    assert response.status_code == 200
    assert response.json()["contexts"][0]["classification"]["model_version"] == "fixture-v1"
    paths = context_api.get("/openapi.json").json()["paths"]
    assert "/api/v1/citation-contexts" in paths and "/api/v1/citation-contexts/classify" in paths


@pytest.mark.parametrize(
    "bad",
    [
        {"citing_paper_id": "not-an-id", "cited_paper_id": "W200"},
        {"citing_paper_id": "W100"},
        {"citing_paper_id": 123, "cited_paper_id": "W200"},
        {"citing_paper_id": "W100", "cited_paper_id": "W200", "mode": "unknown"},
    ],
)
def test_invalid_api_input(context_api, provider, bad):
    assert context_api.get("/api/v1/citation-contexts", params=bad).status_code == 422
    assert context_api.post("/api/v1/citation-contexts/classify", json=bad).status_code == 422
    assert not provider.calls


def test_api_rejects_supplied_passages(context_api):
    response = context_api.post(
        "/api/v1/citation-contexts/classify",
        json={**PAIR.model_dump(), "context_text": "Unverified user content"},
    )
    assert response.status_code == 422


def test_examples_work_without_any_provider_calls(client, provider):
    upstream = httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda request: pytest.fail("Network access for verified examples")
        )
    )
    client.app.state.citation_contexts = CitationContextService(upstream, Settings(_env_file=None))
    pairs = [("W2970771982", target) for target in ("W2963341956", "W2626778328", "W1522301498")]
    for citing, cited in pairs:
        response = client.get(
            "/api/v1/citation-contexts",
            params={"citing_paper_id": citing, "cited_paper_id": cited, "mode": "examples"},
        )
        assert response.status_code == 200
        body = response.json()
        assert body["available"] and body["origin"] == "verified_example"
        assert body["retrieved_at"] and body["evidence_urls"]
        assert body["observed_context_count"] >= len(body["contexts"])
    asyncio.run(upstream.aclose())


def test_auto_examples_and_missing_example_are_explicit(client):
    response = client.get(
        "/api/v1/citation-contexts",
        params={"citing_paper_id": "W2970771982", "cited_paper_id": "W2963341956"},
    )
    assert response.status_code == 200 and response.json()["origin"] == "verified_example"
    response = client.get(
        "/api/v1/citation-contexts", params={**PAIR.model_dump(), "mode": "examples"}
    )
    assert response.status_code == 200 and response.json()["status"] == "example_not_found"
    assert not response.json()["available"]


def test_recorded_context_retrieval_works_without_model_artifacts(client):
    pair = {"citing_paper_id": "W2970771982", "cited_paper_id": "W2963341956", "mode": "examples"}
    assert client.get("/api/v1/citation-contexts", params=pair).json()["available"]
    response = client.post("/api/v1/citation-contexts/classify", json=pair)
    assert response.status_code == 503 and response.json()["error"]["code"] == "model_unavailable"
    assert client.get("/api/v1/health").status_code == 200


def test_concurrent_edges_reuse_mapping_and_reference_pages(provider):
    provider.works["W300"] = {"id": "https://openalex.org/W300", "doi": "10.1000/third"}
    provider.papers["10.1000/third"] = {
        "paperId": "d" * 40,
        "externalIds": {"DOI": "10.1000/third"},
    }
    provider.pages[0]["data"].append(
        {
            "citedPaper": provider.papers["10.1000/third"],
            "contexts": ["Synthetic third-paper passage."],
        }
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            pairs = [PAIR, CitationPair(citing_paper_id="W100", cited_paper_id="W300")]
            results = await asyncio.gather(*(service.retrieve(p, mode="live") for p in pairs * 10))
            assert all(r.available for r in results)
            # Three OpenAlex identities, one S2 batch per pair (was three single
            # lookups) and one shared references page.
            assert len(provider.calls) == 6
            assert sum(r.url.path.endswith("/paper/batch") for r in provider.calls) == 2
            assert sum(r.url.path.endswith("/references") for r in provider.calls) == 1
            assert service._mappings.coalesced > 0

    asyncio.run(run())


def test_expired_reference_pages_refresh_without_remapping(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            await service.retrieve(PAIR, mode="live")
            for key, (_, page) in list(service._references._values.items()):
                service._references._values[key] = (0, page)
            previous = len(provider.calls)
            refreshed = await service.retrieve(PAIR, mode="live")
            assert refreshed.origin == "live" and len(provider.calls) == previous + 1
            assert provider.calls[-1].url.path.endswith("/references")

    asyncio.run(run())


def test_scheduler_spaces_all_endpoints_and_publishes_retry_after(monkeypatch):
    # A virtual monotonic clock keeps tests offline/fast while using the 1.5s production interval.
    now = [0.0]
    real_sleep = asyncio.sleep
    calls = []

    async def sleep(seconds):
        now[0] += seconds
        await real_sleep(0)

    async def handler(request):
        calls.append((now[0], request.url.path))
        await real_sleep(0)
        if len(calls) == 1:
            return httpx.Response(429, headers={"Retry-After": "4"})
        return httpx.Response(200, json={"paperId": CITING})

    monkeypatch.setattr(module, "time", SimpleNamespace(monotonic=lambda: now[0]))
    monkeypatch.setattr(module.asyncio, "sleep", sleep)
    assert module.SEMANTIC_INTERVAL_SECONDS >= 1.5

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = CitationContextService(client, settings())
            await asyncio.gather(
                *(
                    service._get("semantic_scholar", path, {})
                    for path in ["paper/a", "paper/b/references", "paper/c/citations"]
                )
            )

    asyncio.run(run())
    assert len(calls) == 4
    assert calls[1][0] - calls[0][0] >= 4
    assert all(b[0] - a[0] >= 1.5 for a, b in zip(calls, calls[1:]))


def test_long_cooldown_applies_across_endpoints(provider):
    provider.override = lambda request: (
        httpx.Response(429, headers={"Retry-After": "60"})
        if request.url.host == "api.semanticscholar.org"
        else None
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            for path in ["paper/a", "paper/b/references"]:
                with pytest.raises(ServiceError) as exc:
                    await service._get("semantic_scholar", path, {})
                assert exc.value.code == "semantic_scholar_rate_limited"
            assert len(provider.calls) == 1

    asyncio.run(run())


def test_cancellation_while_queued_does_not_send_or_retry():
    calls = []

    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        async def handler(request):
            calls.append(request)
            entered.set()
            await release.wait()
            return httpx.Response(200, json={})

        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = CitationContextService(client, settings())
            first = asyncio.create_task(service._get("semantic_scholar", "paper/a", {}))
            await entered.wait()
            queued = asyncio.create_task(service._get("semantic_scholar", "paper/b", {}))
            await asyncio.sleep(0)
            queued.cancel()
            with pytest.raises(asyncio.CancelledError):
                await queued
            release.set()
            await first

    asyncio.run(run())
    assert len(calls) == 1


def test_keys_are_excluded_from_settings_repr_and_upstream_errors(provider, caplog):
    configured = settings(semantic_scholar_api_key="private-s2", openalex_api_key="private-oa")
    assert "private" not in repr(configured)
    provider.override = lambda request: (
        httpx.Response(403, json={"message": "private-s2 private-oa"})
        if request.url.host == "api.semanticscholar.org"
        else None
    )
    with pytest.raises(ServiceError) as exc:
        retrieve(provider)
    assert "private" not in str(exc.value) + caplog.text


def test_transient_backoff_is_bounded_and_has_jitter(monkeypatch):
    monkeypatch.setattr(module.random, "uniform", lambda low, high: high)
    assert module._backoff(0) == 1.25
    assert module._backoff(1) == 2.25
    assert module._backoff(20) == module.MAX_RETRY_DELAY_SECONDS


def test_duplicate_doi_lookups_across_openalex_ids_share_one_request(provider):
    provider.works["W300"] = {"id": "https://openalex.org/W300", "doi": "10.1000/cited"}

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            results = await asyncio.gather(service._map_paper("W200"), service._map_paper("W300"))
            assert all(mapping.verified for mapping in results)
            assert len(provider.calls) == 3  # two distinct OpenAlex works, one shared DOI lookup

    asyncio.run(run())


def test_queued_request_timeout_is_explicit(monkeypatch):
    monkeypatch.setattr(module, "SEMANTIC_QUEUE_TIMEOUT_SECONDS", 0.01)

    async def run():
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(lambda request: pytest.fail())
        ) as client:
            service = CitationContextService(client, settings())
            async with service._semantic_lock:
                with pytest.raises(ServiceError) as exc:
                    await service._get("semantic_scholar", "paper/a", {})
                assert exc.value.code == "semantic_scholar_busy"

    asyncio.run(run())


def test_cancellation_during_backoff_stops_retries(monkeypatch):
    calls = []

    async def run():
        backing_off = asyncio.Event()

        async def sleep(seconds):
            backing_off.set()
            await asyncio.Event().wait()

        def handler(request):
            calls.append(request)
            return httpx.Response(503)

        monkeypatch.setattr(module.asyncio, "sleep", sleep)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = CitationContextService(client, settings())
            task = asyncio.create_task(service._get("semantic_scholar", "paper/a", {}))
            await backing_off.wait()
            task.cancel()
            with pytest.raises(asyncio.CancelledError):
                await task
            assert len(calls) == 1

    asyncio.run(run())


def test_invalid_reference_response_does_not_poison_cache(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            provider.pages[0]["data"][1]["contexts"] = "invalid"
            with pytest.raises(ServiceError):
                await service.retrieve(PAIR, mode="live")
            assert not service._references._values
            provider.pages[0]["data"][1]["contexts"] = ["Corrected synthetic context."]
            result = await service.retrieve(PAIR, mode="live")
            assert (
                result.available
                and result.contexts[0].context_text == "Corrected synthetic context."
            )

    asyncio.run(run())


def test_unverified_metadata_is_not_cached_as_a_resolved_paper(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            provider.papers["10.1000/citing"]["externalIds"]["DOI"] = "10.1000/wrong"
            result = await service._map_paper("W100")
            assert not result.verified and not service._semantic_papers._values

    asyncio.run(run())


# Diagnostics regression tests. Every payload below is synthetic and only exercises
# validation branches; none reproduces a recorded live provider response.
def _invalid_logs(caplog):
    return [
        r.getMessage()
        for r in caplog.records
        if "citation_provider_invalid_response" in r.getMessage()
    ]


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda page: page.update(data="not a list"), "field=data observed=str"),
        (lambda page: page.pop("data"), "field=data observed=absent"),
        (lambda page: page.update(next="100"), "field=next observed=str"),
        (lambda page: page.update(offset=5), "field=offset observed=int"),
    ],
)
def test_page_level_invalid_response_is_attributed(provider, caplog, change, expected):
    change(provider.pages[0])
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.code == "semantic_scholar_invalid_response"
    [message] = _invalid_logs(caplog)
    assert "stage=reference_page" in message and expected in message
    assert "recoverable=false" in message


def test_row_level_invalid_response_reports_row_without_values(provider, caplog):
    # Current behavior is preserved: one malformed DOI still rejects the page.
    provider.pages[0]["data"][0]["citedPaper"]["externalIds"]["DOI"] = "synthetic bad doi"
    with pytest.raises(ServiceError):
        retrieve(provider)
    [message] = _invalid_logs(caplog)
    assert "category=unnormalizable_doi" in message and "row=0" in message
    assert "synthetic bad doi" not in caplog.text
    assert "synthetic context" not in caplog.text.lower()


def test_auto_mode_public_reason_is_unchanged(provider, caplog):
    provider.pages[0].pop("data")
    result = retrieve(provider, mode="auto")
    assert result.status == "provider_unavailable"
    assert result.reason == "semantic_scholar_invalid_response"
    assert result.contexts == [] and result.relationship_found is None
    assert "stage=reference_page" in _invalid_logs(caplog)[0]


def test_top_level_key_names_are_sanitized(provider, caplog):
    provider.pages[0].pop("data")
    provider.pages[0]["bad key with spaces"] = 1
    with pytest.raises(ServiceError):
        retrieve(provider)
    [message] = _invalid_logs(caplog)
    assert "'offset'" in message and "bad key" not in message


# Live observation (2026-11-14, W2140584250, sanitized diagnostics only): HTTP 200
# with top-level keys exactly {"citingPaperInfo", "data"} and data=null. The page
# below copies only that observed structure; its field contents are synthetic.
def _withheld_reference_page():
    return {"citingPaperInfo": {"title": "Citing fixture"}, "data": None}


def test_withheld_reference_list_is_reported_as_unavailable_not_invalid(provider, caplog):
    provider.pages[0] = _withheld_reference_page()
    result = retrieve(provider, mode="auto")
    assert result.status == "provider_unavailable"
    assert result.reason == "semantic_scholar_references_unavailable"
    # Withheld references neither prove nor disprove the citation.
    assert result.relationship_found is None and result.contexts == []
    assert not _invalid_logs(caplog)


def test_withheld_reference_list_raises_explicit_error_in_live_mode(provider):
    provider.pages[0] = _withheld_reference_page()
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.code == "semantic_scholar_references_unavailable"
    assert error.value.status_code == 503


def test_withheld_reference_list_is_not_cached_as_a_page(provider):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            original = provider.pages[0]
            provider.pages[0] = _withheld_reference_page()
            with pytest.raises(ServiceError):
                await service.retrieve(PAIR, mode="live")
            assert not service._references._values
            provider.pages[0] = original
            assert (await service.retrieve(PAIR, mode="live")).available

    asyncio.run(run())


def test_null_data_on_a_later_page_stays_invalid(provider, caplog):
    # Only a withheld first page is a recognised provider state; a list that
    # disappears mid-pagination remains an invalid response.
    provider.pages[0]["next"] = 100
    provider.pages[100] = {"offset": 100, "data": None}
    with pytest.raises(ServiceError) as error:
        retrieve(provider)
    assert error.value.code == "semantic_scholar_invalid_response"
    assert "field=data observed=NoneType" in _invalid_logs(caplog)[0]


def test_malformed_doi_on_alternative_identifier_match_fails_closed(provider):
    # Previously an uncaught ValueError escaped retrieval (unhandled server error).
    provider.works["W200"] = {
        "id": "https://openalex.org/W200",
        "title": "Cited fixture",
        "doi": None,
        "ids": {"mag": "200"},
    }

    def override(request):
        if request.url.host == "api.semanticscholar.org" and "/paper/MAG:" in request.url.path:
            return httpx.Response(
                200, json={"paperId": CITED, "externalIds": {"MAG": "200", "DOI": "not a doi"}}
            )
        return None

    provider.override = override
    result = retrieve(provider, mode="auto")
    assert result.status == "unresolved_identifiers"
    assert not result.cited_mapping.verified
    assert result.cited_mapping.reason == "unverified_semantic_scholar_doi"
    assert result.contexts == [] and result.relationship_found is None
    assert not any(request.url.path.endswith("/references") for request in provider.calls)


def test_alternative_identifier_match_with_valid_doi_still_verifies(provider):
    provider.works["W200"] = {
        "id": "https://openalex.org/W200",
        "title": "Cited fixture",
        "doi": None,
        "ids": {"mag": "200"},
    }

    def override(request):
        if request.url.host == "api.semanticscholar.org" and "/paper/MAG:" in request.url.path:
            return httpx.Response(
                200, json={"paperId": CITED, "externalIds": {"MAG": "200", "DOI": "10.1000/cited"}}
            )
        return None

    provider.override = override
    result = retrieve(provider)
    assert result.cited_mapping.verified and result.status == "available"


# Batched identifier resolution (synthetic fixture; same verification rules).
def s2_requests(provider, suffix=""):
    return [
        r
        for r in provider.calls
        if r.url.host == "api.semanticscholar.org" and r.url.path.endswith(suffix)
    ]


def test_one_batch_replaces_sequential_identifier_lookups(provider):
    result = retrieve(provider)
    assert result.available and result.citing_mapping.verified and result.cited_mapping.verified
    [batch] = s2_requests(provider, "/paper/batch")
    assert batch.method == "POST" and batch.url.params["fields"] == "paperId,externalIds"
    assert json.loads(batch.content) == {"ids": ["DOI:10.1000/citing", "DOI:10.1000/cited"]}
    # No individual GET lookups remain; only the batch and one references page.
    assert [r.url.path.rsplit("/", 1)[-1] for r in s2_requests(provider)] == [
        "batch",
        "references",
    ]


def test_batch_results_still_pass_through_identity_verification(provider):
    # The batch returns a record whose DOI contradicts OpenAlex: never verified.
    provider.papers["10.1000/cited"]["externalIds"]["DOI"] = "10.1000/other"
    result = retrieve(provider)
    assert result.status == "unresolved_identifiers" and not result.cited_mapping.verified
    assert result.cited_mapping.reason == "semantic_scholar_doi_mismatch"
    assert result.contexts == [] and len(s2_requests(provider, "/paper/batch")) == 1


@pytest.mark.parametrize(
    "rejection",
    [
        httpx.Response(400),
        httpx.Response(200, json={"not": "a list"}),
        httpx.Response(200, json=[None]),  # wrong length
    ],
)
def test_rejected_or_malformed_batch_falls_back_to_single_lookups(provider, rejection):
    provider.override = lambda r: rejection if r.url.path.endswith("/paper/batch") else None
    result = retrieve(provider)
    assert result.available and result.cited_mapping.verified
    singles = [r for r in s2_requests(provider) if "/paper/DOI:" in r.url.path]
    assert len(s2_requests(provider, "/paper/batch")) == 1 and len(singles) == 2


def test_throttled_batch_does_not_multiply_requests(provider):
    provider.override = lambda r: (
        httpx.Response(429) if r.url.host == "api.semanticscholar.org" else None
    )
    result = retrieve(provider, mode="auto")
    assert result.status == "provider_unavailable"
    assert result.reason == "semantic_scholar_rate_limited"
    # Three bounded attempts of one batch; no fallback storm of single lookups.
    assert [r.url.path.endswith("/paper/batch") for r in s2_requests(provider)] == [True] * 3


def test_cached_identifiers_are_not_requested_again(provider):
    provider.works["W300"] = {"id": "https://openalex.org/W300", "doi": "10.1000/third"}
    provider.papers["10.1000/third"] = {
        "paperId": "d" * 40,
        "externalIds": {"DOI": "10.1000/third"},
    }
    provider.pages[0]["data"].append(
        {"citedPaper": provider.papers["10.1000/third"], "contexts": ["Synthetic third passage."]}
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            service._examples = {}
            await service.retrieve(PAIR, mode="live")
            provider.calls.clear()
            third = await service.retrieve(
                CitationPair(citing_paper_id="W100", cited_paper_id="W300"), mode="live"
            )
            assert third.available
            # The citing mapping is cached; one remaining identifier needs no batch.
            lookups = [r.url.path for r in s2_requests(provider) if "/references" not in r.url.path]
            assert lookups == ["/graph/v1/paper/DOI:10.1000/third"]

    asyncio.run(run())
