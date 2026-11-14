"""Contracts for one directed OpenAlex citation relationship."""

from datetime import datetime
from typing import Literal

from pydantic import Field, computed_field, field_validator

from app.schemas.contracts import Classification, Contract, normalize_work_id


class CitationPair(Contract):
    citing_paper_id: str = Field(strict=True)
    cited_paper_id: str = Field(strict=True)

    _normalize_ids = field_validator("citing_paper_id", "cited_paper_id")(normalize_work_id)


class PaperMapping(Contract):
    openalex_id: str
    title: str | None = None
    doi: str | None = None
    semantic_scholar_paper_id: str | None = None
    verified: bool = False
    reason: str | None = None


class CitationContextRequest(CitationPair):
    mode: Literal["auto", "live", "examples"] = "auto"


class CitationPassage(Contract):
    context_text: str = Field(strict=True, min_length=1)
    source: Literal["semantic_scholar", "openalex_tei"] = "semantic_scholar"
    source_url: str
    source_url_scope: Literal["paper", "document"] = "paper"
    bibliography_id: str | None = None
    bibliography_text: str | None = None
    citation_marker: str | None = None
    citation_targets: list[str] | None = None
    section: list[str] | None = None
    document_sha256: str | None = None
    retrieved_at: datetime | None = None
    identity_evidence: list[str] | None = None
    document_identity_method: str | None = None
    classification: Classification | None = None
    classification_unavailable_reason: Literal["context_too_long"] | None = None

    @field_validator("context_text")
    @classmethod
    def nonblank_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A genuine nonblank citation passage is required")
        return value


class CitationContexts(CitationPair):
    status: Literal[
        "available",
        "no_context",
        "relationship_not_found",
        "unresolved_identifiers",
        "incomplete",
        "provider_unavailable",
        "example_not_found",
    ]
    source: Literal["semantic_scholar", "openalex_tei"] = "semantic_scholar"
    fallback_reason: str | None = None
    origin: Literal["live", "memory_cache", "verified_example", "unavailable"] = "live"
    retrieved_at: datetime | None = None
    evidence_urls: list[str] = Field(default_factory=list)
    observed_context_count: int | None = Field(default=None, ge=0)
    citing_mapping: PaperMapping
    cited_mapping: PaperMapping
    relationship_found: bool | None = None
    reference_scan_complete: bool = False
    reason: str | None = None
    contexts: list[CitationPassage] = Field(default_factory=list)

    @computed_field
    @property
    def available(self) -> bool:
        return bool(self.contexts)
