"""Synthetic exact-identity fixtures; no network or title-based matches."""

import asyncio

import httpx
import pytest
from test_citation_contexts import (
    CITING,
    settings,
)
from test_citation_contexts import provider as provider

from app.core.errors import ServiceError
from app.schemas.citation_contexts import CitationPair
from app.services.citation_contexts import CitationContextService
from app.services.citation_identifiers import normalize_doi, normalize_identifier, work_identifiers


@pytest.mark.parametrize(
    "raw,expected",
    [
        (" DOI:10.1234/Foo(Bar);X ", "10.1234/foo(bar);x"),
        ("https://DOI.org/10.1234%2FA%252FB", "10.1234/a%2fb"),
        ("10.1234/ÄABC", "10.1234/Äabc"),
        ("https://doi.org/10.1234/a%23b", "10.1234/a#b"),
    ],
)
def test_doi_preserves_meaningful_characters(raw, expected):
    assert normalize_doi(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://doi.org//10.1234/foo",
        "https://user@doi.org/10.1234/foo",
        "https://doi.org/10.1234/%ZZ",
        "https://doi.org/10.1234/%FF",
        "10.1234/a\x00b",
        "https://doi.org.evil.test/10.1234/foo",
        "10.1234/a b",
    ],
)
def test_invalid_doi_does_not_become_an_identity(raw):
    with pytest.raises(ValueError):
        normalize_doi(raw)


@pytest.mark.parametrize(
    "kind,raw,expected",
    [
        ("ARXIV", "https://arxiv.org/pdf/1910.13461v2.pdf", "1910.13461"),
        ("ARXIV", "hep-th/9901001v1", "hep-th/9901001"),
        # GROBID's copy of the arXiv PDF side-stamp (recorded Skip-Thought header).
        ("ARXIV", "arXiv:1506.06726v1[cs.CL]", "1506.06726"),
        ("ARXIV", "arXiv:1810.04805v2 [cs.CL]", "1810.04805"),
        ("ARXIV", "arXiv:1706.03762v5[stat.ML]", "1706.03762"),
        ("ARXIV", "arXiv:cs/0112017v1[cs.LG]", "cs/0112017"),
        ("PMID", "https://pubmed.ncbi.nlm.nih.gov/12345/", "12345"),
        ("PMCID", "https://pmc.ncbi.nlm.nih.gov/articles/PMC12345/", "12345"),
        ("PMCID", "PMC12345", "12345"),
        ("MAG", "12345", "12345"),
    ],
)
def test_supported_exact_identifier_formats(kind, raw, expected):
    assert normalize_identifier(kind, raw) == expected


@pytest.mark.parametrize(
    "raw", ["arXiv:1506.06726v1[cs.CL]extra", "[cs.CL]", "arXiv:15060.6726[cs.CL]"]
)
def test_arxiv_stamp_suffix_does_not_admit_malformed_identifiers(raw):
    with pytest.raises(ValueError):
        normalize_identifier("ARXIV", raw)


@pytest.mark.parametrize(
    "kind,field,value",
    [
        ("ARXIV", "ArXiv", "1910.13461"),
        ("PMID", "PubMed", "12345"),
        ("PMCID", "PubMedCentral", "12345"),
        ("MAG", "MAG", "12345"),
    ],
)
@pytest.mark.parametrize("has_doi", [False, True])
def test_alternative_fallback_and_identity_cache(provider, kind, field, value, has_doi):
    work = provider.works["W100"]
    work["ids"] = {kind.lower(): value}
    work["doi"] = "10.1000/citing" if has_doi else None
    provider.papers.pop("10.1000/citing")  # DOI lookup is a real fixture 404.
    expected = {field: value}

    def alternate(request):
        if f"/paper/{kind}:" in request.url.path:
            return httpx.Response(200, json={"paperId": CITING, "externalIds": expected})

    provider.override = alternate

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            first = await service._map_paper("W100")
            count = len(provider.calls)
            second = await service._map_paper("W100")
            assert first.verified and second.verified
            assert first.semantic_scholar_paper_id == CITING
            assert len(provider.calls) == count

    asyncio.run(run())


