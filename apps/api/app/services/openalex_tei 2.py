"""Bounded, exact-identifier OpenAlex TEI fallback for selected citation edges."""

import asyncio
import hashlib
import json
import re
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from urllib.parse import urlsplit
from xml.etree.ElementTree import ParseError

import httpx
from defusedxml.common import DefusedXmlException
from defusedxml.ElementTree import iterparse
from starlette.concurrency import run_in_threadpool

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.citation_contexts import (
    CitationContexts,
    CitationPair,
    CitationPassage,
    PaperMapping,
)
from app.schemas.contracts import normalize_work_id
from app.services.citation_identifiers import normalize_identifier, work_identifiers
from app.services.openalex import retry_after_seconds
from app.services.resource_cache import ResourceCache

MAX_XML_BYTES = 10_000_000
MAX_METADATA_BYTES = 2_000_000
MAX_INDEX_BYTES = 2_000_000
MAX_NODES = 50_000
FALLBACK_TIMEOUT = 30
MAX_PASSAGES = 3
MAX_PASSAGE_CHARS = 20_000
XML_ID = "{http://www.w3.org/XML/1998/namespace}id"


class TEIUnavailable(Exception):
    pass


@dataclass
class Missing:
    reason: str


@dataclass
class Bibliography:
    id: str
    identifiers: set[tuple[str, str]]
    text: str


@dataclass
class Sentence:
    text: str
    markers: list[tuple[list[str], str]]
    sections: list[str]


@dataclass
class Document:
    bibliography: list[Bibliography]
    sentences: list[Sentence]
    sha256: str
    captured_at: datetime
    identity_method: str


def local(node):
    return node.tag.rsplit("}", 1)[-1].lower()


def exact_url(value):
    parsed = urlsplit(value)
    if parsed.scheme not in ("http", "https") or parsed.query or parsed.fragment or parsed.username:
        return None
    return parsed.netloc.lower() + parsed.path.rstrip("/")


def metadata_identifiers(work):
    known, aliases = work_identifiers(work)
    result = set(known.items()) | {("DOI", doi) for doi in aliases}
    for location in work.get("locations") or []:
        if isinstance(location, dict):
            for field in ("landing_page_url", "pdf_url"):
                if location.get(field):
                    url = exact_url(location[field])
                    if url:
                        result.add(("URL", url))
    return result


def element_identifiers(element):
    found = set()
    for node in element.iter():
        if local(node) == "idno":
            kind = node.get("type", "").upper()
            if kind in ("DOI", "ARXIV", "PMID", "PMCID", "MAG"):
                found.add((kind, normalize_identifier(kind, "".join(node.itertext()))))
        if local(node) in ("ptr", "ref") and node.get("target", "").startswith("http"):
            url = exact_url(node.get("target"))
            if url:
                found.add(("URL", url))
    return found


def safe_sentence(text):
    # Narrow complete-sentence policy. Reject flattened numeric tables even with punctuation.
    if not 30 <= len(text) <= MAX_PASSAGE_CHARS or not re.search(r"[.!?][\"')]*$", text):
        return False
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", text) or "\ufffd" in text:
        return False
    without_years = re.sub(r"\b(?:18|19|20)\d{2}[a-z]?\b", "", text)
    if len(re.findall(r"\b\d[\d,.]*\b", without_years)) >= 3:
        return False
    if re.search(r"\b(entity type|number of relations|gene/protein)\b", text, re.I):
        return False
    return True


