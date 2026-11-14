import httpx
import pytest
from fastapi.testclient import TestClient

from app.core.config import Settings
from app.main import create_app


@pytest.fixture
def client(tmp_path):
    settings = Settings(_env_file=None, database_url="", model_artifact_dir=tmp_path)
    with TestClient(create_app(settings)) as test_client:
        yield test_client


@pytest.fixture
def openalex_fixture():
    """Synthetic provider fixture, used only in tests."""
    return {
        "meta": {"count": 1},
        "results": [
            {
                "id": "https://openalex.org/W123",
                "display_name": "Synthetic test fixture",
                "publication_year": 2024,
                "doi": None,
                "authorships": [{"author": {"display_name": "Test Author"}}],
                "abstract_inverted_index": {"citation": [1], "A": [0], "context": [2]},
                "cited_by_count": 4,
                "primary_location": None,
            }
        ],
    }


@pytest.fixture
def mock_provider(client, openalex_fixture):
    async def handler(request):
        return httpx.Response(200, json=openalex_fixture)

    provider = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client.app.state.http = provider
    return provider
