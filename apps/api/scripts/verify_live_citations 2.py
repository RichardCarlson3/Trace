"""Explicit authenticated live verification; never run as part of the offline tests.

Run from the repository root:
uv run --project apps/api python apps/api/scripts/verify_live_citations.py
"""

import asyncio
import json
import statistics
import time
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError
from app.schemas.citation_contexts import CitationPair
from app.schemas.contracts import normalize_work_id
from app.services.citation_contexts import CitationContextService, classify_contexts
from app.services.inference import InferenceService
from app.services.openalex import OpenAlexService

OUTPUT = Path(__file__).resolve().parents[3] / ".cache/live-citations/report.json"
# Publication DOIs are resolved live; no passages or target relationships are fixtures.
SEEDS = [
    "10.18653/v1/D19-1410",
    "10.18653/v1/N18-1202",
    "10.18653/v1/2020.acl-main.703",
    "10.1093/bioinformatics/btz682",
]


def summary(values):
    return {
        "count": len(values),
        "median_seconds": round(statistics.median(values), 4) if values else None,
        "max_seconds": round(max(values), 4) if values else None,
    }


async def verify():
    settings = Settings()
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "authenticated": bool(settings.semantic_scholar_api_key.strip()),
        "enabled": settings.semantic_scholar_enabled,
        "method": (
            "Four NLP/biomedical NLP publication seeds; first seven OpenAlex referenced_works "
            "IDs per seed "
            "in returned order. Selected before checking Semantic Scholar coverage. "
            "OpenAlex direction and exact DOI mappings independently checked. "
            "Cold service caches; mode=live excludes bundled examples."
        ),
        "requests": [],
        "relationships": [],
    }
    if not report["authenticated"] or not report["enabled"]:
        report["blocked"] = "Configure the local API key and enable Semantic Scholar."
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(report["blocked"])
        return

    phase = "discovery"

    async def before(request):
        request.extensions["verification_start"] = time.monotonic()

    async def after(response):
        request = response.request
        report["requests"].append(
            {
                "provider": (
                    "semantic_scholar"
                    if request.url.host == "api.semanticscholar.org"
                    else "openalex"
                ),
                "phase": phase,
                "path": request.url.path,
                "status": response.status_code,
                "started_monotonic": request.extensions["verification_start"],
                "seconds": time.monotonic() - request.extensions["verification_start"],
                "authenticated": "x-api-key" in request.headers,
            }
        )

    def save():
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")

    async with httpx.AsyncClient(event_hooks={"request": [before], "response": [after]}) as client:
        service = CitationContextService(client, settings)
        inference = InferenceService(settings.model_artifact_dir)
        candidates = []
        for doi in SEEDS:
            matches = await service._get(
                "openalex",
                "works",
                {"filter": f"doi:{doi}", "select": "id,doi,title,referenced_works"},
            )
            if not matches or len(matches.get("results", [])) != 1:
                continue
            work = matches["results"][0]
            citing_id = normalize_work_id(work["id"])
            for target in work.get("referenced_works", [])[:7]:
                candidates.append((citing_id, normalize_work_id(target), work["title"]))
        report["candidate_count"] = len(candidates)
        save()
        phase = "retrieval"
        for citing, cited, title in candidates:
            pair = CitationPair(citing_paper_id=citing, cited_paper_id=cited)
            row = {
                **pair.model_dump(),
                "citing_title": title,
                "openalex_outbound_reference_verified": True,
            }
            count = len(report["requests"])
            started = time.monotonic()
            try:
                result = await service.retrieve(pair, mode="live")
                row["retrieval_seconds"] = time.monotonic() - started
                classified = await asyncio.to_thread(classify_contexts, result, inference)
                row.update(
                    mapping_succeeded=(
                        result.citing_mapping.verified and result.cited_mapping.verified
                    ),
                    relationship_found=result.relationship_found,
                    status=result.status,
                    origin=result.origin,
                    passage_count=len(result.contexts),
                    classified_passages=sum(
                        c.classification is not None for c in classified.contexts
                    ),
                    result=classified.model_dump(mode="json"),
                )
            except ServiceError as exc:
                row.update(status="upstream_error", error_code=exc.code)
            row["end_to_end_seconds"] = time.monotonic() - started
            calls = report["requests"][count:]
            row["semantic_scholar_requests"] = sum(
                c["provider"] == "semantic_scholar" for c in calls
            )
            row["openalex_requests"] = sum(c["provider"] == "openalex" for c in calls)
            row["http_errors"] = [c["status"] for c in calls if c["status"] >= 400]
            report["relationships"].append(row)
            save()
            print(json.dumps({k: v for k, v in row.items() if k != "result"}), flush=True)

        phase = "repeat"
        repeat_count = len(report["requests"])
        repeat_start = time.monotonic()
        for citing, cited, _ in candidates:
            await service.retrieve(CitationPair(citing_paper_id=citing, cited_paper_id=cited))
        report["repeat"] = {
            "relationships": len(candidates),
            "upstream_requests": len(report["requests"]) - repeat_count,
            "seconds": time.monotonic() - repeat_start,
        }
        phase = "search_regression"
        search = await OpenAlexService(client, settings).search("sentence bert", 1, 2)
        report["openalex_search"] = {
            "total": search.total,
            "returned_ids": [p.id for p in search.papers],
        }
        report["caches"] = {
            name: {"hits": cache.hits, "misses": cache.misses, "coalesced": cache.coalesced}
            for name, cache in [
                ("mappings", service._mappings),
                ("reference_pages", service._references),
            ]
        }
    rows = report["relationships"]
    ss_calls = [c for c in report["requests"] if c["provider"] == "semantic_scholar"]
    starts = [c["started_monotonic"] for c in ss_calls]
    report["summary"] = {
        "unique_relationships": len({(r["citing_paper_id"], r["cited_paper_id"]) for r in rows}),
        "mapped": sum(r.get("mapping_succeeded", False) for r in rows),
        "with_contexts": sum(r.get("passage_count", 0) > 0 for r in rows),
        "classified": sum(r.get("classified_passages", 0) > 0 for r in rows),
        "coverage_percent": 100 * sum(r.get("passage_count", 0) > 0 for r in rows) / len(rows)
        if rows
        else None,
        "semantic_scholar_requests": len(ss_calls),
        "http_429": sum(c["status"] == 429 for c in ss_calls),
        "statuses": dict(Counter(r["status"] for r in rows)),
        "semantic_request_latency": summary([c["seconds"] for c in ss_calls]),
        "retrieval_latency": summary(
            [r["retrieval_seconds"] for r in rows if "retrieval_seconds" in r]
        ),
        "end_to_end_latency": summary([r["end_to_end_seconds"] for r in rows]),
        "minimum_semantic_start_spacing_seconds": min(
            (b - a for a, b in zip(starts, starts[1:])), default=None
        ),
    }
    report["finished_at"] = datetime.now(UTC).isoformat()
    save()
    print(json.dumps(report["summary"], indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(verify())
    except (httpx.HTTPError, ServiceError) as exc:
        # Do not print upstream bodies, request headers or exception diagnostics.
        print(f"Verification interrupted: {getattr(exc, 'code', 'transport_error')}")
        raise SystemExit(1) from None
