# API contract v1 — 2026-10-07

> 2026-10-27 phase 2 extension (camera + tabs + TTS) is at the end of this file and is authoritative over earlier wording. Still `schema_version: 1`; every change is an added optional field or a new route.

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

## 16:52 nearby restaurants from visual context

- SearchRequest adds live:boolean=false and landmark_name:string|null. live=true is restricted to restaurant lookups; a named center must match the assigned session's latest visual landmark suggestion.
- The trusted broker resolves the public landmark name or uses the user's chosen location, then retrieves nearby named restaurants from fixed Nominatim/Overpass endpoints. No model URLs, photos or credentials leave through this tool.
- External network lookup runs outside the session lock. Up to three source-backed OSM places and their fetched evidence are recorded per job; result places/evidence must match the recorded tool output.
- GuideResult adds optional search_origin:Location|null and search_origin_label:string|null, both bound to the tool result. A geocoded landmark center is a search reference, not the visitor's confirmed GPS.
- OpenStreetMap results are nearby restaurant candidates sorted by straight-line distance; no verified ratings, popularity, opening hours or allergy claims. Lookup failure/empty coverage is explicit.
- Browser displays live results on the map and opens OSM details for external places instead of submitting unrecognized catalogue IDs.

## 2026-10-27 phase 2 extension — camera + 3 tabs + TTS (authoritative, additive)

Source of truth is `shared/models.py`. JSON Schemas are generated by `python -m shared.export_schemas`, and `tests/unit/test_contract.py` fails if they drift. Complete, validated example payloads live in `shared/examples/*.json`; frontend fixtures should copy them. Entries named `osm:*:1`/`osm:*:2` or `FIXTURE` are illustrative, not real OSM records.

Route status (M2, 2026-10-27): all routes below are implemented and covered by unit tests with mocked OSM, Wikipedia and TTS servers. None has run against live external services, Magpie or the L40S yet. `POST /api/tts` returns 503 until `TTS_BASE_URL` is configured.

### Verification labels (used by cards)

`verification: 'catalog' | 'public_source' | 'model_unverified'`
- `catalog`: cites records in `data/evidence.json`.
- `public_source`: cites a record the broker fetched from a fixed public source (OSM, Wikipedia) and stored with its URL and fetch time.
- `model_unverified`: model general knowledge. `evidence_ids` may be `[]`. UI must show "확인 필요 / Unverified" on that block.

Rules:
- A block whose label is not `model_unverified` needs at least one `evidence_id`.
- Card-level `verification` is the weakest block label (`catalog` < `public_source` < `model_unverified`).
- Card-level `evidence_ids` is the union of the block ids.

### `LandmarkCard` (4 blocks)

```ts
type StoryBlock = { text: string /*≤600*/; evidence_ids: string[]; verification: Verification; analogy: boolean /*explanatory framing, not a fact*/ };
type LandmarkCard = {
  schema_version: 1; place_id: string | null /*null = model-only, unmatched*/; name: string; lang: 'en'|'ko';
  blocks: { what_it_is: StoryBlock; why_it_matters: StoryBlock; what_to_look_for: StoryBlock; fun_fact: StoryBlock | null };
  visit_note: StoryBlock | null /*hours/fees/closures only; check on visit day*/;
  evidence_ids: string[]; verification: Verification;
};
```
- `GET /api/landmarks/{place_id}/card?lang=en|ko` returns `200 LandmarkCard` or `404 {error_code:'CARD_NOT_FOUND'}`. It needs the session cookie and makes no model call, because cards are authored content in `data/`.
- The card is also returned inline as `GuideResult.landmark_card` (default `null`) when a confirmed place is explained in the camera story sheet.
- Example `shared/examples/landmark-card.ko.json`:
```json
{"schema_version":1,"place_id":"local:gyeongbokgung","name":"경복궁","lang":"ko",
 "blocks":{"what_it_is":{"text":"경복궁은 1395년에 지은 궁궐로, 조선 왕조가 처음 세운 궁궐이에요.","evidence_ids":["wikipedia:gyeongbokgung","visitseoul:gyeongbokgung-culture"],"verification":"catalog"},
  "why_it_matters":{"text":"조선의 중심 궁궐이었어요. 나라의 '본부' 같은 곳이라고 생각하면 쉬워요.","evidence_ids":["visitseoul:gyeongbokgung-culture"],"verification":"catalog","analogy":true},
  "what_to_look_for":{"text":"궁 안에 국립고궁박물관과 국립민속박물관, 두 박물관이 있어요.","evidence_ids":["wikipedia:gyeongbokgung"],"verification":"public_source"},
  "fun_fact":{"text":"'경복궁'은 '큰 복을 누리는 궁궐'이라는 뜻이에요.","evidence_ids":["wikipedia:gyeongbokgung"],"verification":"public_source"}},
 "visit_note":{"text":"화요일 정기 휴궁(공휴일 예외 있음). 관람시간·요금은 방문일에 확인하세요.","evidence_ids":["visitseoul:gyeongbokgung-operation"],"verification":"catalog"},
 "evidence_ids":["visitseoul:gyeongbokgung-culture","visitseoul:gyeongbokgung-operation","wikipedia:gyeongbokgung"],"verification":"public_source"}
```
- `landmark-card.model-unverified.en.json` shows `place_id:null` with `model_unverified` blocks.

