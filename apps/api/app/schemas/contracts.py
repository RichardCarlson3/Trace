import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Intent = Literal["background", "method", "result"]


def normalize_work_id(value: str) -> str:
    work_id = value.removeprefix("https://openalex.org/").removeprefix("http://openalex.org/")
    if not re.fullmatch(r"W\d+", work_id):
        raise ValueError("Expected an OpenAlex work ID such as W2741809807")
    return work_id


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Paper(Contract):
    id: str
    doi: str | None = None
    title: str
    year: int | None = None
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    cited_by_count: int = Field(default=0, ge=0)
    landing_page_url: str | None = None

    _normalize_id = field_validator("id")(normalize_work_id)


class PaperDetails(Paper):
    publication_venue: str | None = None
    reference_count: int | None = Field(default=None, ge=0)


class Citation(Contract):
    """source is the citing work, target is the cited work. B cites A means B -> A."""

    id: str
    source: str
    target: str
    intent: Intent | None = None
    confidence: float | None = Field(default=None, ge=0, le=1)
    context_text: str | None = Field(default=None, min_length=1)
    context_source_url: str | None = None

    _normalize_ids = field_validator("source", "target")(normalize_work_id)

    @model_validator(mode="after")
    def require_evidence(self):
        if self.intent is not None and not (self.context_text and self.context_text.strip()):
            raise ValueError("Citation intent requires actual citation-context text")
        if self.intent is None and self.confidence is not None:
            raise ValueError("An unclassified citation must have null confidence")
        if self.intent is not None and self.confidence is None:
            raise ValueError("A classified citation requires confidence")
        return self


class Graph(Contract):
    papers: list[Paper] = Field(default_factory=list)
    citations: list[Citation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_endpoints(self):
        ids = {paper.id for paper in self.papers}
        if len(ids) != len(self.papers):
            raise ValueError("Graph paper IDs must be unique")
        if any(edge.source not in ids or edge.target not in ids for edge in self.citations):
            raise ValueError("Citation endpoints must reference graph papers")
        return self


class RelationshipResponse(Graph):
    seed_paper_id: str
    has_more: bool = False

    _normalize_seed = field_validator("seed_paper_id")(normalize_work_id)


class ReferenceResponse(RelationshipResponse):
    next_offset: int | None = Field(default=None, ge=0)
    unresolved_reference_ids: list[str] = Field(default_factory=list)


class IncomingCitationResponse(RelationshipResponse):
    next_cursor: str | None = None
    skipped_record_count: int = Field(default=0, ge=0)


class NeighborResponse(RelationshipResponse):
    next_cursor: str | None = None
    unresolved_reference_ids: list[str] = Field(default_factory=list)
    skipped_record_count: int = Field(default=0, ge=0)


class SearchResponse(Contract):
    papers: list[Paper]
    total: int = Field(ge=0)
    page: int = Field(ge=1)
    per_page: int = Field(ge=1, le=25)


class ClassifyRequest(Contract):
    context_text: str = Field(strict=True, min_length=1, max_length=20000)
    context_source_url: str | None = None

    @field_validator("context_text")
    @classmethod
    def nonblank_context(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("A citation passage is required")
        return value


class Classification(Contract):
    intent: Intent
    confidence: float = Field(
        ge=0,
        le=1,
        allow_inf_nan=False,
        description="Uncalibrated predict_proba score for the selected intent",
    )
    model_version: str = Field(
        min_length=1, description="Version recorded in the loaded model metadata"
    )


class SaveGraphRequest(Contract):
    name: str = Field(min_length=1, max_length=200)
    seed_paper_id: str
    graph: Graph
    positions: dict[str, dict[str, float]] = Field(default_factory=dict)
    expanded_nodes: list[str] = Field(default_factory=list)
    settings: dict = Field(default_factory=dict)
    filters: dict = Field(default_factory=dict)

    _normalize_seed = field_validator("seed_paper_id")(normalize_work_id)
