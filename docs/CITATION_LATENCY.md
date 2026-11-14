# Citation classification latency optimization

The classification coordinator now starts the existing OpenAlex fallback during
an **observed Semantic Scholar HTTP 429 cooldown**, instead of always waiting for
the primary retry sequence to finish. It does not bypass ordinary rate-limit
pacing. No provider limits, timeouts, retry counts, identity checks, passage
extraction rules, model artifacts, API contracts, or frontend code changed in
this task. Existing uncommitted frontend/Gemini work was preserved.

The change is confined to the citation coordinator/scheduler, timing hooks in the
existing TEI service and classification route, one small timing utility, and one
offline test file. It adds no cache layer or dependencies.

## Safety and source selection

- The scheduler publishes the same existing cooldown deadline to an event; it
  retains its lock, adaptive interval, Retry-After handling, and three-attempt cap.
- A cached or completed, classifiable primary result wins. Healthy primary
  retrieval proceeds normally without a 429.
- Verified TEI can return early only while a provider cooldown is actually active.
  If TEI finishes after the cooldown expires, an already resumed primary retains
  its success opportunity. The coordinator waits for its result or another 429.
- Failed TEI never removes remaining primary retries. If both paths fail, the
  primary status/reason and TEI fallback reason remain available as before.
- Early cache-capacity rejection sends no I/O. If the primary later fails, the
  original late fallback opportunity is retained once, without an unbounded retry.
- Existing ResourceCache instances coalesce pair, mapping, reference-page,
  metadata, and document requests. Existing TEI gates still permit at most two
  retrievals/documents; Semantic Scholar remains serialized.
- Coordinator-owned tasks are canceled and awaited on exit. Canceling one caller
  does not cancel other callers' shared loaders. Canceling the last waiter stops
  its pending loaders/retries. Tests exercise this through canceled ASGI HTTP
  requests in both primary and fallback phases. A real TCP disconnect does not
  necessarily cancel an ASGI handler; server disconnect policy is unchanged.
- Repeated unavailable-pair reads previously refreshed their five-minute TTL.
  They now preserve the original expiry, so continued clicks cannot indefinitely
  postpone a new primary lookup. Positive cache lifetimes and copy isolation are
  unchanged.

## Measured before/after

These are **deterministic offline virtual-clock measurements**, not live API
benchmarks. The original coordinator was imported from an ignored copy of its
Git HEAD source and run against the same harness as the working tree. The source
hash and baseline commit are recorded in [the sanitized report](reports/citation_latency.json).
All TEI successes use the recorded real BART XML and the unchanged actual model:
Background, confidence `0.8843842684202584`. S2 responses are clearly synthetic
test fixtures. No live provider requests were made.

| Condition | Before (s) | After (s) | HTTP attempts before → after |
| --- | ---: | ---: | ---: |
| Normal S2 success | 3.32 | 3.32 | 5 → 5 |
| Persistent 429, verified TEI | 9.37 | 1.17 | 7 → 5 |
| Slow HTTP plus repeated 429 | 87.07 | 24.02 | 11 → 6 |
| Existing active cooldown, verified TEI | 7.12 | 0.87 | 5 → 4 |
| Expired cooldown | 3.32 | 3.32 | 5 → 5 |
| Ordinary scheduling delay, no 429 | 4.62 | 4.62 | 5 → 5 |
| OpenAlex-only configuration | 0.87 | 0.87 | 3 → 3 |
| Both providers unavailable | 8.92 | 8.52 | 6 → 6 |
| Cached pair, including classification | 0.02 | 0.02 | 0 → 0 |
| Primary resumes before ready TEI can return | 7.17 | 7.17 | 6 → 9 |
| Primary recovers before slow TEI finishes | 8.92 | 8.92 | 6 → 9 |
| TEI unavailable, primary later succeeds | 8.92 | 8.92 | 6 → 8 |
| 20 callers, two targets of one citing paper | 4.82 | 4.82 | 7 → 7 |

The persistent-429 case improves 87.5%; the slow case improves 72.4%. Request
counts include dispatched attempts that were subsequently canceled.

