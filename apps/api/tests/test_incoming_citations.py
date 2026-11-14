"""Incoming-citation tests using only labeled synthetic, offline OpenAlex records."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.fixture
def provider(client, monkeypatch):
    calls, responses = [], []

    def handler(request):
        calls.append(request)
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client.app.state, "http", upstream)
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", AsyncMock())
    yield responses, calls
    asyncio.run(upstream.aclose())


def seed():
    return httpx.Response(200, json={"id": "https://openalex.org/W123", "title": "Synthetic seed"})


def page(ids=(), cursor=None):
    return httpx.Response(
        200,
        json={
            "meta": {"next_cursor": cursor},
            "results": [
                {"id": f"https://openalex.org/{work_id}", "title": "Synthetic citing paper"}
                for work_id in ids
            ],
        },
    )


def test_incoming_direction_and_filter_without_database(client, provider):
    responses, calls = provider
    responses.extend([seed(), page(["W200", "W300"], "next+/=")])
    client.app.state.settings.openalex_api_key = "test-only-key"
    response = client.get("/api/v1/papers/W123/citations")
    assert response.status_code == 200
    data = response.json()
    assert data["seed_paper_id"] == "W123"
    assert [p["id"] for p in data["papers"]] == ["W123", "W200", "W300"]
    assert [(e["source"], e["target"]) for e in data["citations"]] == [
        ("W200", "W123"),
        ("W300", "W123"),
    ]
    for edge in data["citations"]:
        assert edge["id"] == f"{edge['source']}->{edge['target']}"
        assert all(
            edge[f] is None for f in ("intent", "confidence", "context_text", "context_source_url")
        )
    assert data["next_cursor"] == "next+/="
    assert data["has_more"] is True
    assert data["skipped_record_count"] == 0
    assert client.app.state.settings.database_url == ""
    assert len(calls) == 2
    assert calls[1].url.path == "/works"
    assert dict(calls[1].url.params) == {"filter": "cites:W123", "per_page": "10", "cursor": "*"}
    assert calls[1].headers["Authorization"] == "Bearer test-only-key"
    assert "api_key" not in calls[1].url.params
    assert calls[1].extensions["timeout"]["read"] == 10.0


def test_cursor_round_trip_and_terminal_page(client, provider):
    responses, calls = provider
    responses.extend([seed(), page(["W200"], "opaque+/="), seed(), page(["W300"]), seed(), page()])
    first = client.get("/api/v1/papers/W123/citations?limit=1").json()
    second = client.get(
        "/api/v1/papers/W123/citations",
        params={
            "limit": 1,
            "cursor": first["next_cursor"],
        },
    ).json()
    assert calls[3].url.params["cursor"] == "opaque+/="
    assert second["next_cursor"] is None
    assert second["has_more"] is False
    assert second["citations"][0]["source"] == "W300"
    empty = client.get("/api/v1/papers/W123/citations").json()
    assert len(empty["papers"]) == 1
    assert empty["citations"] == []
    assert empty["has_more"] is False


def test_partial_records_deduplicate_without_inventing_data(client, provider):
    responses, _ = provider
    responses.extend(
        [
            seed(),
            httpx.Response(
                200,
                json={
                    "meta": {"next_cursor": "more"},
                    "results": [
                        {"id": "W200"},
                        {"id": "https://openalex.org/W200"},
                        {"id": "W123"},
                        None,
                        {"id": "W300", "cited_by_count": -1},
                    ],
                },
            ),
        ]
    )
    data = client.get("/api/v1/papers/W123/citations").json()
    assert len(data["papers"]) == 2
    assert len(data["citations"]) == 1
    assert data["papers"][1]["abstract"] is None
    assert data["papers"][1]["authors"] == []
    assert data["skipped_record_count"] == 3
    assert data["has_more"] is True


def test_empty_filtered_page_preserves_progressing_cursor(client, provider):
    responses, _ = provider
    responses.extend([seed(), page(["W123"], "more")])
    data = client.get("/api/v1/papers/W123/citations").json()
    assert data["citations"] == []
    assert data["next_cursor"] == "more"
    assert data["has_more"] is True


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 51},
        {"limit": "abc"},
        {"cursor": ""},
        {"cursor": " "},
        {"cursor": "a b"},
        {"cursor": "a" * 2049},
    ],
)
def test_invalid_queries_never_call_provider(client, provider, params):
    _, calls = provider
    response = client.get("/api/v1/papers/W123/citations", params=params)
    assert response.status_code == 422
    assert calls == []


def test_invalid_id_never_calls_provider(client, provider):
    _, calls = provider
    assert client.get("/api/v1/papers/invalid/citations").status_code == 422
    assert calls == []


def test_missing_seed(client, provider):
    responses, calls = provider
    responses.append(httpx.Response(404))
    response = client.get("/api/v1/papers/W123/citations")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "paper_not_found"
    assert len(calls) == 1


def test_merged_seed_uses_canonical_id(client, provider):
    responses, calls = provider
    responses.extend([seed(), page(["W200"])])
    data = client.get("/api/v1/papers/W999/citations").json()
    assert calls[1].url.params["filter"] == "cites:W123"
    assert data["citations"][0]["target"] == "W123"


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"results": []},
        {"results": [], "meta": {}},
        {"results": {}, "meta": {"next_cursor": None}},
        {"results": [], "meta": None},
        *[
            {"results": [], "meta": {"next_cursor": value}}
            for value in (
                42,
                "",
                "bad cursor",
                "*",
                "x" * 2049,
            )
        ],
    ],
)
def test_invalid_provider_pagination(client, provider, payload):
    responses, _ = provider
    responses.extend([seed(), httpx.Response(200, json=payload)])
    response = client.get("/api/v1/papers/W123/citations")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openalex_invalid_response"


def test_maximum_limit(client, provider):
    responses, calls = provider
    responses.extend([seed(), page([f"W{i}" for i in range(1000, 1050)])])
    data = client.get("/api/v1/papers/W123/citations?limit=50").json()
    assert calls[1].url.params["per_page"] == "50"
    assert len(data["papers"]) == 51
    assert len(data["citations"]) == 50


def test_oversized_provider_page_is_rejected(client, provider):
    responses, _ = provider
    responses.extend([seed(), page(["W200", "W300"])])
    assert client.get("/api/v1/papers/W123/citations?limit=1").status_code == 502


@pytest.mark.parametrize("failure,expected", [(429, 503), (500, 503), ("timeout", 502)])
def test_provider_failure_retries_are_bounded(client, provider, failure, expected):
    responses, calls = provider
    responses.append(seed())
    responses.extend(
        [
            httpx.ReadTimeout("Synthetic timeout")
            if failure == "timeout"
            else httpx.Response(failure)
            for _ in range(3)
        ]
    )
    response = client.get("/api/v1/papers/W123/citations")
    assert response.status_code == expected
    assert response.json()["error"]["code"] == "openalex_unavailable"
    assert len(calls) == 4


def test_transient_failure_recovers(client, provider):
    responses, calls = provider
    responses.extend([seed(), httpx.Response(429), page(["W200"])])
    assert client.get("/api/v1/papers/W123/citations").status_code == 200
    assert len(calls) == 3


@pytest.mark.parametrize(
    "status,key,expected,code",
    [
        (400, "", 422, "invalid_cursor"),
        (401, "", 503, "openalex_key_required"),
        (401, "synthetic-test-key", 502, "openalex_error"),
        (403, "", 502, "openalex_error"),
    ],
)
def test_cursor_and_authentication_errors(client, provider, status, key, expected, code):
    responses, calls = provider
    client.app.state.settings.openalex_api_key = key
    responses.extend([seed(), httpx.Response(status)])
    response = client.get("/api/v1/papers/W123/citations?cursor=synthetic-token")
    assert response.status_code == expected
    assert response.json()["error"]["code"] == code
    assert len(calls) == 2
