"""Offline benchmark regressions; no production files or real providers are modified."""

import asyncio
import importlib.util
import json
import socket
import sys
from dataclasses import replace
from pathlib import Path

import httpx
import pytest

from app.services.inference import InferenceService
from app.services.openalex_tei import parse_document

SPEC = importlib.util.spec_from_file_location(
    "offline_benchmark_api", Path(__file__).parents[1] / "scripts/benchmark_api.py"
)
bench = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bench
SPEC.loader.exec_module(bench)


def config(**overrides):
    return replace(bench.Config(concurrency=(2,), requests=4, provider_delay_ms=2), **overrides)


def test_measurements_include_failures_and_use_nearest_rank_percentile():
    samples = [bench.Sample(n * 10, 200, None) for n in range(1, 10)]
    samples.append(bench.Sample(100, 503, "model_unavailable", True))
    summary = bench.summarize(samples, 12, 2, 3, timed_out=True)
    assert summary["request_count"] == 12
    assert summary["completed_requests"] == 10
    assert summary["cancelled_requests"] == 2
    assert summary["success_count"] == 9 and summary["error_count"] == 3
    assert summary["error_codes"] == {"model_unavailable": 1, "case_timeout_cancelled": 2}
    assert summary["classification_unavailable_count"] == 1
    assert summary["median_ms"] == 55 and summary["p95_ms"] == 100
    assert summary["requests_per_second"] == 5
    assert summary["peak_in_flight"] == 3
    empty = bench.summarize([], 1, 1, 1, timed_out=True)
    assert empty["median_ms"] is None and empty["p95_ms"] is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"concurrency": ()},
        {"concurrency": (1, 1)},
        {"concurrency": (21,)},
        {"requests": 201},
        {"requests": 1},
        {"provider_delay_ms": float("nan")},
        {"provider_delay_ms": 1001},
        {"total_timeout_seconds": float("inf")},
        {"scenarios": ("live",)},
        {"provider_status": 500},
    ],
)
def test_configuration_is_bounded(overrides):
    with pytest.raises(ValueError):
        config(**overrides)


def test_real_search_expansion_and_health_routes_overlap_offline(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "must-not-use-this")
    monkeypatch.setenv("OPENALEX_BASE_URL", "https://must-not-use-this.invalid")
    monkeypatch.setenv("OPENALEX_API_KEY", "must-not-appear-in-report")
    report = asyncio.run(
        bench.run_benchmark(
            config(
                concurrency=(1, 2),
                provider_delay_ms=10,
                scenarios=("search", "neighbors", "health", "health_under_load"),
            )
        )
    )
    assert report["valid_run"] and report["all_requests_successful"]
    assert len(report["results"]) == 14
    assert report["blocked_network_attempts"] == report["unexpected_provider_requests"] == 0
    assert "must-not-appear-in-report" not in json.dumps(report)
    for row in report["results"]:
        assert row["success_count"] == row["request_count"]
        assert row["median_ms"] <= row["p95_ms"] <= row["max_ms"]
        if row["scenario"] == "search":
            assert row["provider_request_count"] == row["request_count"]
            assert row["provider_peak_in_flight"] == row["concurrency"]
            assert row["peak_in_flight"] == row["concurrency"]
        elif row["scenario"] == "neighbors":
            assert row["provider_request_count"] == 3 * row["request_count"]
            assert row["provider_requests_by_kind"] == {
                "synthetic_metadata": row["request_count"],
                "references": row["request_count"],
                "citations": row["request_count"],
            }
        elif row["scenario"] == "health":
            assert row["provider_request_count"] == 0
        else:
            assert row["overlap_verified"]
            assert row["requests_overlapping_provider_work"] == row["request_count"]
            assert row["background_search"]["success_count"] == row["concurrency"]


def test_classification_uses_genuine_recorded_text_real_model_and_warm_cache(monkeypatch):
    texts = []
    original = InferenceService.classify

    def capture(self, text):
        texts.append(text)
        return original(self, text)

    monkeypatch.setattr(InferenceService, "classify", capture)
    report = asyncio.run(bench.run_benchmark(config(scenarios=("classification",))))
    assert report["valid_run"]
    cold, warm = report["results"]
    assert cold["provider_request_count"] == 3
    assert warm["provider_request_count"] == 0
    provider = bench.FixtureProvider(config())
    document = parse_document(provider.xml, provider.works[bench.PAIR["citing_paper_id"]])
    genuine_sentences = {sentence.text for sentence in document.sentences}
    assert len(texts) == 6 and all(text in genuine_sentences for text in texts)
    if cold["classification_unavailable_count"]:
        # A checkout without compatible artifacts remains a valid measured result.
        assert not report["all_requests_successful"]
        assert cold["error_codes"] == {"model_unavailable": 2}
        assert warm["cache_precondition"] == "not_established"
    else:
        assert report["all_requests_successful"]
        assert cold["model_versions"] and warm["model_versions"] == cold["model_versions"]
        assert warm["cache_precondition"] == "primed"


