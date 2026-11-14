from typing import Annotated

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from app.schemas.citation_contexts import CitationContextRequest, CitationContexts, CitationPair
from app.services.citation_contexts import classify_contexts

router = APIRouter(
    prefix="/citation-contexts",
    tags=["citation contexts"],
    responses={
        502: {"description": "Live source transport or response failure"},
        503: {"description": "Live provider or classification model unavailable"},
    },
)


@router.get("", response_model=CitationContexts)
async def retrieve_contexts(query: Annotated[CitationContextRequest, Query()], request: Request):
    """Retrieve passages for citing_paper_id -> cited_paper_id using verified DOI mappings."""
    pair = CitationPair(citing_paper_id=query.citing_paper_id, cited_paper_id=query.cited_paper_id)
    return await request.app.state.citation_contexts.retrieve(pair, mode=query.mode)


@router.post("/classify", response_model=CitationContexts)
async def classify_pair(body: CitationContextRequest, request: Request):
    """Retrieve genuine passages and classify each through the existing inference service."""
    pair = CitationPair(citing_paper_id=body.citing_paper_id, cited_paper_id=body.cited_paper_id)
    result = await request.app.state.citation_contexts.retrieve(pair, mode=body.mode)
    return await run_in_threadpool(classify_contexts, result, request.app.state.inference)
