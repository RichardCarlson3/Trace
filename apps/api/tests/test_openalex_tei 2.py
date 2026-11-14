"""Offline real-document regression and synthetic safety/failure tests."""

import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.citation_contexts import CitationContexts, CitationPair
from app.services import openalex_tei as module
from app.services.citation_contexts import CitationContextService, classify_contexts
from app.services.inference import InferenceService
from app.services.openalex_tei import (
    OpenAlexTEIService,
    TEIUnavailable,
    parse_document,
    safe_sentence,
)

FIXTURES = Path(__file__).parent / "fixtures/tei"
BART = "W2982399380"
TARGET = "W1614298861"
PAIR = CitationPair(citing_paper_id=BART, cited_paper_id=TARGET)


@pytest.fixture
def upstream():
    works = json.loads((FIXTURES / "works.json").read_text(encoding="utf-8"))
    calls = []

    def handler(request):
        calls.append(request)
        assert request.headers["Authorization"] == "Bearer synthetic-oa"
        assert "synthetic-oa" not in str(request.url)
        if request.url.host == "content.openalex.org":
            name = "bart" if BART in request.url.path else "biobert"
            return httpx.Response(200, content=(FIXTURES / f"{name}.xml").read_bytes())
        wid = request.url.path.rsplit("/", 1)[-1]
        return httpx.Response(200, json=works[wid]) if wid in works else httpx.Response(404)

    return works, calls, handler


def config():
    return Settings(_env_file=None, openalex_api_key="synthetic-oa", semantic_scholar_enabled=True)


def test_bart_exact_arxiv_sentence_and_unchanged_real_model(upstream):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream[2])) as client:
            service = OpenAlexTEIService(client, config())
            result, reason = await service.retrieve(PAIR)
            assert reason is None and result.source == "openalex_tei"
            assert result.relationship_found and result.contexts[0].bibliography_id == "b17"
            passage = result.contexts[0]
            assert "1301.3781" in passage.bibliography_text
            assert passage.section == ["Introduction"] and "b20" in passage.citation_targets
            assert passage.document_identity_method == "authenticated_provider_binding"
            assert passage.identity_evidence == ["ARXIV:1301.3781"]
            classified = classify_contexts(result, InferenceService(config().model_artifact_dir))
            assert classified.contexts[0].classification.intent == "background"
            assert classified.contexts[0].classification.confidence == pytest.approx(
                0.8843842684202584
            )
            count = len(upstream[1])
            again, _ = await service.retrieve(PAIR)
            assert again.origin == "memory_cache" and again.retrieved_at == result.retrieved_at
            assert len(upstream[1]) == count
            CitationContexts.model_validate(classified.model_dump(exclude_computed_fields=True))

    asyncio.run(run())


def test_all_eleven_recorded_pairs_and_shared_downloads(upstream):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream[2])) as client:
            service = OpenAlexTEIService(client, config())
            pairs = [
                CitationPair(citing_paper_id=wid, cited_paper_id=ref.split("/")[-1])
                for wid in [BART, "W2911489562"]
                for ref in upstream[0][wid]["referenced_works"]
            ]
            results = await asyncio.gather(*(service.retrieve(pair) for pair in pairs))
            assert sum(r is not None for r, _ in results) == 1
            assert sum(c.url.host == "content.openalex.org" for c in upstream[1]) == 2
            assert sum(reason == "tei_bibliography_not_verified" for _, reason in results) == 10

    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 403, 404, 429, 500, 503])
