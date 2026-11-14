"""Offline, real-clock ASGI baseline. Run explicitly; never imported by application startup."""

import argparse
import asyncio
import hashlib
import importlib
import json
import math
import platform
import statistics
import sys
from collections import Counter
from contextlib import ExitStack, asynccontextmanager, contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from time import perf_counter
from unittest.mock import patch

import httpx

from app.core.config import Settings, get_settings
from app.services.citation_contexts import CitationContextService

API_ROOT = Path(__file__).resolve().parents[1]
FIXTURE = API_ROOT / "tests/fixtures/performance/provider_responses.json"
TEI_ROOT = API_ROOT / "tests/fixtures/tei"
PAIR = {"citing_paper_id": "W2982399380", "cited_paper_id": "W1614298861", "mode": "live"}
SCENARIOS = ("health", "search", "neighbors", "classification", "health_under_load")


@dataclass(frozen=True)
class Config:
    concurrency: tuple[int, ...] = (1, 5, 10)
    requests: int = 30
    scenarios: tuple[str, ...] = SCENARIOS
    provider_delay_ms: float = 10
    provider_status: int = 200
    request_timeout_seconds: float = 10
    case_timeout_seconds: float = 30
    total_timeout_seconds: float = 120
    artifact_dir: Path = API_ROOT / "artifacts"

    def __post_init__(self):
        if (
            not self.concurrency
            or len(self.concurrency) > 6
            or len(set(self.concurrency)) != len(self.concurrency)
            or any(type(n) is not int or not 1 <= n <= 20 for n in self.concurrency)
        ):
            raise ValueError("Choose 1–6 unique concurrency levels between 1 and 20")
        if type(self.requests) is not int or not max(self.concurrency) <= self.requests <= 200:
            raise ValueError("Requests must be between the highest concurrency and 200")
        if (
            not self.scenarios
            or len(set(self.scenarios)) != len(self.scenarios)
            or any(s not in SCENARIOS for s in self.scenarios)
        ):
            raise ValueError("Choose unique scenarios from: " + ", ".join(SCENARIOS))
        for value, minimum, maximum in (
            (self.provider_delay_ms, 0, 1000),
            (self.request_timeout_seconds, 0.01, 60),
            (self.case_timeout_seconds, 0.01, 120),
            (self.total_timeout_seconds, 0.01, 300),
        ):
            if not math.isfinite(value) or not minimum <= value <= maximum:
                raise ValueError("Delay or timeout is outside its bounded range")
        if self.provider_status not in (200, 403):
            raise ValueError("Provider status must be 200 or the controlled failure status 403")


class OfflineViolation(RuntimeError):
    pass


@contextmanager
def block_network():
    """Defense in depth if a future service accidentally bypasses the mock client.

    Process-wide patches are only appropriate for this standalone benchmark, not
    for concurrent use inside a running application. Unix socket pairs used by
    asyncio remain available; outbound connects and DNS are blocked.
    """
    blocked = Counter()

    def deny(*args, **kwargs):
        blocked["attempts"] += 1
        raise OfflineViolation("The offline benchmark blocked a real network attempt")

    async def deny_async(*args, **kwargs):
        return deny()

    with ExitStack() as stack:
        for target in (
            "socket.socket.connect",
            "socket.socket.connect_ex",
            "socket.create_connection",
            "socket.getaddrinfo",
            "httpx.HTTPTransport.handle_request",
        ):
            stack.enter_context(patch(target, deny))
        stack.enter_context(patch("httpx.AsyncHTTPTransport.handle_async_request", deny_async))
        yield blocked


