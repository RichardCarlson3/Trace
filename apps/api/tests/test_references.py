"""Outgoing reference tests; every provider response is an offline synthetic fixture."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest


@pytest.fixture
def reference_provider(client, monkeypatch):
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


def seed(*ids):
    return httpx.Response(
        200,
        json={
            "id": "https://openalex.org/W123",
            "display_name": "Synthetic seed",
            "referenced_works": list(ids),
        },
    )


def batch(*ids):
    return httpx.Response(
        200,
        json={
            "results": [
                {"id": f"https://openalex.org/{work_id}", "display_name": "Synthetic reference"}
                for work_id in ids
            ]
        },
    )


def test_outgoing_direction_and_batching_without_database(client, reference_provider):
    responses, calls = reference_provider
    responses.extend([seed("https://openalex.org/W100", "W200"), batch("W200", "W100")])
    response = client.get("/api/v1/papers/W123/references")
    assert response.status_code == 200
    data = response.json()
    assert data["seed_paper_id"] == "W123"
    assert [paper["id"] for paper in data["papers"]] == ["W123", "W100", "W200"]
    assert [(edge["source"], edge["target"]) for edge in data["citations"]] == [
        ("W123", "W100"),
        ("W123", "W200"),
    ]
    for edge in data["citations"]:
        assert edge["id"] == f"{edge['source']}->{edge['target']}"
        for field in ("intent", "confidence", "context_text", "context_source_url"):
            assert edge[field] is None
    assert data["has_more"] is False
    assert data["next_offset"] is None
    assert data["unresolved_reference_ids"] == []
    assert client.app.state.settings.database_url == ""
    assert len(calls) == 2
    assert calls[0].url.path == "/works/W123"
    assert calls[1].url.path == "/works"
    assert calls[1].url.params["filter"] == "ids.openalex:W100|W200"
    assert calls[1].url.params["per_page"] == "2"
    assert data["papers"][1]["abstract"] is None
    assert data["papers"][1]["authors"] == []


def test_deduplicates_references_records_and_self_links(client, reference_provider):
    responses, calls = reference_provider
    responses.extend(
        [
            seed("W123", "W100", "https://openalex.org/W100", "W200", "W300", "W400"),
            batch("W100", "W100", "W200", "W999"),
        ]
    )
    data = client.get("/api/v1/papers/W123/references").json()
    assert len(data["papers"]) == 3
    assert len(data["citations"]) == 2
    assert calls[1].url.params["filter"] == "ids.openalex:W100|W200|W300|W400"


def test_bounded_offset_pages(client, reference_provider):
    responses, calls = reference_provider
    for offset, ids, more, next_offset in [
        (0, ["W100", "W200"], True, 2),
        (2, ["W300"], False, None),
        (8, [], False, None),
    ]:
        responses.append(seed("W100", "W100", "W200", "W300"))
        if ids:
            responses.append(batch(*ids))
        before = len(calls)
        response = client.get(
            "/api/v1/papers/W123/references", params={"limit": 2, "offset": offset}
        )
        assert response.status_code == 200
        data = response.json()
        assert [paper["id"] for paper in data["papers"]] == ["W123", *ids]
        assert data["has_more"] is more
        assert data["next_offset"] == next_offset
        assert len(calls) - before == (2 if ids else 1)


@pytest.mark.parametrize("limit", [None, 50])
def test_large_list_uses_one_bounded_batch(client, reference_provider, limit):
    responses, calls = reference_provider
    ids = [f"W{i}" for i in range(1000, 1500)]
    count = limit or 10
    responses.extend([seed(*ids), batch(*ids[:count])])
    params = {} if limit is None else {"limit": limit}
    data = client.get("/api/v1/papers/W123/references", params=params).json()
    assert len(calls) == 2
    assert calls[1].url.params["per_page"] == str(count)
    assert calls[1].url.params["filter"] == f"ids.openalex:{'|'.join(ids[:count])}"
    assert len(data["citations"]) == count
    assert data["next_offset"] == count
    assert data["has_more"] is True


@pytest.mark.parametrize("references", [[], None, "absent"])
def test_no_reference_data_needs_no_batch(client, reference_provider, references):
    responses, calls = reference_provider
    payload = {"id": "W123"}
    if references != "absent":
        payload["referenced_works"] = references
    responses.append(httpx.Response(200, json=payload))
    data = client.get("/api/v1/papers/W123/references").json()
    assert len(data["papers"]) == 1
    assert data["citations"] == []
    assert data["has_more"] is False
    assert len(calls) == 1


def test_partial_batch_reports_unresolved_and_advances_by_slice(client, reference_provider):
    responses, _ = reference_provider
    responses.extend(
        [
            seed("W100", "W200", "W300", "W400", "W500"),
            httpx.Response(
                200,
                json={
                    "results": [
                        {"id": "W100", "title": "Synthetic reference"},
                        {"id": "W200", "cited_by_count": -1},
                        {"id": "W999"},
                        None,
                    ]
                },
            ),
        ]
    )
    data = client.get("/api/v1/papers/W123/references?limit=4").json()
    assert [paper["id"] for paper in data["papers"]] == ["W123", "W100"]
    assert len(data["citations"]) == 1
    assert data["unresolved_reference_ids"] == ["W200", "W300", "W400"]
    assert data["next_offset"] == 4
    assert data["has_more"] is True


@pytest.mark.parametrize(
    "params",
    [
        {"limit": 0},
        {"limit": 51},
        {"limit": -1},
        {"offset": -1},
        {"limit": "abc"},
        {"offset": "abc"},
    ],
)
def test_invalid_bounds_never_call_provider(client, reference_provider, params):
    _, calls = reference_provider
    response = client.get("/api/v1/papers/W123/references", params=params)
    assert response.status_code == 422
    assert calls == []


def test_invalid_id_never_calls_provider(client, reference_provider):
    _, calls = reference_provider
    assert client.get("/api/v1/papers/invalid/references").status_code == 422
    assert calls == []


def test_missing_seed_returns_404(client, reference_provider):
    responses, calls = reference_provider
    responses.append(httpx.Response(404))
    response = client.get("/api/v1/papers/W123/references")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "paper_not_found"
    assert len(calls) == 1


@pytest.mark.parametrize("references", ["W100", ["invalid"], [None]])
def test_malformed_reference_list(client, reference_provider, references):
    responses, _ = reference_provider
    responses.append(httpx.Response(200, json={"id": "W123", "referenced_works": references}))
    response = client.get("/api/v1/papers/W123/references")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openalex_invalid_response"


@pytest.mark.parametrize("payload", [{}, {"results": None}, {"results": {}}])
def test_malformed_batch_envelope(client, reference_provider, payload):
    responses, _ = reference_provider
    responses.extend([seed("W100"), httpx.Response(200, json=payload)])
    assert client.get("/api/v1/papers/W123/references").status_code == 502


@pytest.mark.parametrize("failure,expected", [(429, 503), (500, 503), ("timeout", 502)])
def test_batch_failure_uses_existing_retries(client, reference_provider, failure, expected):
    responses, calls = reference_provider
    responses.append(seed("W100"))
    responses.extend(
        [
            httpx.ReadTimeout("Synthetic timeout")
            if failure == "timeout"
            else httpx.Response(failure)
            for _ in range(3)
        ]
    )
    response = client.get("/api/v1/papers/W123/references")
    assert response.status_code == expected
    assert response.json()["error"]["code"] == "openalex_unavailable"
    assert len(calls) == 4


def test_transient_batch_failure_recovers(client, reference_provider):
    responses, calls = reference_provider
    responses.extend([seed("W100"), httpx.Response(429), batch("W100")])
    response = client.get("/api/v1/papers/W123/references")
    assert response.status_code == 200
    assert len(response.json()["citations"]) == 1
    assert len(calls) == 3


def test_canonical_seed_id_is_used_for_edges(client, reference_provider):
    responses, _ = reference_provider
    responses.extend([seed("W100"), batch("W100")])
    data = client.get("/api/v1/papers/W999/references").json()
    assert data["seed_paper_id"] == "W123"
    assert data["citations"][0]["source"] == "W123"
