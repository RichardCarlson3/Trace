"""Graph-neighbor integration tests with synthetic offline OpenAlex responses."""

import asyncio
import base64
import json
from unittest.mock import AsyncMock

import httpx
import pytest


def record(work_id):
    return {"id": f"https://openalex.org/{work_id}", "title": "Synthetic fixture"}


@pytest.fixture
def provider(client, monkeypatch):
    state = {
        "seed": {**record("W123"), "referenced_works": ["W100", "W200", "W300"]},
        "references": {work_id: record(work_id) for work_id in ("W100", "W200", "W300")},
        "incoming": [record(work_id) for work_id in ("W200", "W400", "W500")],
        "calls": [],
        "seed_status": 200,
        "incoming_status": 200,
    }

    def handler(request):
        state["calls"].append(request)
        if request.url.path.startswith("/works/"):
            return httpx.Response(state["seed_status"], json=state["seed"])
        query = request.url.params
        if query["filter"].startswith("ids.openalex:"):
            ids = query["filter"].removeprefix("ids.openalex:").split("|")
            return httpx.Response(
                200,
                json={
                    "results": [
                        state["references"][work_id]
                        for work_id in ids
                        if work_id in state["references"]
                    ]
                },
            )
        assert query["filter"] == "cites:W123"
        if state["incoming_status"] != 200:
            return httpx.Response(state["incoming_status"])
        offset = 0 if query["cursor"] == "*" else int(query["cursor"].removeprefix("offset_"))
        end = offset + int(query["per_page"])
        return httpx.Response(
            200,
            json={
                "results": state["incoming"][offset:end],
                "meta": {"next_cursor": f"offset_{end}" if end < len(state["incoming"]) else None},
            },
        )

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client.app.state, "http", upstream)
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", AsyncMock())
    yield state
    asyncio.run(upstream.aclose())


def edge_pairs(page):
    return {(edge["source"], edge["target"]) for edge in page["citations"]}


def assert_graph(page, limit):
    ids = {paper["id"] for paper in page["papers"]}
    assert len(ids) == len(page["papers"])
    assert page["papers"][0]["id"] == page["seed_paper_id"]
    assert len(ids) <= limit + 1
    assert len(page["citations"]) <= limit
    assert len(edge_pairs(page)) == len(page["citations"])
    assert page["has_more"] is (page["next_cursor"] is not None)
    for edge in page["citations"]:
        assert edge["source"] in ids and edge["target"] in ids
        assert edge["id"] == f"{edge['source']}->{edge['target']}"
        assert all(
            edge[field] is None
            for field in ("intent", "confidence", "context_text", "context_source_url")
        )


@pytest.mark.parametrize("direction", ["incoming", "outgoing", "both"])
@pytest.mark.parametrize("limit", [1, 2, 3, 4, 5, 50])
def test_complete_traversal_is_bounded_and_lossless(client, provider, direction, limit):
    expected_outgoing = {("W123", work_id) for work_id in ("W100", "W200", "W300")}
    expected_incoming = {(work_id, "W123") for work_id in ("W200", "W400", "W500")}
    expected = (
        expected_outgoing
        if direction == "outgoing"
        else expected_incoming
        if direction == "incoming"
        else expected_incoming | expected_outgoing
    )
    cursor, seen, tokens = "*", set(), set()
    for _ in range(12):
        before = len(provider["calls"])
        response = client.get(
            "/api/v1/papers/W123/neighbors",
            params={
                "direction": direction,
                "limit": limit,
                "cursor": cursor,
            },
        )
        assert response.status_code == 200
        page = response.json()
        assert_graph(page, limit)
        assert not seen & edge_pairs(page)
        seen |= edge_pairs(page)
        requests = provider["calls"][before:]
        assert sum(request.url.path.startswith("/works/") for request in requests) == 1
        assert len(requests) <= (3 if direction == "both" else 2)
        if not page["has_more"]:
            break
        cursor = page["next_cursor"]
        assert cursor not in tokens
        tokens.add(cursor)
    else:
        pytest.fail("Traversal did not terminate")
    assert seen == expected
    assert client.app.state.settings.database_url == ""


def test_both_merges_common_paper_but_preserves_opposite_edges(client, provider):
    page = client.get("/api/v1/papers/W123/neighbors?limit=6").json()
    assert_graph(page, 6)
    assert len(page["papers"]) == 6
    assert len(page["citations"]) == 6
    assert ("W123", "W200") in edge_pairs(page)
    assert ("W200", "W123") in edge_pairs(page)


def test_limit_one_alternates_directions(client, provider):
    first = client.get("/api/v1/papers/W123/neighbors?limit=1").json()
    second = client.get(
        "/api/v1/papers/W123/neighbors",
        params={
            "limit": 1,
            "cursor": first["next_cursor"],
        },
    ).json()
    assert edge_pairs(first) == {("W123", "W100")}
    assert edge_pairs(second) == {("W200", "W123")}