### `GET /api/nearby?tab=food|landmark&lat=<num>&lng=<num>&radius_m=500|1000|2000|3000`

This route makes no model call and takes no photo. It requires the session cookie.
- The broker merges catalog places within the radius with OSM results from fixed endpoints:
  - food: `amenity=restaurant|cafe|fast_food`
  - landmark: `tourism=attraction|museum|viewpoint` and `historic=*`
- Results are sorted by straight-line distance, with at most 20. The route works worldwide.
- `lat`/`lng` are the search origin only. Device GPS is not stored and is not echoed except as `origin`.

```ts
type NearbyPlace = { place_id: string /*local:* or osm:<node|way|relation>:<id>*/; name: string; name_en: string|null;
  kind: 'restaurant'|'landmark'; category: string|null /*e.g. "historic=palace"*/; lat: number; lng: number;
  distance_m: number /*straight line, ≤3000*/; source_id: string; osm_url: string|null; has_card: boolean };
type NearbyResponse = { schema_version: 1; tab: 'food'|'landmark'; origin: {lat,lng,origin:'gps'|'selected'}; radius_m: 500|1000|2000|3000;
  places: NearbyPlace[]; evidence: Evidence[]; attribution: string; unknowns: string[]; error_code: string|null };
```
- An external failure still returns `200`, with `places:[]` and `error_code` set to one of `nearby_timeout|nearby_unavailable|nearby_busy|nearby_invalid_response` (see `shared/examples/nearby.error.json`).
- Bad query parameters return `422`.
- Ratings, popularity, opening hours and allergy safety are never asserted.
- `attribution` must be shown with the list.
- Example (`shared/examples/nearby.food.json`, abridged):
```json
{"schema_version":1,"tab":"food","origin":{"lat":37.579,"lng":126.973,"origin":"selected"},"radius_m":1000,
 "places":[{"place_id":"local:tosokchon","name":"토속촌삼계탕","name_en":"Tosokchon Samgyetang","kind":"restaurant","category":"cuisine=korean",
            "lat":37.57760304027,"lng":126.971632166657,"distance_m":197.0,"source_id":"visitseoul:tosokchon","osm_url":null,"has_card":false}],
 "evidence":[],"attribution":"© OpenStreetMap contributors (ODbL)",
 "unknowns":["Ratings, popularity, current opening and allergy suitability are not verified."],"error_code":null}
```

### `GET /api/routes?near=<lat>,<lng>&lang=en|ko`

This route returns deterministic templates and makes no model call. It returns at most 2 routes around the Gyeongbokgung area.
- `near` is optional. Templates whose first stop is more than 3 km from `near` are omitted, so an empty `routes` list is valid abroad.
- Distances are haversine distances between the stop coordinates (`distance_basis:'straight_line'`).
- `est_walk_min = ceil(straight_line_m × 1.3 / 70)` is a heuristic.
- `route_verified` is always `false`, and `ui_note` must be shown.

