from uuid import UUID

from fastapi import APIRouter

from app.core.errors import ServiceError
from app.schemas.contracts import SaveGraphRequest

router = APIRouter(prefix="/graphs", tags=["graphs"])


def unavailable():
    raise ServiceError(
        501, "not_implemented", "Graph persistence requires an ownership/authentication design"
    )


@router.post("")
def save_graph(body: SaveGraphRequest):
    unavailable()


@router.get("")
def list_graphs():
    unavailable()


@router.get("/{id}")
def load_graph(id: UUID):
    unavailable()