def test_content_errors_are_not_retried_and_are_negatively_cached(upstream, status):
    calls = []

    def handler(request):
        if request.url.host == "content.openalex.org":
            calls.append(request)
            return httpx.Response(status, headers={"Retry-After": "600"})
        return upstream[2](request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexTEIService(client, config())
            for _ in range(2):
                result, reason = await service.retrieve(PAIR)
                assert result is None and reason == f"openalex_tei_http_{status}"
            assert len(calls) == 1
            if status in [401, 403, 429]:
                assert service._blocked_until > module.time.monotonic() + 590

    asyncio.run(run())


@pytest.mark.parametrize(
    "data",
    [
        b"<TEI>",
        b'<!DOCTYPE TEI [<!ENTITY x SYSTEM "file:///secret">]><TEI>&x;</TEI>',
        b'<!DOCTYPE TEI SYSTEM "https://evil.test/a"><TEI/>',
    ],
)
def test_invalid_xml_and_entities_are_rejected(upstream, data):
    with pytest.raises(TEIUnavailable):
        parse_document(data, upstream[0][BART])


def test_document_size_depth_and_header_identity_limits(upstream, monkeypatch):
    with pytest.raises(TEIUnavailable, match="too_large"):
        parse_document(b"x" * (module.MAX_XML_BYTES + 1), upstream[0][BART])
    data = (FIXTURES / "bart.xml").read_bytes()
    altered = data.replace(
        b'<idno type="MD5">', b'<idno type="DOI">10.1000/wrong</idno><idno type="MD5">', 1
    )
    with pytest.raises(TEIUnavailable, match="identity_mismatch"):
        parse_document(altered, upstream[0][BART])
    with pytest.raises(TEIUnavailable, match="header_missing"):
        parse_document(b"<TEI><text><body/></text></TEI>", upstream[0][BART])
    monkeypatch.setattr(module, "MAX_NODES", 1)
    with pytest.raises(TEIUnavailable, match="structure_limit"):
        parse_document(data, upstream[0][BART])


@pytest.mark.parametrize(
    "text",
    [
        "Entity type Number of relations GAD (Bravo et al., 2015) Gene-disease 5330 "
        "EU-ADR 355 CHEMPROT 10 031.",
        "79 842 BC2GM (Smith et al., 2008) Gene/Protein 20 703 "
        "JNLPBA (Kim et al., 2004) Gene/Protein 35 460.",
        "This is not a complete citation passage",
        "x" * 20001,
    ],
)
def test_table_fragments_and_unsafe_passages_are_rejected(text):
    assert not safe_sentence(text)


def test_biobert_header_doi_and_real_table_fragments(upstream):
    document = parse_document((FIXTURES / "biobert.xml").read_bytes(), upstream[0]["W2911489562"])
    assert document.identity_method == "header_identifier_and_provider_binding"
    for sentence in document.sentences:
        assert not {"b2", "b8", "b19", "b30"} & {t for ids, _ in sentence.markers for t in ids}


def test_relationship_is_required_before_any_content_request(upstream):
    upstream[0][BART]["referenced_works"] = []

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream[2])) as client:
            result, reason = await OpenAlexTEIService(client, config()).retrieve(PAIR)
            assert result is None and reason == "openalex_relationship_not_verified"
            assert len(upstream[1]) == 1

    asyncio.run(run())


def test_missing_key_and_disabled_fallback_do_not_request(upstream):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream[2])) as client:
            service = OpenAlexTEIService(client, Settings(_env_file=None))
            assert (await service.retrieve(PAIR))[1] == "openalex_key_missing"
            service.settings.openalex_tei_enabled = False
            assert (await service.retrieve(PAIR))[1] == "openalex_tei_disabled"
            assert not upstream[1]

    asyncio.run(run())


def test_timeout_is_bounded(upstream, monkeypatch):
    async def handler(request):
        await asyncio.Event().wait()

    monkeypatch.setattr(module, "FALLBACK_TIMEOUT", 0.01)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            assert (await OpenAlexTEIService(client, config()).retrieve(PAIR))[
                1
            ] == "openalex_tei_timeout"

    asyncio.run(run())


def test_classification_endpoint_automatic_fallback_and_primary_success(client, upstream):
    transport = httpx.AsyncClient(transport=httpx.MockTransport(upstream[2]))
    service = CitationContextService(transport, config())
    service._retrieve_live = AsyncMock(
        side_effect=ServiceError(503, "semantic_scholar_rate_limited", "busy")
    )
    client.app.state.citation_contexts = service
    client.app.state.inference = InferenceService(config().model_artifact_dir)
    result = client.post(
        "/api/v1/citation-contexts/classify", json={**PAIR.model_dump(), "mode": "live"}
    )
    assert result.status_code == 200
    body = result.json()
    assert (
        body["source"] == "openalex_tei"
        and body["contexts"][0]["classification"]["intent"] == "background"
    )
    assert body["contexts"][0]["source_url_scope"] == "document"
    count = len(upstream[1])
    assert (
        client.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump()).status_code == 200
    )
    assert len(upstream[1]) == count
    # A verified primary passage returns immediately without TEI.
    body["source"] = "semantic_scholar"
    body.pop("available")
    primary = CitationContexts.model_validate(body)
    service.retrieve = AsyncMock(return_value=primary)
    service.tei.retrieve = AsyncMock(side_effect=AssertionError("Unnecessary fallback"))
    assert (
        client.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump()).status_code == 200
    )
    asyncio.run(transport.aclose())


