# Backend benchmark CI

The separate `.github/workflows/backend-benchmarks.yml` runs the existing offline
benchmark and publishes a job summary plus downloadable diagnostics. It does not
change `.github/workflows/ci.yml`, the benchmark runner, application/service code,
frontend code, model artifacts, dependencies or lockfiles.

## When it runs

- Pull requests targeting **dev** or **main** when `apps/api/**`, this workflow,
  `docs/BACKEND_BENCHMARKS.md`, or this documentation changes.
- Manual `workflow_dispatch` runs, with the same fixed configuration.
- It has no push, deployment, schedule, or `pull_request_target` trigger.

To start a manual run after publishing the workflow, open **Actions → Backend
benchmarks → Run workflow**, select the branch to evaluate, and submit. GitHub
requires the workflow file to exist on the repository's default branch for
manual dispatch to be available; merging only into `dev` may not make the button
available. PR execution does not require a manual dispatch.
[GitHub workflow-dispatch documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#workflow_dispatch).

GitHub may require a maintainer to approve workflows from first-time/fork
contributors. Path-filtered workflows are skipped on unrelated changes, so do
not configure this conditional workflow as an unconditional required check
without accounting for that behavior.

## What the job does

1. Check out the evaluated revision with persisted Git credentials disabled.
2. Use the existing CI conventions: `astral-sh/setup-uv@v6`, uv `0.13.8`, Python
   3.12, and `uv sync --project apps/api --locked --group dev`.
3. Inspect the checked-out local model pair. Select scenarios using the model
   policy below and write `execution.json` before starting the benchmark.
4. Run the unchanged `apps/api/scripts/benchmark_api.py` via `uv run --offline`:
   concurrency **1, 5, 10**, **30 warm requests**, **10 ms** provider delay,
   success responses, and request/case/total deadlines of **10/30/120 seconds**.
5. Validate the resulting JSON and write a readable summary, even when the
   benchmark command failed. Failed validation makes the job fail.
6. Upload the JSON, summary, metadata and logs using an `always()` upload step.

Dependency installation can access package registries. Benchmark execution is
offline: the existing harness supplies controlled HTTP responses and blocks real
HTTP transports, DNS and socket connects. No provider credentials or production
secrets are configured. The workflow has only `contents: read` permission, does
not post PR comments, and does not access another workflow's privileged context.

## Model availability

Only the checked-out files under `apps/api/artifacts` are considered:
`citation_pipeline.joblib` and `model_metadata.json`.

| Local pair | Behavior |
| --- | --- |
| Both regular files exist | Include classification; the actual inference loader checks compatibility/checksum and loads the existing trusted model |
| Both files absent | Run health, search, neighbors and health-under-load; explicitly label classification **skipped / incomplete coverage** |
| Partial pair, directories, or broken links | Run non-classification scenarios for diagnostics, but fail CI because the existing pair is invalid |
| Both files exist but are incompatible/corrupt | Include classification and fail on the real route's unavailable/error responses |

No artifact is downloaded separately, trained, generated or replaced. Missing
models are not presented as successful classification. A passing non-model run
still shows incomplete coverage in the summary and `ci-result.json`. The raw
benchmark report contains only the scenarios actually executed; consult
`execution.json` for the selection and skip reason.

## Finding reports

Open the PR's **Offline backend benchmark report** check, or find the run under
**Actions → Backend benchmarks**. The run summary shows one row per scenario,
phase and caller level, including median/P95 latency, throughput, errors,
provider calls and verified health/provider overlap. Error details and the
classification coverage status are shown alongside the table.

Download the artifact named
`backend-benchmarks-<run_id>-<run_attempt>` from the run's **Artifacts** section.
It is retained for **7 days** and normally contains:

- `benchmark.json`: unchanged machine-readable benchmark report.
- `benchmark.log`: benchmark stdout/stderr, including real command failures.
- `execution.json`: model selection, actual scenarios, process return code and
  execution-error status.
- `summary.md`: the same report written to the GitHub job summary.
- `ci-result.json`: pass/fail, validation errors and classification coverage.

If installation or execution fails before JSON is produced, the reporting step
still creates a failed summary and CI diagnostics. It does not manufacture a
replacement benchmark report. The upload uses `if-no-files-found: error` and no
step uses `continue-on-error` to conceal failures.

Artifact/summary publication is best effort after cancellation, a hard job
timeout, or runner loss; GitHub cannot run cleanup on a runner that has stopped.
[Artifact documentation](https://github.com/actions/upload-artifact),
[job summary documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#adding-a-job-summary).

## Pass/fail policy

The reporter independently checks more than the process's exit code. It requires:

- Schema version 1, offline mode, the fixed requested configuration and fixture
  fingerprints matching the evaluated checkout.
- A completed, successful benchmark command and a valid report with no run error,
  blocked network attempts or unknown provider requests.
- Every expected scenario/concurrency/phase row exactly once (27 rows with a
  model, 21 without), with the expected request counts.
- Completed successful HTTP 200 requests, zero errors/cancellations/unavailable
  classifications, established cold/warm conditions and no case deadlines.
- Valid finite numeric metrics, coherent percentiles and provider counters.
- Every health probe overlapping held provider work, and successful background
  searches. Classification rows must name an actual returned model version.

Nonzero command exits, missing/malformed JSON, incomplete rows, incompatible
models, provider/request failures, failed health overlap and deadlines fail CI.
Partial benchmark JSON and logs are retained when available.

There are **no latency or throughput pass/fail thresholds**. Shared runners vary
in CPU scheduling and filesystem caches; very slow finite measurements can pass
when their request outcomes remain successful. Explicit request/case/run and
workflow deadlines are still enforced for bounded execution.

The job is capped at **15 minutes**; dependency installation at **5 minutes**,
benchmark step at **4 minutes**, and summary/upload steps at **2 minutes** each.
The subprocess additionally has a **210-second** guard. A newer run cancels an
older run for the same PR or manual branch. The benchmark's asyncio deadlines
remain cooperative, as explained in the existing benchmark documentation.

## Local validation without dispatching GitHub Actions

Run the existing benchmark manually using the instructions in
[BACKEND_BENCHMARKS.md](BACKEND_BENCHMARKS.md). For workflow syntax, use a local
`actionlint` installation if available:

```bash
actionlint .github/workflows/backend-benchmarks.yml
```

The workflow's two embedded Python blocks use only the standard library. They
can also be extracted and executed locally without downloading Actions or adding
a repository dependency. This example runs the exact embedded blocks against the
current checkout and writes artifacts to a fresh temporary directory:

```bash
python3 - <<'PY'
import os
import re
import subprocess
import tempfile
import textwrap
from pathlib import Path

workflow = Path('.github/workflows/backend-benchmarks.yml').read_text()
blocks = re.findall(r"          python3 - <<'PY'\n(.*?)          PY\n", workflow, re.S)
assert len(blocks) == 2
output = Path(tempfile.mkdtemp(prefix='trace-benchmark-ci-'))
env = {**os.environ, 'BENCHMARK_DIR': str(output), 'UV_OFFLINE': '1'}
results = []
for block in blocks:
    results.append(subprocess.run(['python3', '-c', textwrap.dedent(block)], env=env).returncode)
print('Runner/reporter exit codes:', results)
print('Local report directory:', output)
raise SystemExit(1 if any(results) else 0)
PY
```

For validation of model-selection logic, the runner's embedded `main(model_dir)`
accepts a local directory when called from a test harness. GitHub always calls it
without arguments, using the checked-out artifact directory. The reporter exposes
`validate(report, execution)` for testing failure/corruption cases in memory.
Use temporary model directories rather than moving or editing the real pair.

Initial local verification exercised the actual runner/reporter with the trusted
pair, absent pair, partial pair and incompatible pair; it also tested corrupted
reports, request/background failures, deadlines, network counters, health overlap,
missing JSON and informational slow timings. No remote run was triggered.
Remote Ubuntu execution, Actions downloads, artifact upload and the GitHub UI
remain to be verified by a future PR or explicitly requested manual run.
