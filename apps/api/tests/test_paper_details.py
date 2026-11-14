"""Paper-detail endpoint tests using synthetic, offline OpenAlex fixtures only."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.fixture
def detail_work(openalex_fixture):
    return {
        **openalex_fixture["results"][0],
        "doi": "https://doi.org/10.0000/synthetic-fixture",
        "primary_location": {
            "source": {"display_name": "Synthetic Test Journal"},
            "landing_page_url": "https://example.org/fixture",
        },
        "referenced_works": ["https://openalex.org/W100", "https://openalex.org/W200"],
    }


@pytest.fixture
def provider(client, monkeypatch):
    calls = []
    responses = []

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


def test_paper_details_without_database(client, provider, detail_work):
    responses, calls = provider
    responses.append(httpx.Response(200, json=detail_work))
    client.app.state.settings.openalex_api_key = "test-only-key"
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 200
    assert response.json() == {
        "id": "W123",
        "doi": "https://doi.org/10.0000/synthetic-fixture",
        "title": "Synthetic test fixture",
        "authors": ["Test Author"],
        "year": 2024,
        "abstract": "A citation context",
        "cited_by_count": 4,
        "publication_venue": "Synthetic Test Journal",
        "landing_page_url": "https://example.org/fixture",
        "reference_count": 2,
    }
    assert client.app.state.settings.database_url == ""
    assert len(calls) == 1
    assert calls[0].url.path == "/works/W123"
    assert calls[0].headers["Authorization"] == "Bearer test-only-key"
    assert "api_key" not in calls[0].url.params
    assert calls[0].extensions["timeout"]["read"] == 10.0


def test_missing_metadata(client, provider):
    responses, _ = provider
    responses.append(httpx.Response(200, json={"id": "https://openalex.org/W123"}))
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 200
    paper = response.json()
    assert paper["title"] == "Untitled work"
    assert paper["authors"] == []
    assert paper["cited_by_count"] == 0
    for field in (
        "doi",
        "year",
        "abstract",
        "publication_venue",
        "landing_page_url",
        "reference_count",
    ):
        assert paper[field] is None


@pytest.mark.parametrize("references", [[], ["https://openalex.org/W100"]])
def test_nullable_metadata_and_reference_list(client, provider, references):
    responses, _ = provider
    responses.append(
        httpx.Response(
            200,
            json={
                "id": "W123",
                "authorships": None,
                "primary_location": None,
                "abstract_inverted_index": None,
                "referenced_works": references,
            },
        )
    )
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 200
    assert response.json()["reference_count"] == len(references)
    assert response.json()["abstract"] is None


def test_provider_reference_count_takes_precedence(client, provider, detail_work):
    responses, _ = provider
    detail_work["referenced_works_count"] = 10
    responses.append(httpx.Response(200, json=detail_work))
    assert client.get("/api/v1/papers/W123").json()["reference_count"] == 10


@pytest.mark.parametrize("work_id", ["invalid", "123", "A123", "W-1", "w123"])
def test_invalid_identifier_never_calls_provider(client, provider, work_id):
    _, calls = provider
    response = client.get(f"/api/v1/papers/{work_id}")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"
    assert calls == []


@pytest.mark.parametrize(
    "status,expected,code",
    [
        (404, 404, "paper_not_found"),
        (401, 502, "openalex_error"),
        (403, 502, "openalex_error"),
        (302, 502, "openalex_error"),
    ],
)
def test_upstream_errors(client, provider, status, expected, code):
    responses, calls = provider
    responses.append(httpx.Response(status))
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == expected
    assert response.json()["error"]["code"] == code
    assert len(calls) == 1


@pytest.mark.parametrize(
    "payload",
    [
        {},
        [],
        None,
        {"id": "invalid"},
        {"id": "W123", "primary_location": [1]},
        {"id": "W123", "referenced_works_count": -1},
        {"id": "W123", "abstract_inverted_index": ["invalid"]},
    ],
)
def test_malformed_upstream_data(client, provider, payload):
    responses, _ = provider
    responses.append(httpx.Response(200, json=payload))
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openalex_invalid_response"


def test_invalid_json(client, provider):
    responses, _ = provider
    responses.append(httpx.Response(200, text="not JSON"))
    assert client.get("/api/v1/papers/W123").status_code == 502


@pytest.mark.parametrize(
    "failure,expected",
    [
        (429, 503),
        (500, 503),
        (503, 503),
        ("timeout", 502),
        ("connection", 502),
    ],
)
def test_bounded_retries(client, provider, failure, expected):
    responses, calls = provider
    for _ in range(3):
        if failure == "timeout":
            responses.append(httpx.ReadTimeout("Synthetic timeout"))
        elif failure == "connection":
            responses.append(httpx.ConnectError("Synthetic connection failure"))
        else:
            responses.append(httpx.Response(failure))
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == expected
    assert response.json()["error"]["code"] == "openalex_unavailable"
    assert len(calls) == 3
    assert asyncio.sleep.await_args_list[0].args == (0.25,)
    assert asyncio.sleep.await_args_list[1].args == (0.5,)


@pytest.mark.parametrize("failure", [429, 500, "timeout"])
def test_transient_failure_recovers(client, provider, detail_work, failure):
    responses, calls = provider
    responses.extend(
        [
            httpx.ReadTimeout("Synthetic timeout")
            if failure == "timeout"
            else httpx.Response(failure),
            httpx.Response(200, json=detail_work),
        ]
    )
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 200
    assert response.json()["id"] == "W123"
    assert len(calls) == 2