class FixtureProvider:
    """Only explicitly recognized OpenAlex fixture requests can receive data."""

    def __init__(self, config: Config):
        self.config = config
        self.fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        if (
            self.fixture["fixture_kind"]
            != "synthetic_offline_benchmark_metadata_not_research_records"
        ):
            raise ValueError("Expected clearly labeled synthetic benchmark metadata")
        recorded = json.loads((TEI_ROOT / "works.json").read_text(encoding="utf-8"))
        self.works = {
            wid: recorded[wid] for wid in (PAIR["citing_paper_id"], PAIR["cited_paper_id"])
        }
        self.xml = (TEI_ROOT / "bart.xml").read_bytes()
        self.calls = Counter()
        self.unexpected = 0
        self.active = 0
        self.peak = 0
        self.hold: asyncio.Event | None = None
        self.all_started = asyncio.Event()
        self.waiting_for = 1

    def response(self, request: httpx.Request):
        url, params = request.url, request.url.params
        if request.method == "GET" and url.scheme == "https":
            if (
                url.host == "content.openalex.org"
                and url.path == f"/works/{PAIR['citing_paper_id']}.grobid-xml"
            ):
                return "tei_document", httpx.Response(200, content=self.xml)
            if url.host == "api.openalex.org":
                wid = url.path.removeprefix("/works/")
                if url.path.startswith("/works/") and wid in self.works:
                    return "recorded_metadata", httpx.Response(200, json=self.works[wid])
                if url.path.startswith("/works/") and wid in self.fixture["works"]:
                    return "synthetic_metadata", httpx.Response(
                        200, json=self.fixture["works"][wid]
                    )
                if url.path == "/works":
                    if params.get("search") == self.fixture["query"]:
                        kind, wid = "search", self.fixture["seed_id"]
                    elif params.get("filter") == f"ids.openalex:{self.fixture['reference_id']}":
                        kind, wid = "references", self.fixture["reference_id"]
                    elif params.get("filter") == f"cites:{self.fixture['seed_id']}":
                        kind, wid = "citations", self.fixture["citing_id"]
                    else:
                        kind, wid = "", ""
                    if kind:
                        return kind, httpx.Response(
                            200,
                            json={
                                "results": [self.fixture["works"][wid]],
                                "meta": {"count": 1, "next_cursor": None},
                            },
                        )
        self.unexpected += 1
        raise OfflineViolation("Unrecognized mocked provider request; no network fallback exists")

    async def handle(self, request: httpx.Request):
        kind, response = self.response(request)
        self.calls[kind] += 1
        self.active += 1
        self.peak = max(self.peak, self.active)
        if self.active >= self.waiting_for:
            self.all_started.set()
        try:
            if self.hold is not None:
                await self.hold.wait()
            await asyncio.sleep(self.config.provider_delay_ms / 1000)
            return response if self.config.provider_status == 200 else httpx.Response(403)
        finally:
            self.active -= 1


def benchmark_settings(config: Config):
    # Supply every field explicitly so neither .env nor shell credentials/config
    # can alter this isolated run. No database, training, or provider key is needed.
    values = {
        name: field.get_default(call_default_factory=True)
        for name, field in Settings.model_fields.items()
    }
    values.update(
        app_env="benchmark",
        database_url="",
        openalex_api_key="offline-fixture-key",
        semantic_scholar_api_key="",
        semantic_scholar_enabled=False,
        openalex_tei_enabled=True,
        model_artifact_dir=config.artifact_dir,
    )
    return Settings(_env_file=None, **values)


@asynccontextmanager
async def offline_app(config: Config, provider: FixtureProvider):
    settings = benchmark_settings(config)
    # app.main constructs a module-level app on first import. Guard that path too
    # so standalone runs do not read the developer's backend environment file.
    with patch("app.core.config.get_settings", return_value=settings) as temporary_settings:
        module = importlib.import_module("app.main")
        if module.get_settings is temporary_settings:
            module.get_settings = get_settings
        create_app = module.create_app
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.MockTransport(provider.handle), trust_env=False
        ) as upstream:
            app.state.http = upstream
            app.state.citation_contexts = CitationContextService(upstream, settings)
            transport = httpx.ASGITransport(app=app, raise_app_exceptions=False)
            async with httpx.AsyncClient(
                transport=transport, base_url="http://benchmark.test", trust_env=False
            ) as client:
                yield client


@dataclass
class Sample:
    latency_ms: float
    status: int | None
    error: str | None
    unavailable: bool = False
    model_versions: tuple[str, ...] = ()
    provider_active_at_start: bool = False


async def request_sample(client, scenario, config, provider):
    started, active = perf_counter(), provider.active > 0
    try:
        async with asyncio.timeout(config.request_timeout_seconds):
            if scenario == "classification":
                response = await client.post("/api/v1/citation-contexts/classify", json=PAIR)
            elif scenario == "search":
                response = await client.get(
                    "/api/v1/papers/search", params={"q": provider.fixture["query"]}
                )
            elif scenario == "neighbors":
                response = await client.get(
                    f"/api/v1/papers/{provider.fixture['seed_id']}/neighbors", params={"limit": 2}
                )
            else:
                response = await client.get("/api/v1/health")
        elapsed = (perf_counter() - started) * 1000
        body = response.json()
        error = (
            body.get("error", {}).get("code", f"http_{response.status_code}")
            if response.is_error
            else None
        )
        unavailable = error == "model_unavailable"
        versions = ()
        if scenario == "classification" and response.is_success:
            classified = [
                c["classification"] for c in body.get("contexts", []) if c.get("classification")
            ]
            if not classified:
                error, unavailable = "classification_unavailable", True
            versions = tuple(sorted({c["model_version"] for c in classified}))
        return Sample(elapsed, response.status_code, error, unavailable, versions, active)
    except TimeoutError:
        return Sample(
            (perf_counter() - started) * 1000,
            None,
            "request_timeout",
            provider_active_at_start=active,
        )
    except Exception as exc:
        return Sample(
            (perf_counter() - started) * 1000,
            None,
            type(exc).__name__,
            provider_active_at_start=active,
        )


