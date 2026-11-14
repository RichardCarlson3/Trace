"""API reliability checks using synthetic metadata and synthetic credentials only."""

import asyncio
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app
from app.schemas.contracts import (
    Citation,
    Graph,
    IncomingCitationResponse,
    Paper,
    ReferenceResponse,
    RelationshipResponse,
)


@pytest.fixture
def provider(client, monkeypatch):
    responses, calls = [], []

    def handler(request):
        calls.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    monkeypatch.setattr(client.app.state, "http", upstream)
    monkeypatch.setattr("app.services.openalex.asyncio.sleep", AsyncMock())
    yield responses, calls
    asyncio.run(upstream.aclose())


@pytest.mark.parametrize(
    "value", ["W123", "w123", "https://openalex.org/w123", " HTTP://OPENALEX.ORG/W123 "]
)
def test_provider_work_ids_normalize_to_canonical_ascii(value):
    assert Paper(id=value, title="Synthetic fixture").id == "W123"


@pytest.mark.parametrize(
    "value", ["W١٢٣", "W１２３", "https://other.example/W123", "W123?key=test"]
)
def test_noncanonical_ids_are_rejected(value):
    with pytest.raises(ValidationError):
        Paper(id=value, title="Synthetic fixture")


@pytest.mark.parametrize(
    "value",
    [
        "10.0000/SYNTHETIC",
        " doi: 10.0000/SYNTHETIC ",
        "http://dx.doi.org/10.0000/SYNTHETIC",
        "https://doi.org/10.0000/synthetic",
        "HTTPS://DOI.ORG/10.0000/SYNTHETIC",
    ],
)
def test_doi_forms_have_one_canonical_representation(value):
    paper = Paper(id="W123", title="Synthetic fixture", doi=value)
    assert paper.doi == "https://doi.org/10.0000/synthetic"
    assert Paper.model_validate(paper.model_dump()).doi == paper.doi


@pytest.mark.parametrize("value", [None, "", "  "])
def test_missing_doi_stays_null(value):
    assert Paper(id="W123", title="Synthetic fixture", doi=value).doi is None


@pytest.mark.parametrize(
    "value",
    [
        "not-a-doi",
        "10.0000/",
        "https://other.example/10.0000/test",
        "https://doi.org/10.0000/test?tracking=1",
        "10.0000/white space",
        123,
    ],
)
def test_malformed_doi_is_rejected(value):
    with pytest.raises(ValidationError):
        Paper(id="W123", title="Synthetic fixture", doi=value)


def test_doi_url_encoding_preserves_identifier_punctuation():
    raw = Paper(id="W123", title="Synthetic fixture", doi="10.0000/Synthetic?#%")
    encoded = Paper(
        id="W123", title="Synthetic fixture", doi="https://doi.org/10.0000/Synthetic%3F%23%25"
    )
    assert raw.doi == encoded.doi == "https://doi.org/10.0000/synthetic%3F%23%25"


@pytest.mark.parametrize("kind", ["paper", "pair", "edge_id"])
def test_graph_contract_rejects_duplicate_identifiers_and_pairs(kind):
    papers = [
        Paper(id="W100", title="Synthetic fixture"),
        Paper(id="W200", title="Synthetic fixture"),
    ]
    edges = [Citation(id="edge-1", source="W100", target="W200")]
    if kind == "paper":
        papers.append(Paper(id="https://openalex.org/w100", title="Duplicate fixture"))
    elif kind == "pair":
        edges.append(Citation(id="edge-2", source="W100", target="W200"))
    else:
        edges.append(Citation(id="edge-1", source="W200", target="W100"))
    with pytest.raises(ValidationError):
        Graph(papers=papers, citations=edges)


def test_opposite_directed_pairs_remain_distinct():
    graph = Graph(
        papers=[
            Paper(id="W100", title="Synthetic fixture"),
            Paper(id="W200", title="Synthetic fixture"),
        ],
        citations=[
            Citation(id="W100->W200", source="W100", target="W200"),
            Citation(id="W200->W100", source="W200", target="W100"),
        ],
    )
    assert len(graph.citations) == 2


def test_relationship_response_requires_seed_and_incident_edges():
    papers = [Paper(id=f"W{i}", title="Synthetic fixture") for i in (100, 200, 300)]
    with pytest.raises(ValidationError, match="seed paper"):
        RelationshipResponse(seed_paper_id="W999", papers=papers)
    with pytest.raises(ValidationError, match="include the seed"):
        RelationshipResponse(
            seed_paper_id="W100",
            papers=papers,
            citations=[Citation(id="edge", source="W200", target="W300")],
        )


@pytest.mark.parametrize(
    "model,source,target",
    [
        (ReferenceResponse, "W200", "W100"),
        (IncomingCitationResponse, "W100", "W200"),
    ],
)
def test_direction_contract_rejects_reversed_edges(model, source, target):
    papers = [Paper(id=f"W{i}", title="Synthetic fixture") for i in (100, 200)]
    with pytest.raises(ValidationError):
        model(
            seed_paper_id="W100",
            papers=papers,
            citations=[Citation(id="edge", source=source, target=target)],
        )


