# Semantic Scholar throttling diagnosis — November 14, 2026

Persistent throttling reproduces with isolated, authenticated requests more than five seconds apart. No application scheduling bypass was found. The evidence points toward upstream enforcement or another restriction outside this service, but does **not establish a root cause**. Key quota assignment, other users of the key, IP-level policy and provider capacity remain unverified.

## Application and process audit

- Production Semantic Scholar lookups use `_get` → `_send` on the one lifespan-owned `CitationContextService`. `_get` attaches the configured `x-api-key`; metadata and references share the same scheduler. Repository search found no other production Semantic Scholar transport path. Optional anonymous configuration remains supported; the diagnostic requires a key and checks exact header equality without recording it.
- The async lock covers spacing, the HTTP attempt and publication of HTTP 429 cooldowns. Starts are separated by at least 1.5 seconds; adaptive spacing grows to 4.5 seconds. Retries also enter this lock. Numeric/date `Retry-After` is respected; long cooldowns fail promptly without an early retry. At most three production attempts are made. Retries increase request volume during throttling, but do not bypass scheduling.
- Mapping, DOI metadata, reference-page and pair caches retain bounded TTLs and coalesce concurrent identical loads. Prior reference-page reuse was effective. Failed requests are not successful cache entries, so later user requests can retry them. Cold caches and failed loads increase total requests; neither explains observed five-second isolated failures by itself.
- Before testing, privileged process inspection found no Python/uv/backend processes and no listeners on ports 8000/8001. At diagnostic start and finish, the only Python chain was `uv.exe` → Windows venv `python.exe` launcher → diagnostic interpreter. The parent launcher waits for the interpreter; it is not a second serving worker. No backend was started or terminated for this test. This establishes local isolation at the observed checkpoints, not exclusive worldwide use of the key. Offline regression tests made no provider calls.

## Controlled live test

Run: **November 14, 2026, 4:50:03–4:50:24 a.m. EST** (09:50:03–09:50:24 UTC). A 60-second quiet period preceded the first request, after earlier local callers had exited. No known local cooldown remained. The provider exposes no cooldown state, so expiry of an undisclosed provider window cannot be proven.

The explicit diagnostic uses the production service's `_get` authentication and `_send` scheduler. It suppresses automatic retries, waits at least five seconds after each response, caps volume at five requests and stops on the second 429. It bypasses resource caches intentionally to measure upstream behavior. No passages were classified or added as examples.

| UTC time | Endpoint | Gap from prior start | HTTP | Provider request ID |
| --- | --- | ---: | ---: | --- |
| 09:50:03.630 | Sentence-BERT DOI metadata | — | 200 | `d2b38a00-fead-4241-882d-f06cb4df9090` |
| 09:50:08.867 | ELMo DOI metadata | 5.250 s | 200 | `e305c64e-5a99-45c7-9dfd-d80c5820928f` |
| 09:50:14.214 | SciBERT references, limit 1 | 5.344 s | 429 | `ac685f57-c5e6-440a-bd88-267904e1db2f` |
| 09:50:19.403 | Sentence-BERT DOI metadata | 5.187 s | 200 | `7b57e75b-fb09-4cd0-92d9-f4f234ecca0f` |
| 09:50:24.561 | ELMo DOI metadata | 5.156 s | 429 | `30ca50cd-9c2e-4563-a8a6-2a1574e95585` |

All five requests carried the exact locally configured key. **Two of five returned HTTP 429 (40%)**; there were no retries or concurrent provider requests. Neither 429 supplied `Retry-After`, rate-limit limits/remaining/reset, or quota headers. Both included `x-amzn-requestid`, current `Date`, `x-amz-cf-pop: BOS50-P4` and `x-cache: Error from cloudfront`. Successful responses said `Miss from cloudfront`. No `Age` header was present. These headers identify the delivery path and correlation IDs; they do not prove that CloudFront itself imposed the limit or cached a stale error. Response bodies and credentials were not recorded.

[Sanitized raw evidence](reports/semantic_throttling_diagnostic.json) includes precise timings, allowlisted response headers and process checkpoints. Reproduction command: `uv run --project apps/api python apps/api/scripts/diagnose_semantic_throttling.py`. Keep other callers of the key idle. No further live probing was performed after the stop condition.

## Comparison and conclusion

| Run | Requests | HTTP 429 | Observed minimum start gap |
| --- | ---: | ---: | ---: |
| Earlier fixed pacing | 39 | 17 (43.6%) | 1.500 s |
| Earlier adaptive pacing | 56 | 25 (44.6%) | 1.500 s, adaptation up to 4.5 s |
| Isolated diagnostic after quiet period | 5 | 2 (40.0%) | 5.156 s |

The small new sample cannot estimate a stable failure rate or prove that slowing down has no benefit. It does show that local bursts, retries and concurrent backend workers are **not necessary** for these failures. ELMo metadata returned both 200 and 429, so an endpoint-only denial is not established. Earlier runs lacked process snapshots, so their global key usage cannot be reconstructed. The official introductory quota is one request per second across endpoints, but actual key assignment and enforcement must be confirmed by the provider. [Official API overview](https://webflow.semanticscholar.org/product/api)

No production limiter or cache changes are justified by this evidence. Changing them again would imply a diagnosis we do not have. Added only the guarded diagnostic CLI and sanitized evidence/report. Backend regression: **177 passed**, one existing Starlette/httpx deprecation warning; Ruff lint/format passed. Existing inference, provenance, caches and recorded examples remain covered. Work remains on `dev-ml`; no merge or push.

## Support-ready technical summary

> We have an approved Semantic Scholar API key with a stated cumulative limit of 1 request/second. On November 14, 2026 at 09:50:03–09:50:24 UTC, after 60 seconds without local provider traffic, one isolated Python client issued five serial authenticated Graph API GETs with measured start gaps of 5.250, 5.344, 5.187 and 5.156 seconds. Automatic retries were disabled. Statuses were 200, 200, 429, 200, 429; we stopped after the second 429. Both metadata and references were tested. The same ELMo DOI metadata lookup succeeded and later returned 429. Neither 429 included Retry-After or quota headers. Please correlate request IDs `ac685f57-c5e6-440a-bd88-267904e1db2f` and `30ca50cd-9c2e-4563-a8a6-2a1574e95585`, confirm that the key is recognized under its approved quota, and clarify any endpoint/IP/cumulative-window restrictions or capacity-related throttling. The sanitized evidence file contains paths, timestamps and response correlation headers. We cannot exclude use of the same key from another machine. Credentials are omitted; account identification can be supplied through your authenticated support channel.

This is a draft for the user to submit; no support message was sent.

## Recommendation

Proceed with **selected-edge frontend integration**, with explicit loading, unavailable/rate-limit states, provenance and cached-example labels. Keep one backend worker/instance per key and reuse reference pages; avoid automatic classification on graph expansion and automatic UI retry loops. Live availability remains best-effort until support clarifies the persistent failures.

Pursue provider support first. A separate, limited TEI feasibility experiment is justified if the demo must cover the four BioBERT relationships with verified missing passages or the BART DOI-mapping gap documented in the earlier report. That experiment addresses evidence coverage, while the throttling diagnosis remains unresolved. It should evaluate a small fixed set of citing documents and exact bibliography identifiers before any full fallback implementation. No TEI extractor, frontend or database change was implemented here.
