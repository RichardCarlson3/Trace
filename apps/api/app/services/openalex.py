import asyncio

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.contracts import Paper, SearchResponse


def normalize_paper(work: dict) -> Paper:
    inverted = work.get("abstract_inverted_index")
    abstract = None
    if inverted:
        tokens = sorted(
            (position, word) for word, positions in inverted.items() for position in positions
        )
        abstract = " ".join(word for _, word in tokens)
    location = work.get("primary_location") or {}
    return Paper(
        id=work["id"],
        doi=work.get("doi"),
        title=work.get("display_name") or work.get("title") or "Untitled work",
        year=work.get("publication_year"),
        authors=[
            entry["author"]["display_name"]
            for entry in work.get("authorships", [])
            if (entry.get("author") or {}).get("display_name")
        ],
        abstract=abstract,
        cited_by_count=work.get("cited_by_count") or 0,
        landing_page_url=location.get("landing_page_url"),
    )


class OpenAlexService:
    """Owns provider I/O. Future metadata/references/citations methods belong here."""

    def __init__(self, client: httpx.AsyncClient, settings: Settings):
        self.client = client
        self.settings = settings

    async def search(self, query: str, page: int, per_page: int) -> SearchResponse:
        params = {"search": query, "page": page, "per-page": per_page}
        headers = {}
        if self.settings.openalex_api_key:
            headers["Authorization"] = f"Bearer {self.settings.openalex_api_key}"
        for attempt in range(3):
            try:
                response = await self.client.get(
                    f"{self.settings.openalex_base_url.rstrip('/')}/works",
                    params=params,
                    headers=headers,
                    timeout=10.0,
                )
            except httpx.TransportError:
                if attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise ServiceError(
                    502, "openalex_unavailable", "OpenAlex could not be reached"
                ) from None
            if response.status_code == 429 or response.status_code >= 500:
                if attempt < 2:
                    await asyncio.sleep(0.25 * 2**attempt)
                    continue
                raise ServiceError(
                    503, "openalex_unavailable", "OpenAlex is busy. Try again shortly."
                )
            if response.is_error:
                raise ServiceError(502, "openalex_error", "OpenAlex rejected the search request")
            try:
                payload = response.json()
                return SearchResponse(
                    papers=[normalize_paper(work) for work in payload["results"]],
                    total=payload["meta"]["count"],
                    page=page,
                    per_page=per_page,
                )
            except (ValueError, KeyError, TypeError):
                raise ServiceError(
                    502, "openalex_invalid_response", "OpenAlex returned invalid data"
                ) from None
        raise AssertionError("Retry loop exhausted unexpectedly")