def summarize(samples, scheduled, elapsed, peak, timed_out=False):
    latencies = sorted(sample.latency_ms for sample in samples)
    cancelled = scheduled - len(samples)
    errors = Counter(s.error for s in samples if s.error)
    if cancelled:
        errors["case_timeout_cancelled"] = cancelled
    return {
        "request_count": scheduled,
        "completed_requests": len(samples),
        "cancelled_requests": cancelled,
        "success_count": sum(s.error is None for s in samples),
        "error_count": sum(errors.values()),
        "error_codes": dict(errors),
        "classification_unavailable_count": sum(s.unavailable for s in samples),
        "status_counts": dict(Counter(str(s.status) for s in samples if s.status is not None)),
        "median_ms": statistics.median(latencies) if latencies else None,
        "p95_ms": latencies[math.ceil(0.95 * len(latencies)) - 1] if latencies else None,
        "max_ms": max(latencies) if latencies else None,
        "elapsed_seconds": elapsed,
        "requests_per_second": len(samples) / elapsed if elapsed > 0 else 0,
        "peak_in_flight": peak,
        "case_timed_out": timed_out,
        "requests_overlapping_provider_work": sum(s.provider_active_at_start for s in samples),
        "model_versions": sorted({v for s in samples for v in s.model_versions}),
    }


async def run_batch(client, provider, config, scenario, count, concurrency):
    samples, active, peak = {}, 0, 0
    started = perf_counter()

    async def worker(worker_id):
        nonlocal active, peak
        for index in range(worker_id, count, concurrency):
            active += 1
            peak = max(peak, active)
            try:
                samples[index] = await request_sample(client, scenario, config, provider)
            finally:
                active -= 1

    tasks = [asyncio.create_task(worker(i)) for i in range(min(count, concurrency))]
    timed_out = False
    try:
        async with asyncio.timeout(config.case_timeout_seconds):
            await asyncio.gather(*tasks)
    except TimeoutError:
        timed_out = True
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
    return summarize(
        [samples[i] for i in sorted(samples)], count, perf_counter() - started, peak, timed_out
    )


def provider_counts(provider, before):
    counts = provider.calls - before
    return {
        "provider_request_count": sum(counts.values()),
        "provider_requests_by_kind": dict(counts),
    }


async def run_case(config, scenario, concurrency, rows, providers):
    provider = FixtureProvider(config)
    providers.append(provider)
    async with offline_app(config, provider) as client:
        if scenario == "health_under_load":
            provider.hold, provider.waiting_for = asyncio.Event(), concurrency
            background = asyncio.create_task(
                run_batch(client, provider, config, "search", concurrency, concurrency)
            )
            try:
                async with asyncio.timeout(config.case_timeout_seconds):
                    await provider.all_started.wait()
                    result = await run_batch(client, provider, config, "health", config.requests, 1)
            finally:
                provider.hold.set()
                background_result = await background
            rows.append(
                {
                    "scenario": scenario,
                    "phase": "providers_held",
                    "concurrency": concurrency,
                    "probe_concurrency": 1,
                    **result,
                    **provider_counts(provider, Counter()),
                    "background_search": background_result,
                    "overlap_verified": result["requests_overlapping_provider_work"]
                    == result["request_count"],
                    "provider_peak_in_flight": provider.peak,
                }
            )
            return
        cold_success = False
        for phase, count in (("cold", concurrency), ("warm", config.requests)):
            before, provider.peak = provider.calls.copy(), 0
            result = await run_batch(client, provider, config, scenario, count, concurrency)
            rows.append(
                {
                    "scenario": scenario,
                    "phase": phase,
                    "concurrency": concurrency,
                    "cache_precondition": "fresh_app"
                    if phase == "cold"
                    else "primed"
                    if cold_success
                    else "not_established",
                    **result,
                    **provider_counts(provider, before),
                    "provider_peak_in_flight": provider.peak,
                }
            )
            cold_success = result["success_count"] > 0