def test_blank_optional_metadata_is_normalized_consistently(client, provider):
    responses, _ = provider
    responses.append(
        httpx.Response(
            200,
            json={
                "id": " https://openalex.org/w123 ",
                "display_name": "   ",
                "doi": " ",
                "authorships": [{"author": {"display_name": "   "}}, {"author": None}],
                "abstract_inverted_index": {},
                "primary_location": None,
            },
        )
    )
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 200
    paper = response.json()
    assert paper["id"] == "W123"
    assert paper["title"] == "Untitled work"
    assert paper["doi"] is None
    assert paper["authors"] == []
    assert paper["abstract"] is None
    assert paper["reference_count"] is None


def test_blank_title_falls_back_to_available_provider_title(client, provider):
    responses, _ = provider
    responses.append(
        httpx.Response(
            200,
            json={
                "id": "W123",
                "display_name": " ",
                "title": " Synthetic title ",
                "primary_location": {"source": {"display_name": " "}, "landing_page_url": " "},
            },
        )
    )
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 200
    paper = response.json()
    assert paper["title"] == "Synthetic title"
    assert paper["publication_venue"] is None
    assert paper["landing_page_url"] is None


@pytest.mark.parametrize(
    "index",
    [
        [],
        {"word": [-1]},
        {"word": [True]},
        {"word": ["0"]},
        {"word": 0},
        {"word": [0, 0]},
        {"word": [0], "other": [0]},
        {"word": [1]},
    ],
)
def test_invalid_abstract_positions_never_become_invented_text(client, provider, index):
    responses, _ = provider
    responses.append(httpx.Response(200, json={"id": "W123", "abstract_inverted_index": index}))
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == "openalex_invalid_response"


def test_repeated_abstract_words_reconstruct_only_provider_positions(client, provider):
    responses, _ = provider
    responses.append(
        httpx.Response(
            200,
            json={
                "id": "W123",
                "abstract_inverted_index": {"Synthetic": [0, 2], "fixture": [1]},
            },
        )
    )
    assert client.get("/api/v1/papers/W123").json()["abstract"] == "Synthetic fixture Synthetic"


@pytest.mark.parametrize(
    "exception,code",
    [
        (httpx.DecodingError("Synthetic bad encoding"), "openalex_invalid_response"),
        (httpx.TooManyRedirects("Synthetic redirects"), "openalex_error"),
        (httpx.InvalidURL("Synthetic invalid URL"), "openalex_error"),
    ],
)
def test_non_transport_http_errors_are_structured(client, provider, exception, code):
    responses, calls = provider
    responses.append(exception)
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 502
    assert response.json()["error"]["code"] == code
    assert len(calls) == 1
    assert client.get("/api/v1/health").status_code == 200


@pytest.mark.parametrize("endpoint", ["search", "details", "references", "citations", "neighbors"])
def test_keys_are_only_in_backend_provider_authorization_headers(client, provider, endpoint):
    responses, calls = provider
    secret = "synthetic-backend-only-secret"
    client.app.state.settings.openalex_api_key = secret
    seed = {"id": "W123", "referenced_works": ["https://openalex.org/w100"]}
    outgoing = httpx.Response(200, json={"results": [{"id": "https://openalex.org/w100"}]})
    incoming = httpx.Response(
        200, json={"results": [{"id": "W200"}], "meta": {"next_cursor": None}}
    )
    if endpoint == "search":
        path = "/api/v1/papers/search?q=synthetic"
        responses.append(httpx.Response(200, json={"results": [seed], "meta": {"count": 1}}))
    else:
        path = "/api/v1/papers/W123" + ("" if endpoint == "details" else f"/{endpoint}")
        responses.append(httpx.Response(200, json=seed))
        if endpoint in ("references", "neighbors"):
            responses.append(outgoing)
        if endpoint in ("citations", "neighbors"):
            responses.append(incoming)
    response = client.get(path)
    assert response.status_code == 200
    assert secret not in response.text
    for request in calls:
        assert request.headers["Authorization"] == f"Bearer {secret}"
        assert secret not in str(request.url)
        assert "api_key" not in request.url.params
    assert client.app.state.settings.database_url == ""


def test_provider_error_payload_is_not_exposed(client, provider):
    responses, _ = provider
    responses.append(httpx.Response(403, json={"message": "synthetic-secret-and-internal-details"}))
    response = client.get("/api/v1/papers/W123")
    assert response.status_code == 502
    assert "synthetic-secret" not in response.text


def test_unexpected_failure_is_generic_and_app_remains_healthy(tmp_path):
    settings = Settings(_env_file=None, database_url="", model_artifact_dir=tmp_path)
    with TestClient(create_app(settings), raise_server_exceptions=False) as client:

        async def handler(request):
            raise RuntimeError("Synthetic private diagnostic detail")

        upstream = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        client.app.state.http = upstream
        try:
            response = client.get("/api/v1/papers/W123")
            assert response.status_code == 500
            assert response.json() == {
                "error": {
                    "code": "internal_error",
                    "message": "An internal server error occurred",
                }
            }
            assert client.get("/api/v1/health").status_code == 200
        finally:
            asyncio.run(upstream.aclose())
