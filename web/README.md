# 한글동행 — web

React/TypeScript/Vite mobile frontend. Owns only `web/`; the root service, agent, shared contracts and OpenShell belong to their assigned workers.

## Run

Node 24.18.0/npm 11.16.0 were used here. Start the root-owned FastAPI broker on `127.0.0.1:8000`, then:

```sh
cd web
npm ci
npm run dev
npm run build
```

Windows PowerShell: use `npm.cmd` / `npx.cmd` if execution policy blocks npm.ps1.
Vite listens on port5173 and proxies **only /api** to the local broker. Preview uses4173 with the same proxy. Production hosting must route /api to the broker; mobile devices require a reachable HTTPS address for browser media/location features. Local development does not establish mobile HTTPS readiness.

## Implemented

Cookie session; validated JPEG/PNG upload <=8MiB; editable English/Korean question; browser speech input/TTS with visible unsupported/permission/service errors; local photo preview; current location on click, map click, or explicitly labeled Seochon demo point; 0.5/1/2/3km radius; server job submission/polling; late-result cancellation; confirmation candidates; place/menu/culture/evidence/unknown cards; Korean phrase copy/read; server-owned result download links; fictional practice mode separate from real-place map. Offline/reconnect and map loading/tile errors are visible. Service connectivity and worker readiness are distinct, and connection details do not claim a completed model/safety test.

Leaflet1.9.4/OSM attribution remains visible. Search covers the server catalog only; coordinates and results come from the service. No restaurant photos, model answers, food-safety guarantees or location are invented. Speech may use a browser external service; OSM receives tile requests. Google fonts are not fetched.

## Tests

```sh
npm test
npx playwright test
node tests/browser/capability-probe.mjs
```

Playwright uses installed Chrome, viewport1280x1000 /390x844 and an already running Vite/broker. The actual-service case only creates a browser session and observes health/map/layout: it does **not** request model inference. All answer scenarios intercept API using `tests/fixtures/guide-result.json`, with visible “Development fixture” text. They verify interface behavior, not model/OpenShell execution. Tests cover session/request isolation, aborted polling, delayed old answers, source URL safety, upload contract, unknowns/download route, unsupported speech, Korean toggle, map tile failure and server outage. Local screenshots/capability JSON are in `tests/artifacts/`.

## Still unverified

User physically verified both English and Korean voice input and later confirmed audible TTS (user report on2026-10-07). The earlier headless microphone/error observations are separate from that physical-device confirmation. Automated mobile checks cover screen layout only.

Android rear-camera preview and a captured image remaining after Stop were physically confirmed by the user (2026-10-07): user-reported hardware PASS. The user subsequently confirmed both Korean and English speech input on the actual Android phone: user-reported physical speech-input PASS. These checks do not verify automatic frame transmission, Android background handling, model recognition or the integrated camera/voice-to-model journey. Actual food/image inference, physical GPS permissions, end-to-end live result/download and OpenShell normal/deny enforcement are not verified by this frontend work. Root's NVIDIA QA is separate; this change sends no competing live jobs. Root owns final integration, commits and publication.

## BUILD-WEB-GPS-FIX-02

Reproduced a delayed GPS callback submitting a third real-place request after switching to a new fictional request. GPS success/error callbacks now require the captured request generation and the current real-place mode. Mode changes, new submissions and photo changes invalidate the old callback and clear its waiting state. Valid current GPS callbacks still update the location and submit normally.

Validation: the new cross-mode regression failed before the fix; `npx playwright test gps-race` passed12/12 after the fix across desktop/mobile. Cases cover mode changes, new real-place requests, photo replacement/removal, obsolete failures and a valid GPS success. All API calls are intercepted with named development fixtures. `npm run build` passed. No cosmetic changes, service/runtime edits or Git writes.

## Sequential real-browser QA preparation

`tests/browser/real-journey.mjs` is now prepared for the culture-first journey. It uses the preserved CC0 `data/samples/heritage-demo.jpg` and `heritage-license.json`; the archive image is not evidence of the user's current location or a team camera capture.

`node tests/browser/real-journey.mjs` checks the local CC0 sample hash/catalog and prints selectors/steps only. It opens no browser and sends no requests. The live branch must wait for root's explicit GO after the current worker is ready and the queue is idle; a CLI flag alone is not approval.

