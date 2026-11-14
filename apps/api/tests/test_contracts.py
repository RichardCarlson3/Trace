import pytest
from pydantic import ValidationError

from app.schemas.contracts import Citation, Graph, Paper


def test_paper_normalization_and_nullable_fields():
    paper = Paper(id="https://openalex.org/W123", title="Test fixture")
    assert paper.id == "W123"
    assert paper.year is None
    assert paper.abstract is None


def test_citation_direction_is_preserved():
    # Fixture W200 cites fixture W100. The arrow must remain W200 -> W100.
    citation = Citation(id="W200->W100", source="https://openalex.org/W200", target="W100")
    assert citation.source == "W200"
    assert citation.target == "W100"
    assert citation.intent is None
    assert citation.confidence is None


@pytest.mark.parametrize(
    "values",
    [
        {"intent": "method", "confidence": 0.8},
        {"confidence": 0.8},
        {"intent": "result", "confidence": 1.1, "context_text": "Actual passage"},
        {"intent": "result", "confidence": 0.9, "context_text": " "},
    ],
)
def test_citation_evidence_validation(values):
    with pytest.raises(ValidationError):
        Citation(id="test", source="W200", target="W100", **values)


def test_graph_requires_existing_endpoints():
    with pytest.raises(ValidationError):
        Graph(papers=[], citations=[Citation(id="test", source="W200", target="W100")])


def test_reject_invalid_work_ids():
    with pytest.raises(ValidationError):
        Paper(id="not-an-openalex-id", title="Test fixture")