def test_both_providers_fail_truthfully(client, upstream):
    upstream[0][BART]["has_content"] = {"grobid_xml": False}
    transport = httpx.AsyncClient(transport=httpx.MockTransport(upstream[2]))
    service = CitationContextService(transport, config())
    service._retrieve_live = AsyncMock(
        side_effect=ServiceError(503, "semantic_scholar_rate_limited", "busy")
    )
    client.app.state.citation_contexts = service
    result = client.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump())
    assert result.status_code == 200
    body = result.json()
    assert not body["available"] and body["relationship_found"] is None
    assert body["reason"] == "semantic_scholar_rate_limited"
    assert body["fallback_reason"] == "openalex_tei_content_unavailable"
    asyncio.run(transport.aclose())


def synthetic_xml(identifier='<idno type="DOI">10.1000/target</idno>', section="Introduction"):
    # Intentionally synthetic minimal document for parser/identity failure cases.
    return f"""<TEI><teiHeader/><text><body><div><head>{section}</head><p><s>
    We apply the documented technique in these experiments <ref type="bibr" target="#b0">[1]</ref>.
    </s></p></div></body><back><listBibl><biblStruct xml:id="b0">{identifier}</biblStruct>
    </listBibl></back></text></TEI>""".encode()


@pytest.mark.parametrize(
    "variant,expected",
    [
        ("doi", None),
        ("wrong", "tei_bibliography_not_verified"),
        ("conflict", "tei_conflicting_bibliography_identifier"),
        ("duplicate", "tei_ambiguous_bibliography"),
        ("abstract", "tei_no_safe_body_sentence"),
        ("figure", "tei_no_safe_body_sentence"),
        ("unlinked", "tei_no_safe_body_sentence"),
        ("redirect", "openalex_tei_http_302"),
    ],
)
def test_exact_doi_and_rejected_variants(upstream, variant, expected):
    upstream[0][TARGET].update(doi="10.1000/target", ids={}, locations=[])
    data = synthetic_xml()
    if variant == "wrong":
        data = synthetic_xml('<idno type="DOI">10.1000/wrong</idno>')
    if variant == "conflict":
        data = synthetic_xml(
            '<idno type="DOI">10.1000/target</idno><idno type="DOI">10.1000/wrong</idno>'
        )
    if variant == "duplicate":
        data = data.replace(
            b"</listBibl>",
            b'<biblStruct xml:id="b1"><idno type="DOI">10.1000/target</idno>'
            b"</biblStruct></listBibl>",
        )
    if variant == "abstract":
        data = synthetic_xml(section="Abstract")
    if variant == "figure":
        data = data.replace(b"<p>", b"<figure><p>").replace(b"</p>", b"</p></figure>")
    if variant == "unlinked":
        data = data.replace(b'target="#b0"', b'target="#missing"')

    def handler(request):
        if request.url.host == "content.openalex.org":
            return (
                httpx.Response(302, headers={"Location": "https://evil.test/a"})
                if variant == "redirect"
                else httpx.Response(200, content=data)
            )
        return upstream[2](request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result, reason = await OpenAlexTEIService(client, config()).retrieve(PAIR)
            assert reason == expected
            assert (result is not None) == (expected is None)

    asyncio.run(run())


def test_streaming_size_limit_and_positive_ttl_refresh(upstream, monkeypatch):
    monkeypatch.setattr(module, "MAX_XML_BYTES", 10)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream[2])) as client:
            result, reason = await OpenAlexTEIService(client, config()).retrieve(PAIR)
            assert result is None and reason == "tei_document_too_large"

    asyncio.run(run())


