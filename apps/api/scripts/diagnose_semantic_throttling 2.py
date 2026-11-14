"""Explicit low-volume diagnostic: 60s quiet period, >=5s spacing, no retries."""

import asyncio
import json
import os
import subprocess
import time
from datetime import UTC, datetime
from pathlib import Path

import httpx

from app.core.config import Settings
from app.core.errors import ServiceError
from app.services.citation_contexts import CitationContextService, _retry_delay

OUTPUT = Path(__file__).resolve().parents[3] / ".cache/live-citations/throttling.json"
HEADERS = {
    "date",
    "retry-after",
    "server",
    "age",
    "via",
    "x-cache",
    "cache-control",
    "x-amzn-requestid",
    "x-amz-cf-id",
    "x-amz-cf-pop",
    "cf-ray",
}


def processes():
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "@(Get-CimInstance Win32_Process | Where-Object { $_.Name -match "
            "'python|uvicorn|uv.exe' } | Select-Object ProcessId,ParentProcessId,Name) "
            "| ConvertTo-Json -Compress",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None


async def main():
    settings = Settings()
    if not settings.semantic_scholar_api_key.strip():
        print("Missing local key; no requests made.")
        return
    report = {
        "started_at": datetime.now(UTC).isoformat(),
        "pid": os.getpid(),
        "processes_before": processes(),
        "quiet_seconds": 60,
        "requests": [],
    }
    others = report["processes_before"]
    if others is None:
        raise SystemExit("Cannot verify process isolation; no requests made.")
    if isinstance(others, dict):
        others = [others]
    print(
        json.dumps({"pid": os.getpid(), "parent_pid": os.getppid(), "processes": others}),
        flush=True,
    )
    # Windows venv python.exe may be a launcher waiting for this interpreter child.
    if any(
        p["ProcessId"] not in (os.getpid(), os.getppid()) and "python" in p["Name"].lower()
        for p in others
    ):
        raise SystemExit("Another Python process is active; no requests made.")
    print("Isolation checked; allowing 60 seconds of local quiet time.", flush=True)
    await asyncio.sleep(30)
    await asyncio.sleep(30)

    class DiagnosticService(CitationContextService):
        async def _send(self, provider, url, params, headers):
            assert provider == "semantic_scholar"
            assert headers.get("x-api-key") == settings.semantic_scholar_api_key
            started = time.monotonic()
            stamp = datetime.now(UTC).isoformat()
            try:
                response = await super()._send(provider, url, params, headers)
            except httpx.TransportError:
                raise ServiceError(
                    503, "diagnostic_transport_error", "Diagnostic transport failure; no retry"
                ) from None
            safe_headers = {
                k: v
                for k, v in response.headers.items()
                if (k in HEADERS or "ratelimit" in k or k.startswith("x-quota"))
                and settings.semantic_scholar_api_key not in v
            }
            report["requests"].append(
                {
                    "utc": stamp,
                    "start_monotonic": started,
                    "seconds": time.monotonic() - started,
                    "path": response.request.url.path,
                    "status": response.status_code,
                    "authenticated": True,
                    "headers": safe_headers,
                }
            )
            print(json.dumps(report["requests"][-1]), flush=True)
            if response.status_code == 429:
                # Keep the production scheduler/cooldown; suppress automatic diagnostic retries.
                self.diagnostic_retry_after = _retry_delay(response, 0)
                raise ServiceError(503, "diagnostic_429", "Diagnostic stopped this attempt")
            if response.is_error:
                raise ServiceError(503, "diagnostic_http_error", "Diagnostic error; no retry")
            return response

    async with httpx.AsyncClient() as client:
        service = DiagnosticService(client, settings)
        paths = [
            "paper/DOI:10.18653%2Fv1%2FD19-1410",
            "paper/DOI:10.18653%2Fv1%2FN18-1202",
            "paper/156d217b0a911af97fa1b5a71dc909ccef7a8028/references",
            "paper/DOI:10.18653%2Fv1%2FD19-1410",
            "paper/DOI:10.18653%2Fv1%2FN18-1202",
        ]
        for path in paths:
            if report["requests"]:
                delay = max(5.0, getattr(service, "diagnostic_retry_after", 0))
                if delay > 60:
                    report["stop_reason"] = "long_retry_after_no_early_retry"
                    break
                await asyncio.sleep(delay)
            params = {"fields": "paperId,externalIds"}
            if path.endswith("/references"):
                params = {"fields": "contexts,externalIds", "limit": 1, "offset": 0}
            try:
                await service._get("semantic_scholar", path, params)
            except ServiceError as exc:
                if exc.code != "diagnostic_429":
                    report["stop_reason"] = exc.code
                    break
            if sum(r["status"] == 429 for r in report["requests"]) >= 2:
                report["stop_reason"] = "two_429_responses_volume_cap"
                break
    report["processes_after"] = processes()
    report["finished_at"] = datetime.now(UTC).isoformat()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(report, indent=2)
    assert settings.semantic_scholar_api_key not in encoded
    OUTPUT.write_text(encoded + "\n", encoding="utf-8")
    print("Saved sanitized diagnostic evidence.")


if __name__ == "__main__":
    asyncio.run(main())
