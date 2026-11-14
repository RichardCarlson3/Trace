from typing import Annotated

from fastapi import APIRouter, Path, Query, Request

from app.core.errors import ServiceError
from app.schemas.contracts import (
    Graph,
    IncomingCitationResponse,
    PaperDetails,
    ReferenceResponse,
    SearchResponse,
)
from app.services.openalex import OpenAlexService

router = APIRouter(prefix="/papers", tags=["papers"])
WorkID = Annotated[str, Path(pattern=r"^W\d+$")]


@router.get("/search", response_model=SearchResponse)
async def search(
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=300)],
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=25)] = 10,
):
    if not q.strip():
        raise ServiceError(422, "validation_error", "Search query must contain text")
    service = OpenAlexService(request.app.state.http, request.app.state.settings)
    return await service.search(q.strip(), page, per_page)


@router.get("/{id}/references", response_model=ReferenceResponse)
async def references(
    id: WorkID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    offset: Annotated[int, Query(ge=0)] = 0,
):
    service = OpenAlexService(request.app.state.http, request.app.state.settings)
    return await service.references(id, limit=limit, offset=offset)


@router.get("/{id}/citations", response_model=IncomingCitationResponse)
async def citations(
    id: WorkID,
    request: Request,
    limit: Annotated[int, Query(ge=1, le=50)] = 10,
    cursor: Annotated[str, Query(min_length=1, max_length=2048, pattern=r"^\S+$")] = "*",
):
    service = OpenAlexService(request.app.state.http, request.app.state.settings)
    return await service.citations(id, limit=limit, cursor=cursor)


@router.get("/{id}/neighbors", response_model=Graph)
def neighbors(id: WorkID):
    raise ServiceError(501, "not_implemented", "Citation expansion is planned")


@router.get("/{id}", response_model=PaperDetails)
async def details(id: WorkID, request: Request):
    service = OpenAlexService(request.app.state.http, request.app.state.settings)
    return await service.details(id)