def test_positive_document_expiry_refreshes_only_xml(upstream):
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(upstream[2])) as client:
            service = OpenAlexTEIService(client, config())
            await service.retrieve(PAIR)
            expiry, doc = service._documents._values[BART]
            service._documents._values[BART] = (0, doc)
            calls = len(upstream[1])
            await service.retrieve(PAIR)
            assert len(upstream[1]) == calls + 1

    asyncio.run(run())


@pytest.mark.parametrize("status", [401, 403, 404, 429, 503])
def test_metadata_access_failures_and_global_cooldown(status):
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(status)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexTEIService(client, config())
            assert (await service.retrieve(PAIR))[1] == f"openalex_tei_http_{status}"
            assert (await service.retrieve(PAIR))[1] == f"openalex_tei_http_{status}"
            assert len(calls) == 1
            if status in (401, 403, 429):
                other = CitationPair(citing_paper_id="W123", cited_paper_id=TARGET)
                assert (await service.retrieve(other))[1] == "openalex_tei_cooldown"
                assert len(calls) == 1

    asyncio.run(run())


def test_semantic_scholar_no_context_and_unresolved_results_fall_back(client, upstream):
    transport = httpx.AsyncClient(transport=httpx.MockTransport(upstream[2]))
    service = CitationContextService(transport, config())
    client.app.state.citation_contexts = service
    client.app.state.inference = InferenceService(config().model_artifact_dir)
    for status in ("no_context", "unresolved_identifiers"):
        primary = service._unavailable(PAIR, status, "fixture_primary_unavailable")
        service.retrieve = AsyncMock(return_value=primary)
        response = client.post("/api/v1/citation-contexts/classify", json=PAIR.model_dump())
        assert response.status_code == 200 and response.json()["source"] == "openalex_tei"
    asyncio.run(transport.aclose())


@pytest.mark.parametrize("kind,value", [("PMID", "1234"), ("PMCID", "PMC1234"), ("MAG", "1234")])
def test_other_exact_bibliography_identifier_namespaces(upstream, kind, value):
    upstream[0][TARGET].update(doi=None, ids={kind.lower(): value}, locations=[])
    data = synthetic_xml(f'<idno type="{kind}">{value}</idno>')

    def handler(request):
        return (
            httpx.Response(200, content=data)
            if request.url.host == "content.openalex.org"
            else upstream[2](request)
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result, reason = await OpenAlexTEIService(client, config()).retrieve(PAIR)
            assert reason is None and result.available

    asyncio.run(run())


def test_transport_failure_is_cached_per_document(upstream):
    calls = []

    def handler(request):
        if request.url.host == "content.openalex.org":
            calls.append(request)
            raise httpx.ReadTimeout("private transport diagnostic", request=request)
        return upstream[2](request)

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            service = OpenAlexTEIService(client, config())
            for _ in range(2):
                assert (await service.retrieve(PAIR))[1] == "openalex_tei_transport_error"
            assert len(calls) == 1

    asyncio.run(run())


def test_depth_limit_is_checked_during_parse(upstream):
    data = b"<TEI>" + b"<div>" * 65 + b"</div>" * 65 + b"</TEI>"
    with pytest.raises(TEIUnavailable, match="structure_limit"):
        parse_document(data, upstream[0][BART])


def test_selected_passage_count_is_bounded(upstream):
    upstream[0][TARGET].update(doi="10.1000/target", ids={}, locations=[])
    data = synthetic_xml()
    sentence = data[data.index(b"<s>") : data.index(b"</s>") + 4]
    data = data.replace(
        sentence,
        b"".join(
            sentence.replace(b"documented", f"documented variant {i}".encode()) for i in range(6)
        ),
    )

    def handler(request):
        return (
            httpx.Response(200, content=data)
            if request.url.host == "content.openalex.org"
            else upstream[2](request)
        )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            result, reason = await OpenAlexTEIService(client, config()).retrieve(PAIR)
            assert reason is None and len(result.contexts) == module.MAX_PASSAGES

    asyncio.run(run())
