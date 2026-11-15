import logging
from typing import Annotated

from fastapi import APIRouter, Query, Request
from starlette.concurrency import run_in_threadpool

from app.core.errors import ServiceError
from app.schemas.citation_contexts import CitationContextRequest, CitationContexts, CitationPair
from app.services.citation_contexts import classify_contexts, evidence_outcome
from app.services.citation_timing import timed

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/citation-contexts",
    tags=["citation contexts"],
    responses={
        502: {"description": "Live source transport or response failure"},
        503: {"description": "Live provider or classification model unavailable"},
    },
)


def log_outcome(result: CitationContexts, outcome: str) -> None:
    # Identifiers and fixed codes only; passages and provider bodies are never logged.
    logger.info(
        "citation_evidence_outcome citing=%s cited=%s outcome=%s status=%s source=%s "
        "origin=%s reason=%s fallback_reason=%s passages=%d classified=%d",
        result.citing_paper_id,
        result.cited_paper_id,
        outcome,
        result.status,
        result.source,
        result.origin,
        result.reason,
        result.fallback_reason,
        len(result.contexts),
        sum(1 for context in result.contexts if context.classification),
    )


@router.get("", response_model=CitationContexts)
async def retrieve_contexts(query: Annotated[CitationContextRequest, Query()], request: Request):
    """Retrieve passages for citing_paper_id -> cited_paper_id using verified DOI mappings."""
    pair = CitationPair(citing_paper_id=query.citing_paper_id, cited_paper_id=query.cited_paper_id)
    return await request.app.state.citation_contexts.retrieve(pair, mode=query.mode)


@router.post("/classify", response_model=CitationContexts)
@timed("classification_total")
async def classify_pair(body: CitationContextRequest, request: Request):
    """Classify verified passages, trying Semantic Scholar then exact-identity OpenAlex TEI."""
    pair = CitationPair(citing_paper_id=body.citing_paper_id, cited_paper_id=body.cited_paper_id)
    result = await request.app.state.citation_contexts.retrieve_for_classification(
        pair, mode=body.mode
    )
    try:
        classified = await run_in_threadpool(classify_contexts, result, request.app.state.inference)
    except ServiceError:
        # Passages were found but the model could not label them.
        log_outcome(
            result, "classification_failed" if result.contexts else evidence_outcome(result)
        )
        raise
    log_outcome(classified, evidence_outcome(classified))
    return classified