@pytest.mark.parametrize(
    "external",
    [
        {"PubMed": "99999"},
        {"DOI": "10.1000/citing"},
        {"PubMed": "12345", "DOI": "10.1000/wrong"},
    ],
)
def test_title_or_conflicting_identifier_never_verifies(provider, external):
    provider.works["W100"]["ids"]["pmid"] = "12345"
    provider.papers.pop("10.1000/citing")
    provider.override = lambda request: (
        httpx.Response(
            200, json={"paperId": CITING, "title": "Citing fixture", "externalIds": external}
        )
        if "/paper/PMID:" in request.url.path
        else None
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            result = await CitationContextService(client, settings())._map_paper("W100")
            assert not result.verified and result.reason == "unverified_alternative_identifier"

    asyncio.run(run())


def test_bart_style_openalex_locations_and_explicit_doi_alias(provider):
    work = provider.works["W100"]
    work["locations"] = [
        {"id": "pmh:oai:arXiv.org:1910.13461", "pdf_url": "https://arxiv.org/pdf/1910.13461v1"},
        {"id": "doi:10.48550/arxiv.1910.13461"},
    ]
    known, aliases = work_identifiers(work)
    assert known["ARXIV"] == "1910.13461" and len(known) == 2
    assert "10.48550/arxiv.1910.13461" in aliases
    provider.papers.pop("10.1000/citing")
    provider.override = lambda request: (
        httpx.Response(
            200,
            json={
                "paperId": CITING,
                "externalIds": {"ArXiv": "1910.13461", "DOI": "10.48550/arxiv.1910.13461"},
            },
        )
        if "/paper/ARXIV:" in request.url.path
        else None
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            assert (await CitationContextService(client, settings())._map_paper("W100")).verified

    asyncio.run(run())


def test_conflicting_location_arxiv_ids_fail_closed():
    with pytest.raises(ValueError, match="ambiguous_arxiv"):
        work_identifiers(
            {
                "locations": [
                    {"id": "pmh:oai:arXiv.org:1910.13461"},
                    {"id": "pmh:oai:arXiv.org:1910.13462"},
                ]
            }
        )


def test_five_namespace_limit_and_negative_mapping_cache(provider):
    provider.works["W100"]["ids"].update(arxiv="1910.13461", pmid="123", pmcid="PMC456", mag="789")
    provider.override = lambda request: (
        httpx.Response(404) if request.url.host == "api.semanticscholar.org" else None
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            service = CitationContextService(client, settings())
            assert not (await service._map_paper("W100")).verified
            assert len(provider.calls) == 6
            await service._map_paper("W100")
            assert len(provider.calls) == 6

    asyncio.run(run())


def test_missing_doi_target_matches_only_verified_hash_not_other_null_dois(provider):
    provider.works["W200"].update(doi=None, ids={"mag": "12345"})
    provider.override = lambda request: (
        httpx.Response(200, json={"paperId": "b" * 40, "externalIds": {"MAG": "12345"}})
        if "/paper/MAG:" in request.url.path
        else None
    )
    provider.pages[0]["data"][0]["citedPaper"]["externalIds"] = {}

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            result = await CitationContextService(client, settings()).retrieve(
                CitationPair(citing_paper_id="W100", cited_paper_id="W200"), mode="live"
            )
            assert result.available and result.cited_mapping.doi is None
            assert len(result.contexts) == 2
            assert all(c.context_text != "Unrelated synthetic context." for c in result.contexts)

    asyncio.run(run())


def test_alternative_lookup_keeps_bounded_rate_limit_retries(provider):
    provider.works["W100"]["ids"]["arxiv"] = "1910.13461"
    provider.papers.pop("10.1000/citing")
    provider.override = lambda request: (
        httpx.Response(429) if "/paper/ARXIV:" in request.url.path else None
    )

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handler)) as client:
            with pytest.raises(ServiceError) as exc:
                await CitationContextService(client, settings())._map_paper("W100")
            assert exc.value.code == "semantic_scholar_rate_limited"
            assert sum("/paper/ARXIV:" in r.url.path for r in provider.calls) == 3

    asyncio.run(run())