def test_missing_artifacts_are_reported_without_skipping_the_real_route(tmp_path, caplog):
    report = asyncio.run(
        bench.run_benchmark(
            config(
                concurrency=(1,),
                requests=1,
                scenarios=("classification", "health"),
                artifact_dir=tmp_path,
            )
        )
    )
    assert report["valid_run"] and not report["all_requests_successful"]
    classification = [r for r in report["results"] if r["scenario"] == "classification"]
    assert all(r["classification_unavailable_count"] == 1 for r in classification)
    assert all(r["error_codes"] == {"model_unavailable": 1} for r in classification)
    assert all(r["status_counts"] == {"503": 1} for r in classification)
    assert all(not r["model_versions"] for r in classification)
    assert not list(tmp_path.iterdir())  # No downloaded/trained replacement artifacts.
    assert all(r["success_count"] == 1 for r in report["results"] if r["scenario"] == "health")


def test_controlled_provider_failure_is_not_mistaken_for_fast_success():
    report = asyncio.run(bench.run_benchmark(config(scenarios=("search",), provider_status=403)))
    assert report["valid_run"] and not report["all_requests_successful"]
    cold, warm = report["results"]
    assert cold["error_codes"] == {"openalex_error": 2}
    assert warm["error_codes"] == {"openalex_error": 4}
    assert cold["status_counts"] == {"502": 2}
    assert warm["success_count"] == 0 and warm["cache_precondition"] == "not_established"


def test_real_network_and_unrecognized_fixture_requests_are_blocked():
    async def run():
        original_dns = socket.getaddrinfo
        with bench.block_network() as blocked:
            with pytest.raises(bench.OfflineViolation):
                socket.getaddrinfo("example.invalid", 443)
            with socket.socket() as sock, pytest.raises(bench.OfflineViolation):
                sock.connect(("127.0.0.1", 9))
            with httpx.Client(trust_env=False) as client, pytest.raises(bench.OfflineViolation):
                client.get("https://example.invalid")
            async with httpx.AsyncClient(trust_env=False) as client:
                with pytest.raises(bench.OfflineViolation):
                    await client.get("https://example.invalid")
            assert blocked["attempts"] == 4
        assert socket.getaddrinfo is original_dns
        provider = bench.FixtureProvider(config())
        async with httpx.AsyncClient(transport=httpx.MockTransport(provider.handle)) as client:
            with pytest.raises(bench.OfflineViolation):
                await client.get("https://api.openalex.org/unrecognized")
        assert provider.unexpected == 1

    asyncio.run(run())


def test_a_future_service_bypassing_the_mock_invalidates_the_report(monkeypatch):
    original = bench.request_sample

    async def bypass(*args):
        async with httpx.AsyncClient(trust_env=False) as client:
            await client.get("https://example.invalid")
        return await original(*args)

    monkeypatch.setattr(bench, "request_sample", bypass)
    report = asyncio.run(bench.run_benchmark(config(scenarios=("health",))))
    assert report["blocked_network_attempts"] > 0
    assert not report["valid_run"] and report["run_error"] == "OfflineViolation"


def test_request_and_case_deadlines_report_errors_and_cancel_work():
    async def run():
        for request_timeout, case_timeout, expected in (
            (0.01, 1, "request_timeout"),
            (1, 0.01, "case_timeout_cancelled"),
        ):
            cfg = config(
                provider_delay_ms=100,
                request_timeout_seconds=request_timeout,
                case_timeout_seconds=case_timeout,
                scenarios=("search",),
            )
            provider = bench.FixtureProvider(cfg)
            with bench.block_network():
                async with bench.offline_app(cfg, provider) as client:
                    row = await bench.run_batch(client, provider, cfg, "search", 4, 2)
                    assert row["error_codes"] == {expected: 4}
                    assert row["error_count"] == 4
                    assert provider.active == 0
                    assert row["case_timed_out"] is (expected == "case_timeout_cancelled")

    asyncio.run(run())


def test_total_deadline_releases_held_background_requests():
    async def run():
        tasks_before = asyncio.all_tasks()
        report = await bench.run_benchmark(
            config(
                provider_delay_ms=100,
                total_timeout_seconds=0.02,
                scenarios=("health_under_load",),
            )
        )
        assert not report["valid_run"] and report["run_error"] == "benchmark_deadline_exceeded"
        await asyncio.sleep(0)
        assert not (asyncio.all_tasks() - tasks_before)

    asyncio.run(run())


def test_cli_prints_summary_exports_json_and_never_overwrites_existing_files(tmp_path, capsys):
    output = tmp_path / "report.json"
    args = [
        "--concurrency",
        "1",
        "--requests",
        "1",
        "--scenarios",
        "search",
        "--provider-delay-ms",
        "0",
        "--json",
        str(output),
    ]
    assert bench.main(args) == 0
    printed = capsys.readouterr().out
    assert "OFFLINE" in printed and "not production latency" in printed and "P95" in printed
    report = json.loads(output.read_text())
    assert report["schema_version"] == 1 and report["all_requests_successful"]
    assert report["fixture_sha256"]["bart.xml"]
    previous = output.read_bytes()
    assert bench.main(args) == 2
    assert output.read_bytes() == previous
    assert "FileExistsError" in capsys.readouterr().err
    assert bench.main(args[:-2] + ["--provider-status", "403"]) == 1
    with pytest.raises(SystemExit) as invalid:
        bench.main(["--concurrency", "21"])
    assert invalid.value.code == 2


def test_settings_reader_is_not_left_patched():
    from app.core.config import get_settings
    from app.main import get_settings as main_settings

    assert main_settings is get_settings
