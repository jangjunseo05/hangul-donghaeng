# API contract v1 — 2026-10-07

## 14:26 additive culture/camera extension — authoritative over earlier food-only wording

- Request adds `interaction_mode: 'ask'|'observe'` (default `ask`) and `confirmed_place_id: string|null` (default null). Legacy `confirmed_shop_id` remains accepted; if both are present they must agree. A camera preview is local; only sampled/captured JPEGs use the existing photo route. Observe requests are explicit opt-in, single-flight and subordinate to manual requests. Do not claim continuous video model inference.
- Scene adds `place_candidates: {id,name_ko,name_en}[]` (default `[]`, maximum 3) and `confirmed_place_id: string|null` (default null). Candidate identity is uncertain until confirmed; no photo-derived GPS or unsupported heritage identification.
- Place adds `kind: 'restaurant'|'heritage'` (default restaurant). Coordinates/source/version still come only from validated catalog search. Maximum total places remains 3.
- `GET /api/catalog` returns `{catalog_count,scope_label,catalog_version,places:[{place_id,name,name_en,kind,lat,lng,source_id,catalog_version}]}` for user-selectable curated anchors. Selecting an anchor explicitly sets `location.origin='selected'`; do not call it device GPS.
- Worker search adds optional `kind: 'restaurant'|'heritage'|null`; `shop_id` remains the legacy target ID field and may name an approved cultural place. Catalog helper signature becomes `search_places(food_id,shop_id,location,radius_m,kind=None)`. pN implements `public_catalog()` matching the browser catalog response. `get_place()` returns the canonical Place fields except distance, including kind, with no extra name_en field.
- Two searches may combine restaurant and heritage results. Broker accumulates validated results from both searches; all distances remain relative to the request's chosen location. To search around a cultural place, user selects/accepts that catalog anchor in the UI first.
- pE supplies `data/heritage-proposal.json` plus official sources; pN merges reviewed records into catalog/evidence. Culture claims may cite approved culture records for the corresponding place; a source ID alone is not semantic verification. Preserve uncertain identity, dated operation information and site etiquette.
- Automatic camera mode samples no more often than 20 seconds after the previous request finishes, pauses for manual editing/questions, hidden tab, denied permission and pending confirmation, and stops on user request. No face/person identification. Repeat proposals are suppressed. Reaching the existing 20-photo session bound pauses auto mode with a visible message; do not silently rotate/delete user captures in this change.
- p8 owns web; pN owns agent/catalog/data; root owns shared/service/render and integration. Add defaults to preserve existing request/response fixtures. The culture/camera runtime is unverified until its own live tests.
- Runtime budget update after measured draft timeouts: model call at most 35 seconds, worker job at most 60 seconds, broker request at most 65 seconds, browser/live poll at most 70 seconds. These are failure bounds, not promised response times. Keep at most 3 model calls including one repair and 2 searches. This supersedes the initial 30-second job budget below.

Owner root. All routes are same-origin JSON unless stated. Browser fetch uses credentials. Root implements server; p8 frontend; pN agent/catalog; pM OpenShell environment. This is the implementation contract; feedback goes to root before incompatible edits.

## Browser routes

- `POST /api/sessions` body `{}` -> `{session_id}` and HttpOnly session cookie. Reuses a valid existing cookie. No secret token in response.
- `GET /api/health` -> `{status, worker_connected, model_configured, sandbox_verified, catalog_count, version}`. Only actual observations may set flags true. A connected local worker does not imply OpenShell verified.
- `POST /api/photos` multipart `file` (JPEG/PNG <=8MiB) -> `{photo_id,width,height}`; requires cookie. Server normalizes orientation/resolution and strips EXIF. Worker receives normalized bytes only.
- `POST /api/requests` body: `{schema_version:1, session_id, question, photo_id:null|string, dataset_mode:'real_place'|'fictional_task', response_language:'en'|'ko', location:null|{lat,lng,origin:'gps'|'selected'}, radius_m:500|1000|2000|3000, confirmed_food_id:null|string, confirmed_shop_id:null|string}` -> HTTP202 `{request_id,status:'queued',poll_url}`. Unknown fields rejected. New request supersedes older queued/running work for this session. JSON errors `{error_code,detail}`.
- `GET /api/requests/{id}` -> `{request_id,status:'queued'|'running'|'completed'|'failed'|'superseded',result:null|Result,error_code:null|string}`. Session ownership enforced. UI polls <=1sec, stops on terminal states and ignores old IDs.
- `GET /api/results/{id}/download?format=json|html|md` -> session-owned saved result download. Server names and owns files. No model-selected paths.

## Worker routes

Header `Authorization: Bearer <WORKER_TOKEN>`, separate from browser cookie. Root creates local token; no hardcoded/default token. Current MVP one active worker. All assignments/results carry matching session/request IDs.
- `GET /worker/jobs/next` -> 204 or `{session_id,request_id,request:Request,history:[{role:'user'|'assistant',content:string}],allowed_source_ids:[string]}`. Worker claim is atomic, at most one claim per job. Server handles expiration.
- `GET /worker/photos/{photo_id}?request_id=...` -> normalized JPEG, only the assigned active request and owning session's photo.
- `POST /worker/search` body `{session_id,request_id,food_id:null|string,shop_id:null|string,radius_m}` -> `{places:Place[],catalog_count,scope_label}`. Server uses current request's location, bounds and catalog. No arbitrary URL, address or query text. No location => `{places:[],needs_location:true,...}`. Search cap 2 per job.
- `POST /worker/results` body `{session_id,request_id,result:Result}` -> `{saved:true,result_id}`. Stale job ->409, invalid data ->422. Server validates before creating new permanent files. Worker has no direct output write permission.
- `POST /worker/fail` body `{session_id,request_id,error_code,detail}` -> `{accepted:true}`. Detail must be sanitized; no upstream tokens/body dump.

