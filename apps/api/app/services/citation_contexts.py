"""Retrieve citation evidence after verifying explicit cross-provider identifiers."""

import asyncio
import json
import logging
import math
import random
import re
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from time import perf_counter
from typing import Literal
from urllib.parse import quote

import httpx
from pydantic import ValidationError

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.citation_contexts import (
    CitationContexts,
    CitationPair,
    CitationPassage,
    PaperMapping,
)
from app.schemas.contracts import ClassifyRequest, normalize_work_id
from app.services.citation_identifiers import identity_matches, normalize_doi, work_identifiers
from app.services.citation_timing import record_timing, timed, timing
from app.services.inference import InferenceService
from app.services.openalex_tei import OpenAlexTEIService
from app.services.resource_cache import ResourceCache

SEMANTIC_INTERVAL_SECONDS = 1.5
MAX_RETRY_DELAY_SECONDS = 5.0
REFERENCE_PAGE_SIZE = 100
MAX_REFERENCE_PAGES = 5
CONTEXT_CACHE_SECONDS = 300
CONTEXT_CACHE_ENTRIES = 128
MAPPING_CACHE_SECONDS = 86400
MAPPING_CACHE_ENTRIES = 512
REFERENCE_CACHE_SECONDS = 900
REFERENCE_CACHE_ENTRIES = 128
SEMANTIC_QUEUE_TIMEOUT_SECONDS = 30.0
MAX_SEMANTIC_INTERVAL_SECONDS = 4.5
EXAMPLES_PATH = Path(__file__).resolve().parents[1] / "examples" / "citation_contexts.json"
logger = logging.getLogger(__name__)


def _invalid_response(provider: str) -> ServiceError:
    return ServiceError(502, f"{provider}_invalid_response", f"{provider} returned invalid data")


def _retry_delay(response: httpx.Response, attempt: int) -> float:
    header = response.headers.get("Retry-After")
    if header:
        try:
            delay = float(header)
        except ValueError:
            try:
                retry_at = parsedate_to_datetime(header)
                if retry_at.tzinfo is None:
                    retry_at = retry_at.replace(tzinfo=UTC)
                delay = (retry_at - datetime.now(UTC)).total_seconds()
            except (ValueError, TypeError, OverflowError):
                delay = _backoff(attempt)
        if math.isfinite(delay):
            return max(0.0, delay)
    return _backoff(attempt)


def _backoff(attempt: int) -> float:
    return min(MAX_RETRY_DELAY_SECONDS, 2.0**attempt + random.uniform(0, 0.25))


@dataclass
class ReferencePage:
    payload: dict
    evidence_url: str
    retrieved_at: datetime


