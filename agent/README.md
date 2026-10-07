# Agent worker (BUILD-AGENT-DATA-01)

Contract: shared/api-contract.md, original SHA256 e1233c6e82b987385722d2d682794aeb3149cb660edc0330d0e3e85de0fd5518.
Owner w1:pN; review/integration by root. No live-model or OpenShell PASS is claimed.

## Start

Run from the product repo with its installed dependencies:

```powershell
.venv/Scripts/python.exe -m agent.worker --once
.venv/Scripts/python.exe -m agent.worker
```

Startup loads repo/.env without overriding existing environment variables. Never print it.
WORKER_TOKEN is always required. GUIDE_SERVER_URL defaults to http://127.0.0.1:8000.
NVIDIA_BASE_URL defaults to https://integrate.api.nvidia.com/v1.
NVIDIA_MODEL defaults to nvidia/nemotron-nano-12b-v2-vl; set the actual served model ID.

NVIDIA_API_KEY is used ONLY for https://integrate.api.nvidia.com (port 443).
Other model hosts use the separate SELF_HOSTED_API_KEY; there is no NVIDIA-key fallback.
Model credentials are rejected on every HTTP model endpoint, including loopback.
For a confirmed local model
endpoint (for example an SSH-forwarded http://127.0.0.1:8001/v1), explicitly set
NVIDIA_ALLOW_UNAUTHENTICATED_LOCAL=true to omit model Authorization when no self-hosted key exists.
For an operator-configured remote self-hosted endpoint, the equivalent opt-in is
NVIDIA_ALLOW_UNAUTHENTICATED_SELF_HOSTED=true. HTTPS remains the remote default.
Only an explicit NVIDIA_ALLOW_HTTP_SELF_HOSTED=true also enables unauthenticated remote HTTP.
These options never relax authentication for integrate.api.nvidia.com.
Endpoints come solely from deployment configuration, never model/user content.
RUN_CONTEXT=openshell is a label, not sandbox verification evidence.

### OpenShell broker gateway (explicit exception)

Root/pM configuration for the worker's fixed internal broker:

```dotenv
GUIDE_SERVER_URL=http://host.openshell.internal:8000
GUIDE_ALLOW_HTTP_OPENSHELL_GATEWAY=true
WORKER_TOKEN=
SELF_HOSTED_API_KEY=
```

Keep the existing secret WORKER_TOKEN via the approved environment; blank values above
are placeholders, not credentials. This opt-in permits broker HTTP only for the exact
hostname host.openshell.internal; suffixes, trailing-dot variants and other non-loopback
HTTP hosts remain denied. The broker token travels over this explicitly trusted internal
gateway; this exception does not enable HTTP model credentials. Default remains disabled.
Never set a model endpoint from user/model content. Both HTTP clients refuse redirects.

### JSON inference and current timing budget

The shared system prompt starts with /no_think for decision, grounded output and repair
calls. This matches the NVIDIA BF16 model card's system-message usage (checked 2026-10-07):
https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-12B-v2-VL-BF16

Model request timeout remains 10 seconds and max_tokens remains 2200; job deadline is
30 seconds (at most 3 calls). No measured warm GPU/prefill/decode timings were available
for this hardening pass. These are existing bounds, not a demonstrated latency promise.
Measure a warm real photo + two JSON calls before tuning them together with root's
server job expiry. Raising only the worker timeout would not fix server-side expiration.

## Pipeline and boundaries

1. Claim one job; keep request/session ID and up to 12 supplied history messages.
2. Fetch assigned normalized JPEG using photo_id and request_id.
3. Real OpenAI-compatible NVIDIA HTTP call proposes intent, food candidates,
   evidence reads and a bounded catalog search.
4. Local allowlisted evidence read + authenticated server radius search.
5. Second actual model call produces the grounded draft. Code supplies canonical
   evidence, menu descriptors and places, and validates the shared GuideResult.
6. Server validates latest request, evidence and searched places before saving.

No fake production fallback. At most 3 model calls including one JSON/grounding repair,
2 searches and a 30-second job deadline. API failures produce sanitized worker/fail
codes; HTTP409 stops superseded jobs. No direct result-file writes.
Ingredient, current availability and allergy suitability always remain unverified.
Dietary questions require staff confirmation. A picture does not identify its shop/GPS.
The model's prose is not mechanically proven true by schema/citation validation.

## Evidence and tests

data/catalog.json: one restaurant / three published menus; straight-line distance only.
data/evidence.json: three real source summaries plus nine official public fictional-input
summaries pinned to challenge commit 714e2e8d32f9b77e763a2458ca11b1270e80abf6.
Visitor names are omitted; no restricted/secrets inputs were read.
Fictional mode uses the same reasoning/tool core, all task evidence, no photo or map,
and requires an itinerary. Output is draft-only; no booking or external message.

```powershell
.venv/Scripts/python.exe -B -m unittest discover -s tests/unit -p "test_catalog*.py" -v
.venv/Scripts/python.exe -B -m unittest discover -s tests/unit -p "test_agent*.py" -v
```

Provider outputs in tests are HTTP stubs, including the FastAPI+worker roundtrip tests.
They do not establish live vision quality, latency, demand, device/audio performance,
or OpenShell enforcement. Required next gate: pM's actual NVIDIA-serving endpoint +
effective OpenShell policy, then one real photo job with root's service and UI.

Official API reviewed 2026-10-07:
https://docs.api.nvidia.com/nim/reference/nvidia-nemotron-nano-12b-v2-vl-infer
The documented user-message image_url accepts base64 data URIs.

BUILD-AGENT-DATA-01 result: 4 catalog tests + 15 agent/service tests passed.
BUILD-AGENT-HARDEN-02 result: 24 agent tests passed, including outbound credential,
redirect and two real-service/HTTP-stub-model integration tests. A separate read-only
review found no remaining blocker in the credential/gateway scope; it did not rerun tests.
Actual GPU inference, OpenShell gateway connectivity and model latency remain unverified.
See BUILD-STATUS.md for the original build's runtime gates.
