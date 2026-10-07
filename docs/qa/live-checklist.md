# Live acceptance checklist — BUILD-LIVE-QA-01

Owner: w1:pG. Only `tests/live/run_demo.py` and this document are owned here.
Contract: `shared/api-contract.md`, v1 (2026-10-07).
Prepared checks are **not live execution evidence**.

## Readiness and execution

- [ ] Root explicitly declares the actual service + worker ready and authorizes the bounded live sequence.
- [ ] Actual NVIDIA endpoint is configured by its owner; no mock transport or canned production reply.
- [ ] Confirm the checked-in CC0 sample manifest and SHA. The photograph is generic samgyetang, **not verified to show this restaurant**, ingredients, or the user's meal.
- [ ] Use the product virtualenv. No credentials in CLI arguments or report.

From product root:

```powershell
.venv/Scripts/python.exe -B tests/live/run_demo.py --check-helpers
# ONLY after root says ready:
.venv/Scripts/python.exe -B tests/live/run_demo.py --run-live --base-url http://127.0.0.1:8000
# Optional additional real model job, if root approves and time remains:
.venv/Scripts/python.exe -B tests/live/run_demo.py --run-live --include-fictional
# Target ONLY far-location and fictional cases, after root readiness:
.venv/Scripts/python.exe -B tests/live/run_demo.py --run-live --scenario far_location_zero_results --scenario fictional_conflict
# Dietary follow-up requires the previous confirmed case in this same session:
.venv/Scripts/python.exe -B tests/live/run_demo.py --run-live --scenario confirmed_near_seochon --scenario dietary_followup
```

Without `--scenario`, the default four cases are unchanged; `--include-fictional` appends the fifth. Repeated `--scenario NAME` selects only those cases, deduplicated and run in canonical order (photo → confirmed → dietary → far → fictional), regardless of argument order. Selecting fictional directly needs no additional flag; combining selections with `--include-fictional` appends it. The choices are `photo_question`, `confirmed_near_seochon`, `dietary_followup`, `far_location_zero_results`, `fictional_conflict`.

Selecting dietary without confirmed-nearby fails with a useful CLI error **before network or artifact creation**; no prerequisite/model call is silently added. The confirmed case may itself legitimately request clarification, so human review still decides whether that context is adequate. Success applies only to the selected cases, recorded in `metrics.json.selected_scenarios`, and is not a full-suite pass. Do not run the full and targeted commands accidentally.

Default/no execution flag exits 2 without network or artifacts. `--check-helpers` checks only pure URL, redaction, distance, subset/prerequisite and Korean-order helpers. It neither creates a fake service nor establishes product acceptance.

Live mode uses one in-memory cookie session and uploads the actual JPEG, including when running a subset. By default it sends four sequential requests: photo question → explicit user-confirmed samgyetang at selected Seochon → seafood-avoidance follow-up → selected Busan point with a 500 m radius. Points and dietary preference are synthetic test conditions, never GPS/private user data. Fictional mode is optional and must never return real map places.

Submission + polling stops at **35 seconds per request**, HTTP timeout is 5 seconds, polling interval 1 second, entire run timeout is **240 seconds**. The script does not launch/restart/stop a service or worker and does not call the model endpoint directly. A failed/timed-out job stops the sequence to avoid stacking calls; root decides recovery. Already submitted work may finish after client timeout; the script does not claim to cancel server/model execution.

## Read results correctly

- [ ] Check every scenario, not just process exit code. `completed_useful` requires a completed job and useful structured result. `completed_clarification` requires a meaningful nonempty next question and is a legitimate completion, not a timeout.
- [ ] A clarification in the confirmed-nearby case does **not** establish successful restaurant discovery. Complete its requested clarification manually before presenting the full product journey as demonstrated. All-clarification runs are not end-to-end usefulness proof.
- [ ] For ready nearby results, catalog coordinates/version and within-radius distances match; source references are approved and present. Catalog coverage is limited; empty far results do not imply no restaurants exist.
- [ ] Dietary follow-up contains uncertainty and a **nonempty `order_ko` with Hangul**, for both ready and clarification results. An English `next_question` cannot substitute. The automated check establishes field presence and Hangul only; human reads whether the Korean sentence meaningfully asks about seafood, broth, ingredients and cross-contact without a safety guarantee. No exact wording is required and semantic safety remains unverified.
- [ ] Verify downloaded JSON card equals the polled result before sanitization. The script keeps both sanitized result and downloaded card per scenario, plus `final-result.json` for the last structurally valid result.
- [ ] If optional fictional case is ready: conflicts and itinerary exist, places are empty, and human checks which dated notice governs, travel buffers, unsupported assumptions and example labeling.
- [ ] A meaningful next question, historical truth, fluent translation, dietary safety and utility need human review; schema/evidence-ID checks do not establish these.

