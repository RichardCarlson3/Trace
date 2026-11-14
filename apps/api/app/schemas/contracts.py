import re
from typing import Literal
from urllib.parse import quote, unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Intent = Literal["background", "method", "result"]


def normalize_work_id(value: str) -> str:
    match = (
        re.fullmatch(r"(?:https?://openalex\.org/)?w([0-9]+)", value.strip(), re.IGNORECASE)
        if isinstance(value, str)
        else None
    )
    if not match:
        raise ValueError("Expected an OpenAlex work ID such as W2741809807")
    return f"W{match[1]}"


def normalize_doi(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected a DOI string or null")
    doi = value.strip()
    if not doi:
        return None
    if re.match(r"https?://", doi, re.IGNORECASE):
        url = urlsplit(doi)
        if url.netloc.lower() not in ("doi.org", "dx.doi.org") or url.query or url.fragment:
            raise ValueError("Expected a DOI resolver URL without query or fragment")
        doi = unquote(url.path.removeprefix("/"), errors="strict")
    else:
        doi = re.sub(r"^doi:\s*", "", doi, flags=re.IGNORECASE)
    if not re.fullmatch(r"10\.[0-9]+(?:\.[0-9]+)*/\S+", doi) or any(
        ord(char) < 32 or ord(char) == 127 for char in doi
    ):
        raise ValueError("Expected a DOI such as 10.1000/example")
    # DOI comparisons use ASCII case folding; preserve non-ASCII identifier characters.
    doi = doi.translate(str.maketrans("ABCDEFGHIJKLMNOPQRSTUVWXYZ", "abcdefghijklmnopqrstuvwxyz"))
    return "https://doi.org/" + quote(doi, safe="/:;()+,=._-~!$&'@")


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Expected a string or null")
    return value.strip() or None


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
    _normalize_doi = field_validator("doi", mode="before")(normalize_doi)
    _normalize_landing_page = field_validator("landing_page_url", mode="before")(
        normalize_optional_text
    )


class PaperDetails(Paper):
    publication_venue: str | None = None
    reference_count: int | None = Field(default=None, ge=0)

    _normalize_venue = field_validator("publication_venue", mode="before")(normalize_optional_text)


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
        if len({(edge.source, edge.target) for edge in self.citations}) != len(self.citations):
            raise ValueError("Graph directed citation pairs must be unique")
        if len({edge.id for edge in self.citations}) != len(self.citations):
            raise ValueError("Graph citation IDs must be unique")
        return self


class RelationshipResponse(Graph):
    seed_paper_id: str
    has_more: bool = False

    _normalize_seed = field_validator("seed_paper_id")(normalize_work_id)

    @model_validator(mode="after")
    def validate_seed(self):
        if self.seed_paper_id not in {paper.id for paper in self.papers}:
            raise ValueError("Relationship responses must include the seed paper")
        if any(self.seed_paper_id not in (edge.source, edge.target) for edge in self.citations):
            raise ValueError("Every relationship must include the seed paper")
        return self


class ReferenceResponse(RelationshipResponse):
    next_offset: int | None = Field(default=None, ge=0)
    unresolved_reference_ids: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_direction(self):
        if any(edge.source != self.seed_paper_id for edge in self.citations):
            raise ValueError("Reference edges must run from the seed to the cited paper")
        return self


class IncomingCitationResponse(RelationshipResponse):
    next_cursor: str | None = None
    skipped_record_count: int = Field(default=0, ge=0)

    @model_validator(mode="after")
    def validate_direction(self):
        if any(edge.target != self.seed_paper_id for edge in self.citations):
            raise ValueError("Incoming edges must run from the citing paper to the seed")
        return self


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
