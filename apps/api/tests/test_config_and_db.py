import pytest
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateTable

from app.core.config import API_ROOT, Settings
from app.core.errors import ServiceError
from app.db import session
from app.db.models import SavedGraph


def test_dotenv_and_artifacts_are_anchored(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    assert Settings.model_config["env_file"] == API_ROOT / ".env"
    assert (
        Settings(_env_file=None, model_artifact_dir="").model_artifact_dir == API_ROOT / "artifacts"
    )
    assert (
        Settings(_env_file=None, model_artifact_dir="models").model_artifact_dir
        == API_ROOT / "models"
    )


def test_database_is_lazy_and_optional(monkeypatch):
    monkeypatch.setattr(session, "get_settings", lambda: Settings(_env_file=None, database_url=""))
    session.get_engine.cache_clear()
    with pytest.raises(ServiceError) as error:
        session.get_engine()
    assert error.value.status_code == 503


def test_saved_graph_postgres_schema():
    sql = str(CreateTable(SavedGraph.__table__).compile(dialect=postgresql.dialect()))
    assert "JSONB" in sql
    assert "UUID" in sql
    assert "TIMESTAMP WITH TIME ZONE" in sql