def parse_document(data: bytes, work: dict) -> Document:
    if len(data) > MAX_XML_BYTES:
        raise TEIUnavailable("tei_document_too_large")
    try:
        parser = iterparse(
            BytesIO(data),
            events=("start", "end"),
            forbid_dtd=True,
            forbid_entities=True,
            forbid_external=True,
        )
        depth, count = 0, 0
        for event, _ in parser:
            if event == "start":
                depth += 1
                count += 1
                if depth > 64 or count > MAX_NODES:
                    raise TEIUnavailable("tei_structure_limit")
            else:
                depth -= 1
        root = parser.root
        nodes = list(root.iter())
        if len(nodes) > MAX_NODES:
            raise TEIUnavailable("tei_structure_limit")
        parent = {c: p for p in nodes for c in p}
        for node in nodes:
            depth, cursor = 0, node
            while cursor in parent:
                depth += 1
                if depth > 64:
                    raise TEIUnavailable("tei_structure_limit")
                cursor = parent[cursor]
        headers = [n for n in nodes if local(n) == "teiheader"]
        if len(headers) != 1 or not any(local(n) == "tei" for n in nodes):
            raise TEIUnavailable("tei_header_missing")
        known = metadata_identifiers(work)
        header_ids = {p for p in element_identifiers(headers[0]) if p[0] != "URL"}
        if header_ids - known:
            raise TEIUnavailable("tei_document_identity_mismatch")
        bibliography = []
        used = set()
        for node in nodes:
            if local(node) != "biblstruct" or not node.get(XML_ID):
                continue
            bid = node.get(XML_ID)
            if bid in used:
                raise TEIUnavailable("tei_duplicate_bibliography_id")
            used.add(bid)
            try:
                ids = element_identifiers(node)
            except ValueError:
                ids = set()  # Malformed identifiers cannot make this entry match.
            raw = next(
                (n for n in node.iter() if local(n) == "note" and n.get("type") == "raw_reference"),
                node,
            )
            reference_text = "".join(raw.itertext()).strip()
            if len(reference_text) > 4000:
                ids, reference_text = set(), ""
            bibliography.append(Bibliography(bid, ids, reference_text))
        if len(bibliography) > 2000:
            raise TEIUnavailable("tei_structure_limit")
        sentences = []
        index_size = sum(len(repr(b)) for b in bibliography)
        for node in nodes:
            if local(node) != "s":
                continue
            ancestors, cursor = [], node
            while cursor in parent:
                cursor = parent[cursor]
                ancestors.append(cursor)
            names = {local(a) for a in ancestors}
            if names & {
                "teiheader",
                "abstract",
                "back",
                "listbibl",
                "figure",
                "table",
                "cell",
                "note",
            }:
                continue
            if any(
                a.get("type", "").lower() in ("abstract", "bibliography", "table", "figure")
                or any(
                    local(h) == "head"
                    and "".join(h.itertext()).strip().lower()
                    in ("abstract", "references", "bibliography")
                    for h in a
                )
                for a in ancestors
            ):
                continue
            # Support standard text/body/div and older html/body/tei/text/div layouts.
            if "text" not in names or not (
                "body" in names or any(local(a) == "tei" for a in ancestors)
            ):
                continue
            if any(local(a) == "s" for a in ancestors):
                continue
            text = "".join(node.itertext()).strip()
            if not safe_sentence(text):
                continue
            markers = []
            for marker in node.iter():
                if local(marker) == "ref" and marker.get("type") == "bibr":
                    targets = marker.get("target", "").split()
                    if targets and all(re.fullmatch(r"#[A-Za-z_][\w.-]*", t) for t in targets):
                        markers.append(([t[1:] for t in targets], "".join(marker.itertext())))
            if not markers:
                continue
            sections = [
                "".join(h.itertext()).strip()
                for a in reversed(ancestors)
                if local(a) == "div"
                for h in a
                if local(h) == "head"
            ]
            index_size += len(text) + len(repr(markers)) + len(repr(sections))
            if index_size > MAX_INDEX_BYTES or len(sentences) >= 5000:
                raise TEIUnavailable("tei_index_limit")
            sentences.append(Sentence(text, markers, sections))
        return Document(
            bibliography,
            sentences,
            hashlib.sha256(data).hexdigest(),
            datetime.now(UTC),
            "header_identifier_and_provider_binding"
            if header_ids
            else "authenticated_provider_binding",
        )
    except (ParseError, DefusedXmlException, ValueError, TypeError, AttributeError, RecursionError):
        raise TEIUnavailable("tei_invalid_xml_or_identifiers") from None