After that GO, use `node tests/browser/real-journey.mjs --root-go "<root GO reference>" --base-url http://127.0.0.1:5173`. This standalone script observes actual UI requests without interception. It sends at most five sequential deliberate questions: cultural photo identity without assumed GPS, explicit Gwanghwamun confirmation at its catalog point, culture-to-nearby-meal, restaurant selection/menu, and restaurant-to-history. The restaurant's selected coordinates are checked separately from the heritage point. Each terminal response must finish before the next action; failures stop without retry or injected candidates. The real API's catalog supplies coordinates and kind. Korean phrases, source cards, map, HTML/JSON and layout are checked; a missing returned phrase requires review. Automatic frames and physical camera/voice are outside this script.

Only the live branch writes timestamped artifacts into `../.runtime/qa-ui-real/`: actual HTML/JSON downloads, screenshots at1440px and390px, a receipt, and silent actual UI video under each run's `raw-video/`. The context closes even on failure to flush the recording. The receipt records action/accepted/terminal/UI-ready times, screenshot and download times for transparent later wait compression. The video depicts an archive sample uploaded through the actual UI, not on-site camera footage or audio evidence. Mobile reuses the same result without another inference. Root still reviews semantic accuracy, deployment revision and independent OpenShell evidence. Preparation is not a live execution PASS.

## Culture/camera handoff — 2026-10-07 14:45 KST

Culture-first welcome and questions; local camera start/stop with environment preference and audio:false; fixed capture sent separately with a question; separate opt-in automatic companion; catalog cultural starting points/place confirmation; heritage/restaurant labels in lists/popups; culture-to-meal and meal-to-culture actions. Cultural confirmation selects the catalog coordinates. Gwanghwamun is identified as Gyeongbokgung's main gate in the same complex.

Automatic mode uploads sampled JPEGs. It waits20seconds after each response, permits one automatic task at a time, pauses for manual input and stops on hidden page, camera loss, confirmation, error or photo limit. Observation epochs reject late answers after stop; TTS reads the latest read-aloud preference and suppresses repeated proposals. The existing20-photo bound is preserved; there is no deletion/rotation or session reset to bypass it. Permission denial, busy/unsupported camera, PHOTO_LIMIT and JOB_BUSY have visible fallbacks.

Validation: `npm run build` PASS; `npm test`12/12; `npx playwright test camera-culture`30/30 desktop/mobile; `npx playwright test guide gps-race`22/22. New camera cases use synthetic canvas MediaStreams and intercepted named API fixtures, never model GPU jobs. They cover explicit permission/capture without transmission, late permission cleanup, one automatic task, manual priority, background stop, camera-ended late answer/TTS rejection, latest read-aloud toggle, repeated proposal suppression, confirmation/error/photo-limit stop, catalog coordinates and culture/meal transitions. Legacy proxy/health/map cases perform no inference. Fixture screenshots: `tests/artifacts/desktop-culture-camera-fixture.png` and `mobile-culture-camera-fixture.png`.

Physical Android updates (user report, 2026-10-07): rear-camera preview works and a captured image stays visible after camera stop, both normal; hardware PASS for these two checks. A later actual-phone check confirmed Korean and English speech input, both PASS. Still unverified: Android TTS, Android background lifecycle, automatic frame analysis and the integrated culture/camera/voice-to-model journey. Earlier audible TTS confirmation remains a separate user-reported observation and does not establish Android TTS. Root owns service/worker restart, runtime GO, integration and Git; this frontend work sends no model jobs.

Self-hosted eligibility/privacy correction: automatic mode uses a reachable service, valid browser session and connected worker, with the existing photo cap. Hosted `model_configured` and `sandbox_verified` flags are independent metadata, not eligibility gates; the live journey preparation also removes the hosted flag assertion. The connection dialog labels hosted configuration explicitly and explains manual-question/automatic-companion photo transmission while preview stays local. The added desktop/mobile regression covers worker=true, hosted=false and sandbox=false. Confirmation stops automatic mode; the demonstrated two-frame path is confirm then explicitly re-enable, not uninterrupted autonomous viewing.

Correction validation: `npx playwright test camera-culture -g "self-hosted"`2/2 PASS with transmission-copy assertions; production build PASS (`index-FWKuvoMh.js`). No model jobs were sent.