```ts
type RouteStop = { order: number /*1..n*/; place_id: string; name: string; kind: 'restaurant'|'heritage'|'landmark'; lat: number; lng: number;
  dwell_min_estimate: number; note: string|null; has_card: boolean };
type RouteLeg = { from_place_id: string; to_place_id: string; straight_line_m: number; est_walk_min: number; route_verified: false; note: string|null };
type Route = { route_id: string; title: string; summary: string; stops: RouteStop[]; legs: RouteLeg[] /*consecutive stops*/;
  total_straight_line_m: number /*= sum(legs)*/; total_dwell_min_estimate: number; distance_basis: 'straight_line'; ui_note: string; evidence_ids: string[] };
type RoutesResponse = { schema_version: 1; lang: 'en'|'ko'; routes: Route[]; unknowns: string[] };
```
- Full examples are in `shared/examples/routes.en.json` and `routes.ko.json`:
  - `route:palace-in-a-nutshell`: 4 stops, 891 m.
  - `route:palace-to-hanok`: 3 stops, 1057 m.
- Leg distances were recomputed from the coordinates and match the research values within 1 m.

### `POST /api/tts` — server speech (NVIDIA Magpie TTS Multilingual)

Body: `{text: string /*1..600*/, lang: 'ko'|'en'}`. It requires the session cookie.
- The voice is chosen by the server, never by the client. It is set with `TTS_VOICE_KO`/`TTS_VOICE_EN` after the user picks a voice.
- `200` returns `Content-Type: audio/wav`. M2 may switch to `audio/mpeg`, so play the response as a Blob whatever its type. The `X-TTS-Voice` header names the voice. The server may cache identical `(lang,text)` requests.
- `503 {error_code:'TTS_UNAVAILABLE'}` means Magpie is not configured or not reachable. It is always 503 while `TTS_BASE_URL` is unset. The frontend then falls back to browser TTS, preferring a female voice.
- `429 {error_code:'TTS_BUSY'}` (M2, single-flight per session) also means fall back.
- `422` means the text is empty or too long, or `lang` is unknown.
- `401` means there is no session.

### Observe result additions (`GuideResult.scene`)

`observed_place_source: 'catalog'|'osm'|'model'|null` (default null):
- `catalog` or `osm`: the VLM made a closed choice among broker-issued GPS candidates. `place_candidates[0]` is the selected one, and the rest (at most 3 in total) are alternatives for the "Not this" chips. OSM candidate ids look like `osm:node:123`.
- `model`: free recognition outside the candidates. `observed_place_name` is tentative and never verified.
- `null`: nothing was recognized.

`observed_place_confidence: 'high'|'medium'|'low'|null` (default null) is the model's self-report, **not a calibrated probability**. The UI may use it only for wording, such as "This may be…".

Unchanged: a frame without a cultural landmark returns `status:'ready'`, `speech_text:''` and `next_question:null`. The app stays silent and does not interrupt.

Confirmation: `confirmed_place_id` currently accepts catalog ids only. From M2 it also accepts `osm:*` ids, but only ids the broker has issued to this session in a nearby or observe result.

Example (`shared/examples/result.observe.json`, scene only):
```json
{"food_candidates":[],"confirmed_food_id":null,"confirmed_shop_id":null,
 "place_candidates":[{"id":"local:gyeongbokgung","name_ko":"경복궁","name_en":"Gyeongbokgung Palace"},{"id":"local:gwanghwamun","name_ko":"광화문","name_en":"Gwanghwamun Gate"}],
 "confirmed_place_id":null,"observed_place_name":"Gyeongbokgung Palace","observed_place_source":"catalog","observed_place_confidence":"medium"}
```

### Job progress stage

`GET /api/requests/{id}` adds `stage: 'observing'|'matching'|'writing'|null` (default null).
- It is a hint only, and it is non-null only while `status:'running'`.
- The stages are: observing = reading the frame, matching = choosing among place candidates, writing = drafting the explanation.
- The worker reports the stage with `POST /worker/progress {session_id,request_id,stage}`. It uses the same auth and stale-job rules as `/worker/results`.

Example: `{"request_id":"r-example","status":"running","stage":"matching","result":null,"error_code":null}`

### Observe frames vs the 20-photo bound

`POST /api/photos` accepts an optional multipart field `purpose: 'capture'|'observe'` (default `capture`). The response adds `purpose`.
- `capture` works as it does today. These photos count toward the 20-photo session bound and are owned by the session and downloadable.
- `observe` frames do **not** count toward that bound:
  - They are kept in a per-session ring of 2, and the oldest is evicted.
  - Only the worker for the request that references them can read them. They are never downloadable.
  - They are deleted when that request reaches a terminal state.
