# BUILD-WEB-01 — review handoff

Owner w1:p8; reviewer/root w1:p7. 2026-10-07 KST. Status READY_FOR_REVIEW (frontend scope).
Product root: C:/Users/USER/Desktop/hangul-donghaeng. Only web/ was changed; no Git writes or pane control.
Contract SHA256 unchanged: e1233c6e82b987385722d2d682794aeb3149cb660edc0330d0e3e85de0fd5518.

## Changes

- src/App.tsx, src/styles.css: warm white responsive single page, English primary/Korean toggle, photo picker/capture, editable voice transcript, conversation, explicit Seochon demo/GPS/map point, radius controls, menu/culture/source/unknown/confirmation cards, Korean phrase copy/read, server download links, separate connection/privacy dialog.
- src/api.ts, src/types.ts: cookie session, photo upload, strict request shape, job polling on fixed /api routes; abort/ID/session checks prevent obsolete answers from overwriting current state.
- src/MapView.tsx: Leaflet1.9.4/OSM attribution, catalog markers and safe DOM popup text, selected point, loading/tile-error state. No fabricated GPS/restaurant data.
- src/useSpeech.ts: browser recognition/TTS, editable output, visible failure/unsupported notices, cancellation on new requests.
- package.json/package-lock.json, index.html, tsconfig.json, vite.config.ts, src/main.tsx, .gitignore: runnable Vite setup, /api proxy to127.0.0.1:8000, production build.
- src/api.test.ts, vitest.config.ts, playwright.config.ts, tests/browser/, tests/fixtures/: boundary and browser tests; every answer fixture is visibly development-only and never a live inference claim.
- README.md, DESIGN.md, this handoff. Screenshots/runtime observations remain ignored local artifacts under tests/artifacts/.

## Execution evidence

- npm.cmd install: completed. npm.cmd run dev: Vite on http://localhost:5173 (exec session44663); keep available for root integration.
- npm.cmd run build: PASS after final changes (TypeScript + Vite8.3.3,1571 transformed modules).
- npm.cmd test: 7/7 PASS (session/request isolation, abort, auth detail suppression, safe source URLs).
- npx.cmd playwright test: final10/10 PASS, installed Chrome at1280x1000 and390x844. First actual-service tests create sessions, observe health/OSM/layout with no JS errors/overflow. Eight answer/error scenarios use named route-intercept fixtures.
- Actual broker GET/api/health and Vite proxy both returned200. At13:22 KST, catalog_count=1 and worker_connected/model_configured/sandbox_verified were all false. Broker connectivity is shown separately from worker readiness; no “model ready” claim.
- node tests/browser/capability-probe.mjs: actual headless Chrome, no fake microphone. Recognition API=true, synthesis API=true, voices=[]; clicking mic produced “Check microphone permission or voice connection. You can also type your question.” Listening ended, typed transcript editing succeeded. This does not verify spoken recognition or audible playback.
- Local evidence: tests/artifacts/desktop-actual-ui.png, mobile-actual-ui.png, runtime-capabilities.json. Physical-device microphone/camera/GPS and HTTPS remain separate checks.

## Integration limits / blockers

No live inference was requested by this frontend validation. Live image/food judgment, actual server photo/result download round trip, OpenShell normal/deny evidence, physical-device voice/TTS/camera, mobile HTTPS and final submission are unverified. Root is moving the broker to WSL while preserving localhost:8000; temporary reconnect errors are expected. No additional UI feature is required before that integration test. Fixture passes cannot establish model/OpenShell success.

15:30 feature freeze /16:30 presentation transition /17:20 submission inherited. Root owns shared/service integration, Git and publication; this report is not product completion.