@pytest.mark.parametrize("empty", ["incoming", "outgoing", "both"])
def test_empty_direction_and_budget_transfer(client, provider, empty):
    if empty in ("incoming", "both"):
        provider["incoming"] = []
    if empty in ("outgoing", "both"):
        provider["seed"]["referenced_works"] = []
    first = client.get("/api/v1/papers/W123/neighbors?limit=2").json()
    if empty == "both":
        assert first["citations"] == []
        assert len(first["papers"]) == 1
        assert first["next_cursor"] is None
    else:
        assert len(first["citations"]) == 1
        second = client.get(
            "/api/v1/papers/W123/neighbors",
            params={
                "limit": 2,
                "cursor": first["next_cursor"],
            },
        ).json()
        assert len(second["citations"]) == 2
        assert second["next_cursor"] is None


def test_partial_data_and_deduplication(client, provider):
    provider["seed"]["referenced_works"] = ["W123", "W100", "W100", "W200", "W300"]
    provider["references"]["W200"] = {"id": "W200", "cited_by_count": -1}
    del provider["references"]["W300"]
    provider["incoming"] = [record("W400"), record("W400"), None, record("W123")]
    page = client.get("/api/v1/papers/W123/neighbors?limit=8").json()
    assert_graph(page, 8)
    assert edge_pairs(page) == {("W123", "W100"), ("W400", "W123")}
    assert page["unresolved_reference_ids"] == ["W200", "W300"]
    assert page["skipped_record_count"] == 2
    assert page["has_more"] is False


def test_default_and_maximum_limits(client, provider):
    ids = [f"W{i}" for i in range(1000, 1500)]
    provider["seed"]["referenced_works"] = ids
    provider["references"] = {work_id: record(work_id) for work_id in ids}
    provider["incoming"] = [record(f"W{i}") for i in range(2000, 2500)]
    for params, limit in [({}, 10), ({"limit": 50}, 50)]:
        page = client.get("/api/v1/papers/W123/neighbors", params=params).json()
        assert_graph(page, limit)
        assert len(page["citations"]) == limit
        assert page["has_more"] is True


@pytest.mark.parametrize(
    "params",
    [
        {"direction": "invalid"},
        {"limit": 0},
        {"limit": 51},
        {"limit": "abc"},
        {"cursor": ""},
        {"cursor": "bad cursor"},
        {"cursor": "x" * 8193},
        {"cursor": "not_a_valid_token"},
    ],
)
def test_invalid_queries_before_provider_requests(client, provider, params):
    response = client.get("/api/v1/papers/W123/neighbors", params=params)
    assert response.status_code == 422
    assert provider["calls"] == []


def test_invalid_id(client, provider):
    assert client.get("/api/v1/papers/invalid/neighbors").status_code == 422
    assert provider["calls"] == []


@pytest.mark.parametrize("change", [{"direction": "incoming"}, {"limit": 5}, {"id": "W999"}])
def test_cursor_is_bound_to_its_query(client, provider, change):
    first = client.get("/api/v1/papers/W123/neighbors?limit=2").json()
    before = len(provider["calls"])
    params = {"cursor": first["next_cursor"], "direction": "both", "limit": 2, **change}
    work_id = params.pop("id", "W123")
    response = client.get(f"/api/v1/papers/{work_id}/neighbors", params=params)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"
    assert len(provider["calls"]) == before


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"outgoing_offset": -1},
        {"outgoing_offset": True},
        {"incoming_cursor": "bad cursor"},
        {"incoming_cursor": "x" * 2049},
        {"outgoing_offset": None, "incoming_cursor": None},
        {"unexpected": True},
    ],
)
def test_invalid_cursor_state(client, provider, change):
    state = {
        "work_id": "W123",
        "direction": "both",
        "limit": 2,
        "outgoing_offset": 0,
        "incoming_cursor": "*",
        **change,
    }
    cursor = base64.urlsafe_b64encode(json.dumps(state).encode()).decode().rstrip("=")
    response = client.get("/api/v1/papers/W123/neighbors", params={"limit": 2, "cursor": cursor})
    assert response.status_code == 422
    assert provider["calls"] == []


def test_missing_seed(client, provider):
    provider["seed_status"] = 404
    response = client.get("/api/v1/papers/W123/neighbors")
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "paper_not_found"
    assert len(provider["calls"]) == 1


def test_malformed_seed(client, provider):
    provider["seed"] = {"id": "invalid"}
    response = client.get("/api/v1/papers/W123/neighbors")
    assert response.status_code == 502
    assert len(provider["calls"]) == 1


@pytest.mark.parametrize(
    "status,expected,code",
    [
        (429, 503, "openalex_unavailable"),
        (500, 503, "openalex_unavailable"),
        (401, 503, "openalex_key_required"),
        (400, 422, "invalid_cursor"),
    ],
)
def test_one_failed_direction_does_not_pretend_success(client, provider, status, expected, code):
    client.app.state.settings.openalex_api_key = ""
    provider["incoming_status"] = status
    response = client.get("/api/v1/papers/W123/neighbors")
    assert response.status_code == expected
    assert response.json()["error"]["code"] == code