- A request with `interaction_mode:'observe'` may reference either purpose. An `ask` request that references an evicted `observe` frame fails with `404 PHOTO_NOT_FOUND`.
- Implemented in M2.

### 2026-10-27 M2 additions (implemented; additive)

**Card labels and sources** (decision 7)
- The server recomputes every label from the cited records and ignores the label written in the authored file or by the model:
  - a block citing any `wikipedia:`/`wikidata:`/`osm:` record is at least `public_source`;
  - a block citing only `data/evidence.json` records is `catalog`;
  - a block with no recognised evidence is `model_unverified`, and unknown ids are dropped.
- `LandmarkCard.sources: {id,url,title|null,license|null,verification:'catalog'|'public_source'}[]` (default `[]`). When present, its ids equal `evidence_ids`.
- Show the link and the license only. Quoted source text (`quotes` in `data/evidence.json`) is never served (decision 6). Suggested captions (research §4):
  - EN: `Source: Wikipedia — “<title>”, CC BY-SA 4.0. Text adapted.`
  - KO: `출처: 위키백과 「<title>」, CC BY-SA 4.0. 내용을 쉽게 고쳐 썼어요.`
- Catalog cards: 5 places × en/ko (경복궁, 광화문, 근정전, 경회루, 북촌), authored by research and served without a model call. Because of the recomputation, 경복궁 `what_it_is` (which cites `wikipedia:gyeongbokgung`) is now `public_source`.

**`GET /api/nearby` parameters**
- Optional parameters: `origin=gps|selected` (default `selected`) and `lang=en|ko` (affects `unknowns`).
- OSM results are dropped when they share a name with a catalog place within 300 m.
- Every OSM place returned is **issued** to the session, which means it may later be sent as `confirmed_place_id`. Ids that were never issued return `422 UNKNOWN_PLACE`.
- Catalog interior stops (근정전, 경회루) appear in the landmark tab, but conversational heritage search skips them (`nearby_search:false` in `data/catalog.json`).

**`Route.visit_note: StoryBlock|null`** (default null)
- This is a dated visiting restriction. Example: `route:palace-to-hanok` → Bukchon red zone, 2024 notice, `seoul:bukchon-visit-restriction`, `catalog`.
- Its text is also appended to `ui_note`.
- Show it, along with the reference date, whenever that route is shown. The demo default is `route:palace-in-a-nutshell`.

**Confirmed external place** (`confirmed_place_id: 'osm:*'`, ask mode)
- The broker passes `confirmed_external_place {place_id,name,name_en,kind,category}` to the worker.
- The worker calls `POST /worker/wiki {session_id,request_id,lang}` at most once per job. The broker then fetches a Wikipedia summary from fixed hosts. The title comes from the OSM `wikipedia` tag, a Wikidata sitelink, or an exact title match only.
- The broker records the result as job evidence `wikipedia:<lang>:<pageid>` (`public_source`).
- The model writes the 4 blocks, and `allow_unverified` is true. The result has `landmark_card`, `claims` for the cited blocks, and an `unknowns` note when any block is `model_unverified`.
- The broker rejects a card whose labels, evidence or name do not match the records it fetched (`422 INVALID_CARD`).
- If no article exists, the card is `model_unverified`.
- For a confirmed **catalog** place, `GuideResult.landmark_card` is the prepared card. The broker checks that it equals `GET /api/landmarks/{id}/card`.

**Observe with a location** (worker-internal)
- The worker calls `POST /worker/search {kind:'landmark', live:true}` and gets `{candidates:[{id,name_ko,name_en,kind:'heritage'|'landmark',distance_m,source:'catalog'|'osm'}], error_code}`. Candidates are the nearest 5 within `min(radius_m,1000)`.
- The VLM then chooses one id or `unknown` (with `confidence` and `visual_cues`).
- `observed_place_source:'catalog'|'osm'` must name one of this job's candidates. The broker checks this and returns `422 INVALID_OBSERVATION` otherwise.
- If there are no candidates, or no location, observe falls back to free recognition, which reports `observed_place_source:'model'` when a name is recognised.

**Stage hints**: `observing` (frame fetched), `matching` (closed-set choice), `writing` (draft or card). The hint is best effort, and a lost update never fails a job.
