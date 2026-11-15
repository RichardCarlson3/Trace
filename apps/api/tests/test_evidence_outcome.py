"""Diagnostic outcome categories for classification responses (synthetic responses)."""

import logging

import pytest

from app.schemas.citation_contexts import CitationContexts, CitationPassage, PaperMapping
from app.schemas.contracts import Classification
from app.services.citation_contexts import evidence_outcome


def response(status, reason=None, fallback=None, contexts=()):
    return CitationContexts(
        citing_paper_id="W1",
        cited_paper_id="W2",
        status=status,
        reason=reason,
        fallback_reason=fallback,
        citing_mapping=PaperMapping(openalex_id="W1", verified=True),
        cited_mapping=PaperMapping(openalex_id="W2", verified=True),
        relationship_found=True if contexts else None,
        contexts=list(contexts),
    )


PASSAGE = CitationPassage(context_text="Synthetic passage [1].", source_url="https://example.org")
CLASSIFIED = PASSAGE.model_copy(
    update={
        "classification": Classification(intent="method", confidence=0.7, model_version="synthetic")
    }
)


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        (response("available", contexts=[CLASSIFIED]), "classified"),
        (response("available", contexts=[PASSAGE]), "classification_failed"),
        # Observed live for Skip-Thought -> Aligning Books (before the TEI fix).
        (
            response(
                "provider_unavailable",
                "semantic_scholar_rate_limited",
                "tei_invalid_xml_or_identifiers",
            ),
            "rate_limited",
        ),
        (response("no_context", fallback="openalex_tei_http_429"), "rate_limited"),
        (response("unresolved_identifiers", fallback="openalex_tei_cooldown"), "rate_limited"),
        (
            response(
                "provider_unavailable",
                "semantic_scholar_unavailable",
                "tei_no_safe_body_sentence",
            ),
            "provider_failed",
        ),
        (
            response("incomplete", "reference_scan_limit", "tei_no_safe_body_sentence"),
            "provider_failed",
        ),
        # Identity failure is reported as such, never as proof of absent context.
        (
            response("unresolved_identifiers", fallback="tei_no_safe_body_sentence"),
            "identifier_resolution_failed",
        ),
        (
            response("no_context", fallback="tei_unrecognized_header_identifier"),
            "identifier_resolution_failed",
        ),
        (
            response("provider_unavailable", "semantic_scholar_disabled", "openalex_tei_disabled"),
            "not_attempted",
        ),
        (response("example_not_found", "no_verified_example"), "not_attempted"),
        (
            response(
                "provider_unavailable",
                "semantic_scholar_references_unavailable",
                "openalex_tei_content_unavailable",
            ),
            "context_unavailable",
        ),
        (response("no_context", fallback="tei_no_safe_body_sentence"), "context_unavailable"),
    ],
)
def test_outcome_categories(result, expected):
    assert evidence_outcome(result) == expected


def test_classify_route_logs_outcome_without_passage_text(client, caplog, monkeypatch):
    service = client.app.state.citation_contexts

    async def retrieve(pair, mode="auto"):
        return response("no_context", fallback="tei_no_safe_body_sentence").model_copy(
            update=pair.model_dump()
        )

    monkeypatch.setattr(service, "retrieve_for_classification", retrieve)
    with caplog.at_level(logging.INFO, logger="app.api.v1.citation_contexts"):
        r = client.post(
            "/api/v1/citation-contexts/classify",
            json={"citing_paper_id": "W10", "cited_paper_id": "W20", "mode": "auto"},
        )
    assert r.status_code == 200
    [line] = [m for m in caplog.messages if m.startswith("citation_evidence_outcome")]
    assert "citing=W10 cited=W20 outcome=context_unavailable" in line
    assert "fallback_reason=tei_no_safe_body_sentence" in line
