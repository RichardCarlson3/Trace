from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.errors import ServiceError


@lru_cache
def get_engine():
    url = get_settings().database_url
    if not url:
        raise ServiceError(503, "database_unavailable", "DATABASE_URL is not configured")
    if not url.startswith("postgresql+psycopg://"):
        raise ServiceError(503, "database_unavailable", "Use a postgresql+psycopg connection URL")
    return create_engine(url, pool_pre_ping=True, connect_args={"connect_timeout": 10})


def get_session():
    """Use after authenticated ownership is implemented. Engine creation is lazy."""
    with Session(get_engine()) as session:
        yield session
