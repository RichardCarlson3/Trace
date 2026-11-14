import asyncio
import math
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.contracts import (
    Citation,
    IncomingCitationResponse,
    NeighborResponse,
    Paper,
    PaperDetails,
    ReferenceResponse,
    SearchResponse,
    normalize_work_id,
)
from app.services.neighbor_cursor import Direction, NeighborCursor

MAX_ATTEMPTS = 3
REQUEST_TIMEOUT_SECONDS = 10.0
MAX_RETRY_WAIT_SECONDS = 2.0
MAX_BASIC_RESULTS = 10_000


def retry_after_seconds(value: str | None) -> float | None:
    """Read delta-seconds or an HTTP date; invalid headers use normal backoff."""
    if value is None:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                date = date.replace(tzinfo=UTC)
            seconds = (date - datetime.now(UTC)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def normalize_paper(work: dict) -> Paper:
    inverted = work.get("abstract_inverted_index")
    abstract = None
    if inverted is not None:
        if not isinstance(inverted, dict):
            raise ValueError("Expected an inverted abstract index")
        words = {}
        for word, positions in inverted.items():
            if not isinstance(word, str) or not word or not isinstance(positions, list):
                raise ValueError("Invalid abstract token")
            for position in positions:
                if type(position) is not int or position < 0 or position in words:
                    raise ValueError("Invalid or duplicate abstract position")
                words[position] = word
        if sorted(words) != list(range(len(words))):
            raise ValueError("Incomplete abstract positions")
        abstract = " ".join(words[index] for index in range(len(words))) if words else None
    location = work.get("primary_location") or {}
    title = work.get("display_name")
    if title is None or (isinstance(title, str) and not title.strip()):
        title = work.get("title")
    if isinstance(title, str):
        title = title.strip()
    return Paper(
        id=work["id"],
        doi=work.get("doi"),
        title=title or "Untitled work",
        year=work.get("publication_year"),
        authors=[
            entry["author"]["display_name"].strip()
            for entry in work.get("authorships") or []
            if (entry.get("author") or {}).get("display_name")
            and entry["author"]["display_name"].strip()
        ],
        abstract=abstract,
        cited_by_count=work.get("cited_by_count") or 0,
        landing_page_url=location.get("landing_page_url"),
    )


class OpenAlexService:
    """Owns provider I/O and normalization; a future metadata cache belongs here."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def search(self, query: str, page: int, per_page: int) -> SearchResponse:
        if not 1 <= per_page <= 25 or page < 1 or page * per_page > MAX_BASIC_RESULTS:
            raise ServiceError(
                422,
                "validation_error",
                "Search requires per_page 1–25 and page × per_page no greater than 10000",
            )
        params = {"search": query, "page": page, "per-page": per_page}
        payload = await self._get_json("/works", params=params)
        try:
            results = payload["results"]
            if not isinstance(results, list) or len(results) > per_page:
                raise ValueError("Invalid search page size")
            return SearchResponse(
                papers=[normalize_paper(work) for work in results],
                total=payload["meta"]["count"],
                page=page,
                per_page=per_page,
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise self._invalid_response() from None

    async def details(self, work_id: str) -> PaperDetails:
        work_id = normalize_work_id(work_id)
        work = await self._get_json(f"/works/{work_id}", missing_paper=True)
        try:
            paper = normalize_paper(work)
            location = work.get("primary_location") or {}
            source = location.get("source") or {}
            reference_count = work.get("referenced_works_count")
            if reference_count is None and isinstance(work.get("referenced_works"), list):
                reference_count = len(work["referenced_works"])
            return PaperDetails(
                **paper.model_dump(),
                publication_venue=source.get("display_name"),
                reference_count=reference_count,
            )
        except (ValueError, KeyError, TypeError, AttributeError):
            raise self._invalid_response() from None

    async def references(
        self, work_id: str, *, limit: int = 10, offset: int = 0
    ) -> ReferenceResponse:
        if not 1 <= limit <= 50 or offset < 0:
            raise ServiceError(422, "validation_error", "Expected limit 1–50 and offset >= 0")
        work_id = normalize_work_id(work_id)
        work = await self._get_json(f"/works/{work_id}", missing_paper=True)
        return await self._references_for_seed(work, limit=limit, offset=offset)

    async def _references_for_seed(
        self, work: dict, *, limit: int, offset: int
    ) -> ReferenceResponse:
        try:
            seed = normalize_paper(work)
            references = work.get("referenced_works")
            if references is None:
                references = []
            if not isinstance(references, list):
                raise ValueError("Expected a reference list")
            # Deduplicate before slicing so offsets count unique, non-self references.
            reference_ids = list(dict.fromkeys(normalize_work_id(ref) for ref in references))
            reference_ids = [ref for ref in reference_ids if ref != seed.id]
        except (ValueError, KeyError, TypeError, AttributeError):
            raise self._invalid_response() from None

        selected = reference_ids[offset : offset + limit]
        papers_by_id = {}
        if selected:
            payload = await self._get_json(
                "/works",
                params={"filter": f"ids.openalex:{'|'.join(selected)}", "per_page": len(selected)},
            )
            results = payload.get("results")
            if not isinstance(results, list) or len(results) > len(selected):
                raise self._invalid_response()
            # A partial batch must never produce invented nodes or dangling edges.
            requested = set(selected)
            for record in results:
                try:
                    paper = normalize_paper(record)
                except (ValueError, KeyError, TypeError, AttributeError):
                    continue
                if paper.id in requested:
                    papers_by_id.setdefault(paper.id, paper)

        resolved = [papers_by_id[ref] for ref in selected if ref in papers_by_id]
        end = offset + len(selected)
        has_more = end < len(reference_ids)
        return ReferenceResponse(
            seed_paper_id=seed.id,
            papers=[seed, *resolved],
            citations=[
                Citation(id=f"{seed.id}->{paper.id}", source=seed.id, target=paper.id)
                for paper in resolved
            ],
            next_offset=end if has_more else None,
            has_more=has_more,
            unresolved_reference_ids=[ref for ref in selected if ref not in papers_by_id],
        )

    async def citations(
        self, work_id: str, *, limit: int = 10, cursor: str = "*"
    ) -> IncomingCitationResponse:
        if (
            not 1 <= limit <= 50
            or not cursor
            or len(cursor) > 2048
            or any(char.isspace() for char in cursor)
        ):
            raise ServiceError(422, "validation_error", "Expected limit 1–50 and a nonblank cursor")
        work_id = normalize_work_id(work_id)
        work = await self._get_json(f"/works/{work_id}", missing_paper=True)
        try:
            seed = normalize_paper(work)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise self._invalid_response() from None
        return await self._citations_for_seed(seed, limit=limit, cursor=cursor)

    async def _citations_for_seed(
        self, seed: Paper, *, limit: int, cursor: str
    ) -> IncomingCitationResponse:
        payload = await self._get_json(
            "/works",
            params={"filter": f"cites:{seed.id}", "per_page": limit, "cursor": cursor},
            cursor_paging=True,
        )
        results = payload.get("results")
        meta = payload.get("meta")
        if not isinstance(results, list) or len(results) > limit or not isinstance(meta, dict):
            raise self._invalid_response()
        if "next_cursor" not in meta:
            raise self._invalid_response()
        next_cursor = meta["next_cursor"]
        if next_cursor is not None and (
            not isinstance(next_cursor, str)
            or not next_cursor
            or len(next_cursor) > 2048
            or any(char.isspace() for char in next_cursor)
            or next_cursor == cursor
        ):
            raise self._invalid_response()

        citing_papers = {}
        skipped = 0
        for record in results:
            try:
                paper = normalize_paper(record)
            except (ValueError, KeyError, TypeError, AttributeError):
                skipped += 1
                continue
            if paper.id == seed.id:
                skipped += 1
                continue
            citing_papers.setdefault(paper.id, paper)
        return IncomingCitationResponse(
            seed_paper_id=seed.id,
            papers=[seed, *citing_papers.values()],
            citations=[
                Citation(id=f"{paper.id}->{seed.id}", source=paper.id, target=seed.id)
                for paper in citing_papers.values()
            ],
            next_cursor=next_cursor,
            has_more=next_cursor is not None,
            skipped_record_count=skipped,
        )

    async def neighbors(
        self, work_id: str, *, direction: Direction = "both", limit: int = 10, cursor: str = "*"
    ) -> NeighborResponse:
        if direction not in ("incoming", "outgoing", "both") or not 1 <= limit <= 50:
            raise ServiceError(422, "validation_error", "Expected a valid direction and limit 1–50")
        work_id = normalize_work_id(work_id)
        state = NeighborCursor.start_or_decode(
            cursor, work_id=work_id, direction=direction, limit=limit
        )
        work = await self._get_json(f"/works/{work_id}", missing_paper=True)
        try:
            seed = normalize_paper(work)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise self._invalid_response() from None

        outgoing_limit = limit if state.outgoing_offset is not None else 0
        incoming_limit = limit if state.incoming_cursor is not None else 0
        if outgoing_limit and incoming_limit:
            if limit == 1:
                outgoing_limit = int(state.turn == "outgoing")
                incoming_limit = 1 - outgoing_limit
                state.turn = "incoming" if outgoing_limit else "outgoing"
            else:
                outgoing_limit = (limit + 1) // 2
                incoming_limit = limit // 2

        requests = []
        unresolved = []
        skipped = 0
        if outgoing_limit:
            requests.append(
                asyncio.create_task(
                    self._references_for_seed(
                        work, limit=outgoing_limit, offset=state.outgoing_offset
                    )
                )
            )
        if incoming_limit:
            requests.append(
                asyncio.create_task(
                    self._citations_for_seed(
                        seed, limit=incoming_limit, cursor=state.incoming_cursor
                    )
                )
            )
        try:
            pages = await asyncio.gather(*requests)
        finally:
            # Fail atomically and stop sibling I/O if either direction fails or the caller cancels.
            for request in requests:
                if not request.done():
                    request.cancel()
            await asyncio.gather(*requests, return_exceptions=True)

        for page in pages:
            if isinstance(page, ReferenceResponse):
                state.outgoing_offset = page.next_offset
                unresolved = page.unresolved_reference_ids
            else:
                state.incoming_cursor = page.next_cursor
                skipped = page.skipped_record_count

        papers = {seed.id: seed}
        citations = {}
        for page in pages:
            for paper in page.papers:
                papers.setdefault(paper.id, paper)
            for edge in page.citations:
                citations.setdefault((edge.source, edge.target), edge)
        has_more = state.outgoing_offset is not None or state.incoming_cursor is not None
        return NeighborResponse(
            seed_paper_id=seed.id,
            papers=list(papers.values()),
            citations=list(citations.values()),
            next_cursor=state.encode() if has_more else None,
            has_more=has_more,
            unresolved_reference_ids=unresolved,
            skipped_record_count=skipped,
        )

    @staticmethod
    def _invalid_response() -> ServiceError:
        return ServiceError(502, "openalex_invalid_response", "OpenAlex returned invalid data")

    async def _get_json(
        self,
        path: str,
        *,
        params: dict | None = None,
        missing_paper: bool = False,
        cursor_paging: bool = False,
    ) -> dict:
        headers = {}
        if self.settings.openalex_api_key:
            headers["Authorization"] = f"Bearer {self.settings.openalex_api_key}"
        for attempt in range(MAX_ATTEMPTS):
            try:
                async with asyncio.timeout(REQUEST_TIMEOUT_SECONDS):
                    response = await self.client.get(
                        f"{self.settings.openalex_base_url.rstrip('/')}{path}",
                        params=params,
                        headers=headers,
                        timeout=REQUEST_TIMEOUT_SECONDS,
                    )
            except (httpx.TransportError, TimeoutError):
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise ServiceError(
                    502, "openalex_unavailable", "OpenAlex could not be reached"
                ) from None
            except httpx.DecodingError:
                raise self._invalid_response() from None
            except (httpx.RequestError, httpx.InvalidURL):
                raise ServiceError(
                    502, "openalex_error", "OpenAlex request could not be completed"
                ) from None
            if response.status_code == 429 or response.status_code >= 500:
                delay = max(
                    0.25 * 2**attempt, retry_after_seconds(response.headers.get("Retry-After")) or 0
                )
                if attempt < MAX_ATTEMPTS - 1 and delay <= MAX_RETRY_WAIT_SECONDS:
                    await asyncio.sleep(delay)
                    continue
                raise ServiceError(
                    503, "openalex_unavailable", "OpenAlex is busy. Try again shortly."
                )
            if response.status_code == 404 and missing_paper:
                raise ServiceError(404, "paper_not_found", "Paper was not found in OpenAlex")
            if cursor_paging and response.status_code == 400:
                raise ServiceError(422, "invalid_cursor", "OpenAlex rejected the pagination cursor")
            if cursor_paging and response.status_code == 401 and not self.settings.openalex_api_key:
                raise ServiceError(
                    503,
                    "openalex_key_required",
                    "OpenAlex requires a backend OPENALEX_API_KEY for this pagination request",
                )
            if not response.is_success:
                raise ServiceError(502, "openalex_error", "OpenAlex rejected the request")
            try:
                payload = response.json()
                if not isinstance(payload, dict):
                    raise ValueError("Expected an object")
                return payload
            except ValueError:
                raise self._invalid_response() from None
        raise AssertionError("Retry loop exhausted unexpectedly")