## Result (all fields present, null/[] when unused)

```ts
type Place = { place_id:string; name:string; lat:number; lng:number; distance_m:number; source_id:string; catalog_version:string };
type Result = {
 schema_version:1; session_id:string; request_id:string; captured_at:string;
 dataset_mode:'real_place'|'fictional_task'; status:'need_confirmation'|'ready'|'failed';
 speech_text:string; response_language:'en'|'ko';
 scene:{food_candidates:{id:string;name_ko:string;name_en:string}[];confirmed_food_id:string|null;confirmed_shop_id:string|null};
 places:Place[];
 menus:{name_ko:string;description:string;evidence_ids:string[];unknowns:string[]}[];
 claims:{text:string;scope:'menu'|'operation'|'culture';evidence_ids:string[]}[];
 evidence:{id:string;source:string;as_of:string|null;type:'document'|'live_statement'|'example';dataset_id:string}[];
 conflicts:{evidence_ids:string[];decision:string;reason:string}[];
 itinerary:{time:string;activity:string;buffer_minutes:number|null;evidence_ids:string[]}[];
 order_ko:string|null;unknowns:string[];next_question:string|null;error_code:string|null;
};
```

Maximum 3 places, 3 menus, 3 food candidates. Result coordinates must match catalog. All cited evidence IDs must exist in approved mode-specific source data; claim presence does not prove truth. `fictional_task` must have `places=[]`. API returns saved result ID equal to request ID. UI uses `/api/results/{request_id}/download?format=json` etc. Result statuses are distinct from job states.

## Catalog integration — pN owns service/catalog.py

- `catalog_summary() -> dict` returns `{catalog_count,scope_label,catalog_version}`.
- `search_places(food_id, shop_id, location, radius_m) -> dict` returns `{places,catalog_count,scope_label,needs_location?}`; plain JSON objects, no service model imports. Server rejects unknown IDs before/using catalog helper.
- `get_place(place_id) -> dict|None` canonical Place base (distance optional); `valid_food_ids() -> set[str]`.
- `evidence_for_mode(mode) -> list[dict]` returns approved evidence records matching Result.evidence shape, source IDs stable. Additional source text stored only in data/ for agent reading.
- `food_candidates() -> list[dict]` gives id/name_ko/name_en.

## Agent integration — pN owns agent/

Use `httpx`, standard library, optional Pillow; no extra provider SDK required. Env `GUIDE_SERVER_URL`, `WORKER_TOKEN`, `NVIDIA_API_KEY`, `NVIDIA_BASE_URL` default `https://integrate.api.nvidia.com/v1`, `NVIDIA_MODEL` default `nvidia/nemotron-nano-12b-v2-vl`. Real HTTPS OpenAI-compatible chat endpoint; confirm actual model API. Never fake a reply when credential/runtime fails. Implement `python -m agent.worker` polling loop and CLI single job mode if helpful. Poll/photo/search/result calls confined to fixed service host; source files read from approved data directory. Max3 model calls (incl1 schema repair), max2 searches, <=30sec per job initially. Upstream error ->worker/fail; credentials never printed. Distinguish `RUN_CONTEXT=local-dev|openshell`; setting the flag alone is not runtime evidence.

Initial flow: photo+question -> actual model food/intent/uncertainty/tool decision -> read evidence/search tool as applicable -> grounded structured output. Require user confirmation for ambiguous identity. Returned Place/evidence fields come from tool/catalog, never model coordinates. Carry prior intent via job.history and confirmed IDs. Food/shop/menu unknowns and dietary uncertainty must be explicit. No external booking/order/network actions.

## Frontend UX — p8

React/TS/Vite, Leaflet1.9.4, white mobile-first design. API relative /api; Vite proxies to http://127.0.0.1:8000. Upload photo and editable speech transcript. en primary + ko toggle, browser speech capture/TTS with capability/error messages and text fallback. User-selectable Seochon demo point (37.5790,126.9730) visibly labeled, never fake GPS. Radius controls, map marker popup text escaped, OSM attribution retained, catalog scope label. Photo preview stays local object URL. Display current status, confirmations, evidence/menu/culture cards, Korean question, download. New request stops speech and dims old results. Device/media permissions requested on click only. API outage/auth/expired session handled visibly. Do not mark fixture data as live. Testing fixtures stay in tests/development modes.

## 16:42 visual-topic continuity extension

- Scene adds optional observed_place_name:string|null (default null, max120): the model's tentative freely recognized landmark name; never a confirmed identity or GPS position.
- Broker retains the latest qualified observation in the same session and dataset mode and supplies job.last_visual_observation with landmark_name, photo_id, question, is_cultural_landmark, identification_supported and same_photo.
- A short affirmative reply can refer to the preceding spoken suggestion even when a fresh camera frame has a new photo ID. An explicit new target/question takes priority; previous observation is not proof of a new frame's identity.
- Observation context resets on dataset-mode changes and on a subsequent observation with no named landmark. It stays separate from visitor preferences in manual conversation history.
- A named landmark outside the nearby-search catalogue must not be replaced with an unrelated catalogue candidate. Explanations may use approved evidence with matching entity_names; absent evidence is reported without fabricated claims, coordinates or sources.