class OpenAlexTEIService:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client, self.settings = client, settings
        self._metadata = ResourceCache[dict | Missing](64, 86400, max_pending=16)
        self._documents = ResourceCache[Document | Missing](16, 86400, max_pending=2)
        self._gate = asyncio.Semaphore(2)
        self._blocked_until = 0.0

    async def _read(self, url, limit):
        if self._blocked_until > time.monotonic():
            raise TEIUnavailable("openalex_tei_cooldown")
        async with self.client.stream(
            "GET",
            url,
            headers={"Authorization": f"Bearer {self.settings.openalex_api_key}"},
            timeout=10,
            follow_redirects=False,
        ) as response:
            if response.status_code != 200:
                if response.status_code in (401, 403, 429):
                    delay = retry_after_seconds(response.headers.get("Retry-After")) or 0
                    self._blocked_until = time.monotonic() + max(300, delay)
                raise TEIUnavailable(f"openalex_tei_http_{response.status_code}")
            data = bytearray()
            async for chunk in response.aiter_bytes(chunk_size=65536):
                data.extend(chunk)
                if len(data) > limit:
                    raise TEIUnavailable("tei_document_too_large")
            return bytes(data)

    async def _work(self, wid):
        async def load():
            try:
                url = httpx.URL(
                    f"{self.settings.openalex_base_url.rstrip('/')}/works/{wid}",
                    params={
                        "select": (
                            "id,doi,ids,title,locations,referenced_works,content_urls,has_content"
                        )
                    },
                )
                payload = json.loads(await self._read(url, MAX_METADATA_BYTES))
                if normalize_work_id(payload["id"]) != wid:
                    raise TEIUnavailable("openalex_work_identity_mismatch")
                metadata_identifiers(payload)  # Check conflicting/malformed explicit identities.
                return payload
            except TEIUnavailable as exc:
                return Missing(str(exc))
            except httpx.HTTPError:
                return Missing("openalex_tei_transport_error")
            except (ValueError, KeyError, TypeError, AttributeError):
                return Missing("openalex_tei_invalid_metadata")

        value, _ = await self._metadata.get(
            wid, load, lifetime=lambda v: 300 if isinstance(v, Missing) else 86400
        )
        if isinstance(value, Missing):
            raise TEIUnavailable(value.reason)
        return value

    async def _document(self, wid, work):
        async def load():
            try:
                url = f"https://content.openalex.org/works/{wid}.grobid-xml"
                if (
                    not (work.get("has_content") or {}).get("grobid_xml")
                    or (work.get("content_urls") or {}).get("grobid_xml") != url
                ):
                    return Missing("openalex_tei_content_unavailable")
                data = await self._read(url, MAX_XML_BYTES)
                return await run_in_threadpool(parse_document, data, work)
            except TEIUnavailable as exc:
                return Missing(str(exc))
            except httpx.HTTPError:
                return Missing("openalex_tei_transport_error")

        return await self._documents.get(
            wid, load, lifetime=lambda v: 300 if isinstance(v, Missing) else 86400
        )

    async def retrieve(self, pair: CitationPair):
        if not self.settings.openalex_tei_enabled:
            return None, "openalex_tei_disabled"
        if not self.settings.openalex_api_key.strip():
            return None, "openalex_key_missing"
        try:
            async with asyncio.timeout(FALLBACK_TIMEOUT):
                async with self._gate:
                    work = await self._work(pair.citing_paper_id)
                    references = {normalize_work_id(r) for r in work.get("referenced_works", [])}
                    if pair.cited_paper_id not in references:
                        return None, "openalex_relationship_not_verified"
                    target = await self._work(pair.cited_paper_id)
                    document, cached = await self._document(pair.citing_paper_id, work)
                    if isinstance(document, Missing):
                        return None, document.reason
                    known = metadata_identifiers(target)
                    matches = [b for b in document.bibliography if b.identifiers & known]
                    if len(matches) != 1:
                        return (
                            None,
                            "tei_bibliography_not_verified"
                            if not matches
                            else "tei_ambiguous_bibliography",
                        )
                    bib = matches[0]
                    # A matching identifier cannot override another contradictory known namespace.
                    for kind, value in bib.identifiers:
                        values = {v for k, v in known if k == kind}
                        if kind != "URL" and values and value not in values:
                            return None, "tei_conflicting_bibliography_identifier"
                    contexts, seen = [], set()
                    for sentence in document.sentences:
                        selected = [m for m in sentence.markers if bib.id in m[0]]
                        if not selected or sentence.text in seen:
                            continue
                        if any(
                            t not in {b.id for b in document.bibliography}
                            for targets, _ in sentence.markers
                            for t in targets
                        ):
                            continue
                        seen.add(sentence.text)
                        contexts.append(
                            CitationPassage(
                                context_text=sentence.text,
                                source="openalex_tei",
                                source_url=f"https://content.openalex.org/works/{pair.citing_paper_id}.grobid-xml",
                                source_url_scope="document",
                                bibliography_id=bib.id,
                                bibliography_text=bib.text,
                                citation_marker=" ".join(m[1] for m in selected),
                                citation_targets=list(
                                    dict.fromkeys(t for m in sentence.markers for t in m[0])
                                ),
                                section=sentence.sections,
                                document_sha256=document.sha256,
                                retrieved_at=document.captured_at,
                                document_identity_method=document.identity_method,
                                identity_evidence=sorted(
                                    f"{k}:{v}" for k, v in bib.identifiers & known
                                ),
                            )
                        )
                        if len(contexts) >= MAX_PASSAGES:
                            break
                    if not contexts:
                        return None, "tei_no_safe_body_sentence"

                    def mapping(record, wid):
                        ids, _ = work_identifiers(record)
                        return PaperMapping(
                            openalex_id=wid,
                            doi=ids.get("DOI"),
                            title=record.get("title"),
                            verified=True,
                        )

                    return CitationContexts(
                        **pair.model_dump(),
                        status="available",
                        source="openalex_tei",
                        origin="memory_cache" if cached else "live",
                        contexts=contexts,
                        citing_mapping=mapping(work, pair.citing_paper_id),
                        cited_mapping=mapping(target, pair.cited_paper_id),
                        relationship_found=True,
                        retrieved_at=document.captured_at,
                        observed_context_count=len(contexts),
                        evidence_urls=[contexts[0].source_url],
                    ), None
        except TimeoutError:
            return None, "openalex_tei_timeout"
        except httpx.HTTPError:
            return None, "openalex_tei_transport_error"
        except TEIUnavailable as exc:
            return None, str(exc)
        except (ValueError, TypeError, KeyError, AttributeError):
            return None, "openalex_tei_invalid_metadata"
        except ServiceError as exc:
            return None, exc.code
