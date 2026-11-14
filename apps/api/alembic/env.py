from sqlalchemy import create_engine, pool

from alembic import context
from app.core.config import get_settings
from app.db.models import Base

target_metadata = Base.metadata
url = get_settings().database_url
if not url:
    raise RuntimeError("Set DATABASE_URL in apps/api/.env before running migrations")
if not url.startswith("postgresql+psycopg://"):
    raise RuntimeError("DATABASE_URL must use the postgresql+psycopg driver")

if context.is_offline_mode():
    context.configure(url=url, target_metadata=target_metadata, literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()
else:
    engine = create_engine(url, poolclass=pool.NullPool, connect_args={"connect_timeout": 10})
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