Default modeled waits: metadata HTTP 200ms, S2 HTTP 100ms, XML HTTP 400ms, parse
50ms, inference 20ms, Retry-After 4s. Slow-case waits: metadata 2s, S2 HTTP 9s, XML
8s. The actual parser and classifier still execute, but their CPU cost is excluded
from virtual time. Recovery cases vary XML/Retry-After delays as recorded in the
test harness.
The cached request still runs inference; no prediction cache was introduced.

The 87.07s baseline comprises 54s across six S2 HTTP attempts, 16s of retry
backoff, 1s of additional scheduler pacing, 8s of metadata HTTP, 8s XML HTTP,
50ms modeled parsing, and 20ms modeled inference. After optimization, TEI runs
during retry waits. Its verified passage is ready at 23.05s; the coordinator
retains the resumed S2 attempt until its next 429 at 24s, then returns the same
TEI passage and classifies it. No in-flight healthy primary attempt is cut off
just because TEI is ready.

A separate actual local CPU profile used instant mocked HTTP and the real BART
document/model: cold parsing 68.35ms, first model load/inference 632.36ms, handler
total 711.56ms; warm retrieval 0.29ms, inference 2.43ms, handler total 3.33ms.
These timings include local initialization and thread-pool overhead, and exclude
real network latency. They are one machine's observations, not performance bounds.

## Instrumentation and remaining limits

Enable INFO for `app.services.citation_timing` to collect timings. It is silent
at the default application logging level. Classification records share an opaque
trace ID, fixed stage names, elapsed milliseconds, and safe metrics such as provider,
attempt number, HTTP status, cache reuse, or remaining cooldown. It logs no
request identifiers, URLs, credentials, response bodies, passages, or predictions.
The classification-route trace propagates through coalesced tasks and inference
thread-pool work; shared loaders belong to the initiating trace, while other
callers record their own cache-wait duration. Timings are nested/overlapping and
must not be added indiscriminately.
Standalone service probes outside a timed request can have no trace ID.

Stages cover handler total, retrieval, pair/mapping/reference/fallback cache reuse,
identifier resolution, S2 queue acquisition/pacing/HTTP, provider backoff,
references, TEI queue/metadata/HTTP/XML/parsing, and model inference. The inference
stage includes first-use model loading; handler time also includes thread-pool
dispatch. The handler total excludes HTTP response serialization/network transit.

Transient throttling can cause **extra bounded OpenAlex work** even when S2 later
succeeds: recovery tests add two metadata requests or two metadata plus one XML
request. Existing caches and cancellation reduce repeated work; no provider's
concurrency limit is increased. An active cooldown can yield a verified TEI
passage instead of waiting for a potentially different future S2 passage, so the
selected source/context/prediction can differ. Both retain full original identity
verification, exact text, provenance, and the original classifier.

Transport errors and 5xx responses without a 429 still follow the original S2
retry sequence and can remain slow. Reference pagination, rate-limit queueing,
and cold TEI downloads also remain variable. Full-text unavailability is not
hidden. Shortening retries or timeouts would risk coverage and was not done.

OpenAlex citing metadata is sometimes fetched by both paths: the S2 resolver
requests a smaller field set, while TEI requires the citation list, content
binding, and stricter full-document metadata. Mapping-cache entries cannot safely
stand in for complete TEI metadata. Cross-seeding partial metadata was therefore
not introduced. The existing mapping, reference, TEI metadata, parsed-document,
and pair caches already eliminate repeated lookups within each validated path.

## Verification

`npm run lint`, `npm run typecheck`, `npm run test`, and `npm run build` passed:
494 backend tests (including 21 new latency/concurrency/privacy tests) and 34
frontend tests. One existing Starlette TestClient deprecation warning remains.
Tests preserve the real BART passage/confidence and cover ordinary success,
throttling, resumed S2 success, disabled S2, both failures, cache TTLs, same-citing
request sharing, capacity rejection, canceled callers, and credential-free logs.

Reproduce the controlled cases offline with:

```text
uv run --offline --project apps/api pytest apps/api/tests/test_citation_latency.py -q -s
```

All work remains uncommitted on `dev-ml`; no branch operations or pushes occurred.