Artifacts: ignored `.runtime/qa/<UTC timestamp>/metrics.json`, `<scenario>.result.json`, `<scenario>.downloaded-card.json`, `final-result.json`. A failure before a valid result has metrics only. IDs, cookies and auth values stay in memory; saved copies remove identity fields, redact known session values and common credential forms, and remove URL credentials/query/fragment. No raw request/response headers, error bodies, uploaded bytes or environment dumps are saved. This is a bounded public-sample run, not a general PII anonymizer. Do not substitute private photos/questions. Do not commit runtime evidence. Root should review artifacts before sharing.

Latency is client wall time including queue, tools and model; **model-only latency and provider provenance are unverifiable through this browser API**. Health flags are recorded as server-reported observations, not independent proof. OpenShell remains `independent_proof_required`, even if health reports true.

## Actual human browser microphone and TTS

Record device/browser/version, test time, observer, outcome and redacted evidence path manually.

- [ ] On an actual supported browser/device, microphone permission is requested only after clicking. Speak a short food question; visible transcript is editable and the submitted text matches the edited words.
- [ ] Deny microphone permission once. The UI explains the issue and text input still completes the request. Check unsupported speech-recognition fallback where available.
- [ ] Upload the CC0 JPEG in the UI; preview is visible, identity uncertainty is shown appropriately, confirmation survives follow-up, and the Seochon point is labeled selected rather than GPS.
- [ ] User activates TTS; audible content corresponds to the current answer. Stop works. A new request cancels old speech and stale answers do not restart speaking.
- [ ] Test English/Korean voice availability and unavailable-voice fallback. Check no autoplay or surprise permission requests; headphones/screen recording are optional, not acceptance substitutes.
- [ ] Download and open the HTML/Markdown card manually; readability, escaped text, source links, uncertainty and Korean staff question survive. Automated JSON equality does not verify browser rendering/audio.
- [ ] Map shows attribution and catalog coverage; a far-point empty result clears stale markers. No reservation/order/network action is claimed from generating a Korean question.

## Independent OpenShell and actual-provider evidence (infra/root)

- [ ] Record actual runtime/container identity, installed OpenShell version and effective policy, including provider-injected permissions; a `RUN_CONTEXT` string is insufficient.
- [ ] Show one approved actual NVIDIA request/response with provider/model and sanitized correlation/time evidence, without tokens or full private prompts. Client wall time is separate from provider timing.
- [ ] In the approved disposable probe environment, show normal input-read/result-publication success alongside denied non-allowlisted egress and denied write outside allowed scope.
- [ ] Use owner-provided harmless sentinels for deny tests. **Do not read /hackathon/restricted or /hackathon/secrets, private host files, or delete real assets.**
- [ ] Demonstrate deletion denial separately with disposable sentinel/writer controls. A read-write directory alone does not establish deletion prevention.
- [ ] Record policy enforcement mode and deny logs; service-cookie rejection is not OpenShell network/filesystem denial. Independent reviewer checks that logs come from the same actual runtime used for the demo.
- [ ] If runtime is local-dev or any proof is missing, mark OpenShell **UNVERIFIED**. Never upgrade this script's successful HTTP flow to runtime compliance.

## Handoff

Only syntax and offline helper checks are authorized during preparation. Live status, model inference, microphone/TTS and OpenShell denial remain **NOT RUN / UNVERIFIED** until their owners execute and inspect evidence after root readiness.
