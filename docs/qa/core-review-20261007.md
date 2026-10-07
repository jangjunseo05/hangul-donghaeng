# Core review — 2026-10-07

Reviewed baseline: `76d785f`. Corrective commit: `bb6630b`.
Scope: Python broker/worker, shared contracts, curated data and related tests.
Web, deployment infrastructure, physical audio and live inference are outside this verdict.

Two independent OMX role lanes reviewed the scope: `core_code_review` (code-reviewer) and `core_architecture_review` (architect). Existing Herdr pF separately reproduced the session-capacity fix; pN implemented worker fixes while pM continued deployment.

| Finding | Correction | Evidence |
|---|---|---|
| Food observation lost between model calls | Carry validated observation, intent, permitted menu metadata and explicit user confirmation into drafting | Different observed dishes produce different second prompts; five context regressions |
| Saved cards omitted conflicts and claim citations | Include decisions/reasons, claims, citation associations and next question in Markdown/escaped HTML | Both output formats preserve the result content |
| Fictional/real history mixed | Clear history when dataset mode changes | Same-mode history retained, cross-mode history empty |
| Missing Content-Length bypassed body limit | Count actual ASGI body bytes before parsing | Chunked 300 kB JSON rejected with 413 |

Follow-up lane verdicts: **code-reviewer APPROVE; architect CLEAR**. Combined recommendation: **APPROVE for this source-code scope only**. Code lane reran 33 relevant tests; architecture lane reran seven targeted tests. Root full suite: **50 passed, 29 subtests passed**, including four policy configuration tests. One upstream Starlette/httpx deprecation warning remains.

These model tests use explicit HTTP stubs. They do not prove actual NVIDIA inference, photo recognition quality, latency or OpenShell isolation. Those require separate runtime evidence.

Human input observation: user reported both English and Korean speech appearing in the input box on the demo PC at approximately 13:30 KST. Audible output and mobile HTTPS are still pending; this is user-reported physical input evidence, separate from browser automation.