async def run_benchmark(config: Config):
    rows, providers = [], []
    report = {
        "schema_version": 1,
        "measurement_mode": "offline_in_process_asgi_real_clock",
        "started_at": datetime.now(UTC).isoformat(),
        "config": {**asdict(config), "artifact_dir": str(config.artifact_dir)},
        "environment": {
            "python": platform.python_version(),
            "platform": platform.system(),
            **{p: version(p) for p in ("fastapi", "httpx", "scikit-learn")},
        },
        "fixture_sha256": {},
        "classification_path": (
            "recorded BART TEI fallback; Semantic Scholar disabled; real local model"
        ),
        "results": rows,
        "run_error": None,
    }
    with block_network() as blocked:
        try:
            report["fixture_sha256"] = {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in (FIXTURE, TEI_ROOT / "works.json", TEI_ROOT / "bart.xml")
            }
            async with asyncio.timeout(config.total_timeout_seconds):
                for concurrency in config.concurrency:
                    for scenario in config.scenarios:
                        await run_case(config, scenario, concurrency, rows, providers)
        except TimeoutError:
            report["run_error"] = "benchmark_deadline_exceeded"
        except Exception as exc:
            report["run_error"] = type(exc).__name__
        report["blocked_network_attempts"] = blocked["attempts"]
    report["unexpected_provider_requests"] = sum(p.unexpected for p in providers)
    report["valid_run"] = not (
        report["run_error"]
        or report["blocked_network_attempts"]
        or report["unexpected_provider_requests"]
    )
    report["all_requests_successful"] = (
        bool(rows)
        and report["valid_run"]
        and all(
            r["error_count"] == 0
            and r.get("background_search", {}).get("error_count", 0) == 0
            and r.get("overlap_verified", True)
            for r in rows
        )
    )
    return report


def print_summary(report):
    print("OFFLINE BACKEND BASELINE — in-process ASGI; not production latency")
    print("Cold: one fresh concurrent wave. Warm: repeated requests on that same app.")
    print(
        f"{'Scenario / phase':34} {'C':>3} {'Done':>5} {'Err':>4} "
        f"{'Median ms':>10} {'P95 ms':>10} {'Req/s':>9} {'Provider':>8}"
    )
    for row in report["results"]:
        median = f"{row['median_ms']:.2f}" if row["median_ms"] is not None else "n/a"
        p95 = f"{row['p95_ms']:.2f}" if row["p95_ms"] is not None else "n/a"
        print(
            f"{row['scenario'] + ' / ' + row['phase']:34} {row['concurrency']:3} "
            f"{row['completed_requests']:5} {row['error_count']:4} {median:>10} {p95:>10} "
            f"{row['requests_per_second']:9.1f} {row['provider_request_count']:8}"
        )
        if row["error_codes"]:
            print("  Errors:", json.dumps(row["error_codes"], sort_keys=True))
        if row["classification_unavailable_count"]:
            print("  Classification unavailable; no replacement predictions were generated.")
        if "overlap_verified" in row:
            print(
                f"  Health/provider overlap verified: {row['overlap_verified']}; "
                f"background search errors: {row['background_search']['error_count']}"
            )
    print(
        f"Valid run: {report['valid_run']}; "
        f"all requests successful: {report['all_requests_successful']}"
    )
    print(
        f"Blocked network attempts: {report['blocked_network_attempts']}; "
        f"unexpected fixture requests: {report['unexpected_provider_requests']}"
    )
    if report["run_error"]:
        print("Run error:", report["run_error"])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--concurrency", type=int, nargs="+", default=[1, 5, 10])
    parser.add_argument(
        "--requests", type=int, default=30, help="Requests per warm batch/health probe"
    )
    parser.add_argument("--scenarios", nargs="+", choices=SCENARIOS, default=list(SCENARIOS))
    parser.add_argument("--provider-delay-ms", type=float, default=10)
    parser.add_argument("--provider-status", type=int, choices=(200, 403), default=200)
    parser.add_argument("--request-timeout-seconds", type=float, default=10)
    parser.add_argument("--case-timeout-seconds", type=float, default=30)
    parser.add_argument("--total-timeout-seconds", type=float, default=120)
    parser.add_argument(
        "--artifact-dir",
        type=Path,
        default=API_ROOT / "artifacts",
        help="Existing trusted local model directory only",
    )
    parser.add_argument(
        "--json",
        type=Path,
        help="Write a report to a NEW file; existing files are never overwritten",
    )
    args = parser.parse_args(argv)
    try:
        config = Config(
            concurrency=tuple(args.concurrency),
            requests=args.requests,
            scenarios=tuple(args.scenarios),
            provider_delay_ms=args.provider_delay_ms,
            provider_status=args.provider_status,
            artifact_dir=args.artifact_dir.resolve(),
            request_timeout_seconds=args.request_timeout_seconds,
            case_timeout_seconds=args.case_timeout_seconds,
            total_timeout_seconds=args.total_timeout_seconds,
        )
    except ValueError as exc:
        parser.error(str(exc))
    report = asyncio.run(run_benchmark(config))
    print_summary(report)
    if args.json:
        try:
            with args.json.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2, allow_nan=False)
                handle.write("\n")
        except OSError as exc:
            print(f"Report not written: {type(exc).__name__}", file=sys.stderr)
            return 2
    return 0 if report["all_requests_successful"] else 1 if report["valid_run"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
