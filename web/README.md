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

Actual food/image inference; spoken recognition and audible TTS on the presentation device; physical camera/GPS permissions; HTTPS mobile deployment; end-to-end live result/download; actual OpenShell normal/deny enforcement. Microphone capability/error observations are recorded separately from fixture tests and are not proof of successful speech. Root owns final integration, commits and publication.