class CitationContextService:
    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings
        self._semantic_lock = asyncio.Lock()
        self._next_semantic_request = 0.0
        self._semantic_interval = SEMANTIC_INTERVAL_SECONDS
        self._semantic_successes = 0
        self._semantic_cooldown_until = 0.0
        self._semantic_cooldown = asyncio.Event()
        self._cache: OrderedDict[tuple[str, str], tuple[float, CitationContexts]] = OrderedDict()
        self._doi_aliases: OrderedDict[str, set[str]] = OrderedDict()
        self._examples: dict[tuple[str, str], CitationContexts] | None = None
        self._mappings = ResourceCache[PaperMapping](MAPPING_CACHE_ENTRIES, MAPPING_CACHE_SECONDS)
        self._semantic_papers = ResourceCache[dict | None](
            MAPPING_CACHE_ENTRIES, MAPPING_CACHE_SECONDS
        )
        self._references = ResourceCache[ReferencePage](
            REFERENCE_CACHE_ENTRIES, REFERENCE_CACHE_SECONDS
        )
        # No stored pair values here: the existing pair cache owns their TTL.
        self._pairs = ResourceCache[CitationContexts](CONTEXT_CACHE_ENTRIES, 0)
        self.tei = OpenAlexTEIService(client, settings)
        self._tei_pairs = ResourceCache(128, 300, max_pending=16)

    @timed("classification_retrieval")
    async def retrieve_for_classification(self, pair: CitationPair, mode="auto"):
        """Overlap fallback with an observed cooldown, retaining the primary retry path."""
        if mode == "examples":
            return await self.retrieve(pair, mode=mode)
        key = (pair.citing_paper_id, pair.cited_paper_id)
        can_fallback = self.settings.openalex_tei_enabled and bool(
            self.settings.openalex_api_key.strip()
        )

        async def primary():
            try:
                return await self.retrieve(pair, mode=mode), None
            except ServiceError as exc:
                return self._unavailable(pair, "provider_unavailable", exc.code), exc

        async def load_fallback():
            started = perf_counter()
            value, reused = await self._tei_pairs.get(key, lambda: self.tei.retrieve(pair))
            record_timing("fallback_cache", started, reused=reused)
            return value

        primary_task = asyncio.create_task(primary())
        tasks = [primary_task]
        fallback_task = None
        speculative = False
        try:
            if can_fallback and self.settings.semantic_scholar_enabled:
                cooldown = asyncio.create_task(self._wait_for_semantic_cooldown())
                tasks.append(cooldown)
                await asyncio.wait([primary_task, cooldown], return_when=asyncio.FIRST_COMPLETED)
                if not primary_task.done():
                    record_timing(
                        "cooldown_fallback",
                        perf_counter(),
                        remaining_ms=max(0, self._semantic_cooldown_until - time.monotonic())
                        * 1000,
                    )
                    speculative = True
                    fallback_task = asyncio.create_task(load_fallback())
                    tasks.append(fallback_task)
                    await asyncio.wait(
                        [primary_task, fallback_task], return_when=asyncio.FIRST_COMPLETED
                    )
                    if not primary_task.done():
                        # An unsuccessful speculative fallback must not replace
                        # a primary success or remove its remaining retry chances.
                        try:
                            fallback, _ = fallback_task.result()
                        except Exception:
                            fallback = None
                        if fallback is not None and self._classifiable(fallback):
                            # A resumed primary keeps its success chance. Return
                            # early only during an actual provider cooldown;
                            # otherwise wait for its result or another 429.
                            cooldown = asyncio.create_task(self._wait_for_semantic_cooldown())
                            tasks.append(cooldown)
                            await asyncio.wait(
                                [primary_task, cooldown], return_when=asyncio.FIRST_COMPLETED
                            )
                            if not primary_task.done():
                                self._remember(key, fallback)
                                return fallback

            result, primary_error = await primary_task
            if self._classifiable(result):
                return result
            if not can_fallback:
                if primary_error:
                    raise primary_error
                return result
            if fallback_task is None:
                fallback_task = asyncio.create_task(load_fallback())
                tasks.append(fallback_task)
            try:
                fallback, reason = await fallback_task
            except ServiceError as exc:
                if not speculative or exc.code != "citation_context_busy":
                    raise
                # Early capacity rejection sent no I/O and is not cached. Keep
                # the original late fallback opportunity once the primary fails.
                fallback, reason = await load_fallback()
            if fallback is not None:
                result = fallback
            else:
                result.fallback_reason = reason
            # Re-reading a negative pair must not indefinitely extend its TTL.
            self._remember(
                key, result, refresh=fallback is not None or result.origin != "memory_cache"
            )
            return result
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _wait_for_semantic_cooldown(self):
        while self._semantic_cooldown_until <= time.monotonic():
            self._semantic_cooldown.clear()
            await self._semantic_cooldown.wait()

    @staticmethod
    def _classifiable(result):
        return (
            result.relationship_found is True
            and result.citing_mapping.verified
            and result.cited_mapping.verified
            and any(len(c.context_text) <= 20000 for c in result.contexts)
        )

    def _remember(self, key, result, *, refresh=True):
        expires = time.monotonic() + CONTEXT_CACHE_SECONDS
        if not refresh and key in self._cache:
            expires = self._cache[key][0]
        self._cache[key] = (expires, result.model_copy(deep=True))
        self._cache.move_to_end(key)
        if len(self._cache) > CONTEXT_CACHE_ENTRIES:
            self._cache.popitem(last=False)

    def _example(self, key: tuple[str, str]) -> CitationContexts | None:
        if self._examples is None:
            self._examples = {}
            try:
                records = json.loads(EXAMPLES_PATH.read_text(encoding="utf-8"))["examples"]
                for record in records:
                    result = CitationContexts.model_validate(record)
                    if not (
                        result.available
                        and result.citing_mapping.verified
                        and result.cited_mapping.verified
                        and result.relationship_found is True
                        and result.retrieved_at
                        and result.evidence_urls
                    ):
                        raise ValueError(
                            "Examples require verified mappings, passages and recorded provenance"
                        )
                    result.origin = "verified_example"
                    for context in result.contexts:
                        context.classification = None
                        context.classification_unavailable_reason = None
                    self._examples[(result.citing_paper_id, result.cited_paper_id)] = result
            except (OSError, ValueError, KeyError, TypeError):
                logger.exception("Verified citation examples could not be loaded")
                self._examples = {}
        result = self._examples.get(key)
        return result.model_copy(deep=True) if result is not None else None

    @staticmethod
    def _unavailable(pair: CitationPair, status: str, reason: str) -> CitationContexts:
        return CitationContexts(
            **pair.model_dump(),
            status=status,
            origin="unavailable",
            reason=reason,
            citing_mapping=PaperMapping(openalex_id=pair.citing_paper_id, reason=reason),
            cited_mapping=PaperMapping(openalex_id=pair.cited_paper_id, reason=reason),
        )

    async def retrieve(
        self, pair: CitationPair, mode: Literal["auto", "live", "examples"] = "auto"
    ) -> CitationContexts:
        started = perf_counter()
        key = (pair.citing_paper_id, pair.cited_paper_id)
        if mode == "auto" and key in self._cache:
            expires_at, result = self._cache[key]
            if expires_at > time.monotonic():
                self._cache.move_to_end(key)
                record_timing("pair_cache", started, reused=True)
                return result.model_copy(deep=True, update={"origin": "memory_cache"})
            del self._cache[key]
        record_timing("pair_cache", started, reused=False)
        if mode in ("auto", "examples"):
            example = self._example(key)
            if example is not None:
                return example
            if mode == "examples":
                return self._unavailable(pair, "example_not_found", "no_verified_example")
        if not self.settings.semantic_scholar_enabled:
            if mode == "live":
                raise ServiceError(
                    503, "semantic_scholar_disabled", "Live Semantic Scholar retrieval is disabled"
                )
            return self._unavailable(pair, "provider_unavailable", "semantic_scholar_disabled")
        try:
            result, _ = await self._pairs.get(key, lambda: self._retrieve_live(pair))
        except ServiceError as exc:
            if mode == "live":
                raise
            return self._unavailable(pair, "provider_unavailable", exc.code)
        if result.retrieved_at is None:
            result.retrieved_at = datetime.now(UTC)
        self._remember(key, result)
        return result

    async def _send(self, provider: str, url: str, params: dict, headers: dict) -> httpx.Response:
        if provider != "semantic_scholar":
            with timing("mapping_metadata_http"):
                return await self.client.get(url, params=params, headers=headers, timeout=10.0)
        try:
            async with asyncio.timeout(SEMANTIC_QUEUE_TIMEOUT_SECONDS):
                queued_at = perf_counter()
                async with self._semantic_lock:
                    record_timing("semantic_queue", queued_at)
                    delay = self._next_semantic_request - time.monotonic()
                    if delay > MAX_RETRY_DELAY_SECONDS:
                        raise ServiceError(
                            503, "semantic_scholar_rate_limited", "Semantic Scholar is rate limited"
                        )
                    if delay > 0:
                        with timing("semantic_pacing"):
                            await asyncio.sleep(delay)
                    self._next_semantic_request = time.monotonic() + self._semantic_interval
                    with timing("semantic_http"):
                        response = await self.client.get(
                            url, params=params, headers=headers, timeout=10.0
                        )
                    # Publish cooldown before releasing the shared scheduler lock.
                    if response.status_code == 429:
                        self._semantic_successes = 0
                        self._semantic_interval = min(
                            MAX_SEMANTIC_INTERVAL_SECONDS,
                            max(SEMANTIC_INTERVAL_SECONDS, self._semantic_interval * 1.5),
                        )
                        self._next_semantic_request = max(
                            self._next_semantic_request,
                            time.monotonic()
                            + max(_retry_delay(response, 0), self._semantic_interval),
                        )
                        self._semantic_cooldown_until = self._next_semantic_request
                        self._semantic_cooldown.set()
                    elif response.is_success:
                        self._semantic_successes += 1
                        if self._semantic_successes >= 8:
                            self._semantic_interval = max(
                                SEMANTIC_INTERVAL_SECONDS, self._semantic_interval - 0.25
                            )
                            self._semantic_successes = 0
                    return response
        except TimeoutError:
            raise ServiceError(
                503, "semantic_scholar_busy", "Semantic Scholar request queue is busy"
            ) from None

    async def _get(self, provider: str, path: str, params: dict) -> dict | None:
        headers = {}
        if provider == "semantic_scholar":
            base_url = self.settings.semantic_scholar_base_url
            if self.settings.semantic_scholar_api_key:
                headers["x-api-key"] = self.settings.semantic_scholar_api_key
        else:
            base_url = self.settings.openalex_base_url
            if self.settings.openalex_api_key:
                headers["Authorization"] = f"Bearer {self.settings.openalex_api_key}"
        for attempt in range(3):
            started = perf_counter()
            try:
                response = await self._send(
                    provider, f"{base_url.rstrip('/')}/{path}", params, headers
                )
            except httpx.TransportError:
                if attempt < 2:
                    with timing("provider_backoff", provider=provider):
                        await asyncio.sleep(_backoff(attempt))
                    continue
                raise ServiceError(
                    502, f"{provider}_unavailable", f"{provider} could not be reached"
                ) from None
            record_timing(
                "provider_attempt",
                started,
                provider=provider,
                operation="references" if path.endswith("/references") else "mapping",
                attempt=attempt + 1,
                status=response.status_code,
            )
            if response.status_code == 404:
                return None
            if response.status_code == 429 or response.status_code >= 500:
                delay = _retry_delay(response, attempt)
                code = "rate_limited" if response.status_code == 429 else "unavailable"
                if attempt == 2 or delay > MAX_RETRY_DELAY_SECONDS:
                    raise ServiceError(
                        503, f"{provider}_{code}", f"{provider} is temporarily unavailable"
                    )
                with timing("provider_backoff", provider=provider):
                    await asyncio.sleep(delay)
                continue
            if response.status_code in (401, 403):
                raise ServiceError(
                    503, f"{provider}_access_denied", f"{provider} access is unavailable"
                )
            if response.is_error:
                raise ServiceError(502, f"{provider}_error", f"{provider} rejected the request")
            try:
                payload = response.json()
            except ValueError:
                raise _invalid_response(provider) from None
            if not isinstance(payload, dict):
                raise _invalid_response(provider)
            return payload
        raise AssertionError("Retry loop exhausted unexpectedly")

    @timed("identifier_resolution")
    async def _map_paper(self, work_id: str) -> PaperMapping:
        started = perf_counter()
        mapping, reused = await self._mappings.get(
            work_id,
            lambda: self._resolve_paper(work_id),
            lifetime=lambda mapping: MAPPING_CACHE_SECONDS if mapping.verified else 300,
        )
        record_timing("mapping_cache", started, reused=reused)
        return mapping

    async def _resolve_paper(self, work_id: str) -> PaperMapping:
        mapping = PaperMapping(openalex_id=work_id)
        work = await self._get(
            "openalex", f"works/{work_id}", {"select": "id,doi,ids,title,locations"}
        )
        if work is None:
            return mapping.model_copy(update={"reason": "openalex_work_not_found"})
        try:
            if not isinstance(work.get("id"), str):
                raise TypeError("Missing OpenAlex work identity")
            if normalize_work_id(work["id"]) != work_id:
                return mapping.model_copy(update={"reason": "openalex_id_mismatch"})
            ids = work.get("ids") or {}
            if not isinstance(ids, dict):
                raise TypeError("Invalid OpenAlex identifiers")
        except (KeyError, TypeError):
            raise _invalid_response("openalex") from None
        except ValueError:
            return mapping.model_copy(update={"reason": "invalid_openalex_identifier"})
        if isinstance(work.get("title"), str):
            mapping.title = work["title"]
        try:
            known, aliases = work_identifiers(work)
        except ValueError as exc:
            reason = (
                "ambiguous_openalex_doi" if str(exc) == "ambiguous_doi_identifier" else str(exc)
            )
            return mapping.model_copy(update={"reason": reason})
        mapping.doi = known.get("DOI")
        mapping.reason = "missing_doi" if not mapping.doi else "semantic_scholar_work_not_found"
        for kind, value in known.items():
            paper, _ = await self._semantic_papers.get(
                (kind, value),
                lambda: self._get(
                    "semantic_scholar",
                    f"paper/{kind}:{quote(value, safe='')}",
                    {"fields": "paperId,externalIds"},
                ),
                lifetime=lambda paper: (
                    300
                    if paper is None
                    else MAPPING_CACHE_SECONDS
                    if identity_matches(paper, kind, value, known, aliases)
                    and isinstance(paper.get("paperId"), str)
                    and re.fullmatch(r"[a-fA-F0-9]{40}", paper["paperId"])
                    else 0
                ),
            )
            if paper is None:
                mapping.reason = "semantic_scholar_work_not_found"
                continue
            external_ids = paper.get("externalIds") or {}
            if not isinstance(external_ids, dict):
                raise _invalid_response("semantic_scholar")
            if not identity_matches(paper, kind, value, known, aliases):
                mapping.reason = "unverified_alternative_identifier"
                if kind == "DOI":
                    try:
                        normalize_doi(external_ids.get("DOI"))
                        mapping.reason = "semantic_scholar_doi_mismatch"
                    except ValueError:
                        mapping.reason = "unverified_semantic_scholar_doi"
                continue
            paper_id = paper.get("paperId")
            if not isinstance(paper_id, str) or not re.fullmatch(r"[a-fA-F0-9]{40}", paper_id):
                raise _invalid_response("semantic_scholar")
            mapping.semantic_scholar_paper_id = paper_id.lower()
            mapping.verified = True
            mapping.reason = None
            accepted_dois = set(aliases)
            if external_ids.get("DOI"):
                accepted_dois.add(normalize_doi(external_ids["DOI"]))
            self._doi_aliases[paper_id.lower()] = accepted_dois
            self._doi_aliases.move_to_end(paper_id.lower())
            if len(self._doi_aliases) > MAPPING_CACHE_ENTRIES:
                self._doi_aliases.popitem(last=False)
            return mapping
        return mapping

    @timed("semantic_references")
    async def _reference_page(self, paper_id: str, offset: int) -> tuple[ReferencePage, bool]:
        parameters = {
            "fields": "contexts,externalIds",
            "limit": REFERENCE_PAGE_SIZE,
            "offset": offset,
        }
        path = f"paper/{paper_id}/references"
        key = (paper_id, tuple(sorted(parameters.items())))

        async def load():
            payload = await self._get("semantic_scholar", path, parameters)
            if payload is None:
                raise ServiceError(
                    503, "semantic_scholar_unavailable", "Verified reference data is unavailable"
                )
            if not isinstance(payload.get("data"), list) or payload.get("offset", offset) != offset:
                raise _invalid_response("semantic_scholar")
            next_offset = payload.get("next")
            if next_offset is not None and (type(next_offset) is not int or next_offset <= offset):
                raise _invalid_response("semantic_scholar")
            # Validate before storing so a malformed response cannot poison the page cache.
            for reference in payload["data"]:
                if not isinstance(reference, dict):
                    raise _invalid_response("semantic_scholar")
                paper = reference.get("citedPaper")
                if paper is None:
                    continue
                if not isinstance(paper, dict):
                    raise _invalid_response("semantic_scholar")
                identifiers = paper.get("externalIds") or {}
                if not isinstance(identifiers, dict):
                    raise _invalid_response("semantic_scholar")
                if identifiers.get("DOI"):
                    try:
                        normalize_doi(identifiers["DOI"])
                    except ValueError:
                        raise _invalid_response("semantic_scholar") from None
                passages = reference.get("contexts")
                if passages is not None and (
                    not isinstance(passages, list)
                    or any(not isinstance(text, str) for text in passages)
                ):
                    raise _invalid_response("semantic_scholar")
            url = str(
                httpx.URL(
                    f"{self.settings.semantic_scholar_base_url.rstrip('/')}/{path}",
                    params=parameters,
                )
            )
            return ReferencePage(payload, url, datetime.now(UTC))

        started = perf_counter()
        page, reused = await self._references.get(key, load)
        record_timing("reference_cache", started, reused=reused)
        return page, reused

    async def _retrieve_live(self, pair: CitationPair) -> CitationContexts:
        citing = await self._map_paper(pair.citing_paper_id)
        cited = await self._map_paper(pair.cited_paper_id)
        result = CitationContexts(
            **pair.model_dump(),
            status="unresolved_identifiers",
            citing_mapping=citing,
            cited_mapping=cited,
        )
        if not citing.verified or not cited.verified:
            return result
        if (
            citing.semantic_scholar_paper_id == cited.semantic_scholar_paper_id
            and citing.openalex_id != cited.openalex_id
        ):
            result.reason = "ambiguous_paper_pair"
            return result
        offset = 0
        contexts = []
        found = False
        all_pages_cached = True
        for _ in range(MAX_REFERENCE_PAGES):
            page, cached = await self._reference_page(citing.semantic_scholar_paper_id, offset)
            all_pages_cached = all_pages_cached and cached
            payload = page.payload
            result.evidence_urls.append(page.evidence_url)
            result.retrieved_at = min(result.retrieved_at or page.retrieved_at, page.retrieved_at)
            references = payload.get("data")
            if not isinstance(references, list) or payload.get("offset", offset) != offset:
                raise _invalid_response("semantic_scholar")
            for reference in references:
                if not isinstance(reference, dict):
                    raise _invalid_response("semantic_scholar")
                paper = reference.get("citedPaper")
                if paper is None:
                    continue
                if not isinstance(paper, dict):
                    raise _invalid_response("semantic_scholar")
                external_ids = paper.get("externalIds") or {}
                if not isinstance(external_ids, dict):
                    raise _invalid_response("semantic_scholar")
                reference_doi = external_ids.get("DOI")
                try:
                    reference_doi = normalize_doi(reference_doi) if reference_doi else None
                except ValueError:
                    raise _invalid_response("semantic_scholar") from None
                reference_id = paper.get("paperId")
                matches_id = reference_id == cited.semantic_scholar_paper_id
                matches_doi = bool(cited.doi and reference_doi == cited.doi)
                accepted_dois = self._doi_aliases.get(
                    cited.semantic_scholar_paper_id, {cited.doi} if cited.doi else set()
                )
                if (
                    matches_id
                    and accepted_dois
                    and reference_doi
                    and reference_doi not in accepted_dois
                ) or (matches_doi and reference_id not in (None, cited.semantic_scholar_paper_id)):
                    result.reason = "ambiguous_reference_identity"
                    return result
                if not matches_id and not (matches_doi and reference_id is None):
                    continue
                found = True
                passages = reference.get("contexts")
                if passages is None:
                    passages = []
                if not isinstance(passages, list) or any(
                    not isinstance(text, str) for text in passages
                ):
                    raise _invalid_response("semantic_scholar")
                contexts.extend(text for text in passages if text.strip())
            next_offset = payload.get("next")
            if next_offset is None:
                result.reference_scan_complete = True
                break
            if type(next_offset) is not int or next_offset <= offset:
                raise _invalid_response("semantic_scholar")
            offset = next_offset
        result.relationship_found = found if result.reference_scan_complete or found else None
        result.contexts = [
            CitationPassage(
                context_text=text,
                source_url=f"https://www.semanticscholar.org/paper/{citing.semantic_scholar_paper_id}",
            )
            for text in dict.fromkeys(contexts)
        ]
        result.observed_context_count = len(result.contexts)
        result.origin = "memory_cache" if all_pages_cached else "live"
        if not result.reference_scan_complete:
            result.status = "incomplete"
            result.reason = "reference_scan_limit"
        elif result.contexts:
            result.status = "available"
        else:
            result.status = "no_context" if found else "relationship_not_found"
        return result


@timed("model_inference")
def classify_contexts(result: CitationContexts, inference: InferenceService) -> CitationContexts:
    """Classify retrieved evidence for this pair only, preserving its exact attribution."""
    classified = result.model_copy(deep=True)
    if classified.contexts and not (
        classified.citing_mapping.verified
        and classified.cited_mapping.verified
        and classified.relationship_found is True
    ):
        raise ServiceError(
            422, "unverified_context", "Citation evidence requires verified paper mappings"
        )
    for context in classified.contexts:
        try:
            request = ClassifyRequest(
                context_text=context.context_text, context_source_url=context.source_url
            )
        except ValidationError:
            context.classification_unavailable_reason = "context_too_long"
            continue
        context.classification = inference.classify(request.context_text)
    return classified
