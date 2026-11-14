import pytest


def test_health_without_database_or_model(client):
    assert client.app.state.settings.database_url == ""
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_route_registration(client):
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/api/v1/health",
        "/api/v1/papers/search",
        "/api/v1/papers/{id}",
        "/api/v1/papers/{id}/references",
        "/api/v1/papers/{id}/citations",
        "/api/v1/papers/{id}/neighbors",
        "/api/v1/classify",
        "/api/v1/graphs",
        "/api/v1/graphs/{id}",
    }
    assert expected <= paths.keys()


@pytest.mark.parametrize("path", ["/papers/W123/neighbors", "/graphs"])
def test_planned_routes_are_explicit(client, path):
    response = client.get(f"/api/v1{path}")
    assert response.status_code == 501
    assert response.json()["error"]["code"] == "not_implemented"


def test_graph_write_does_not_pretend_to_save(client):
    response = client.post(
        "/api/v1/graphs",
        json={
            "name": "Test",
            "seed_paper_id": "W123",
            "graph": {"papers": [], "citations": []},
        },
    )
    assert response.status_code == 501


def test_model_unavailable(client):
    response = client.post(
        "/api/v1/classify", json={"context_text": "A real passage supplied by a caller."}
    )
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "model_unavailable"


@pytest.mark.parametrize("text", ["", " "])
def test_classification_requires_context(client, text):
    response = client.post("/api/v1/classify", json={"context_text": text})
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_search_route_normalizes_provider_data(client, mock_provider):
    response = client.get("/api/v1/papers/search", params={"q": "test"})
    assert response.status_code == 200
    paper = response.json()["papers"][0]
    assert paper["id"] == "W123"
    assert paper["abstract"] == "A citation context"
    assert paper["doi"] is None
    assert paper["authors"] == ["Test Author"]


@pytest.mark.parametrize(
    "params", [{"q": ""}, {"q": " "}, {"q": "test", "per_page": 26}, {"q": "test", "page": 0}]
)
def test_search_validation(client, params):
    assert client.get("/api/v1/papers/search", params=params).status_code == 422


def test_cors(client):
    response = client.options(
        "/api/v1/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_consistent_not_found(client):
    response = client.get("/api/v1/missing")
    assert response.status_code == 404
    assert "error" in response.json()
