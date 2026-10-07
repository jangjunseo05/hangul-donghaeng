# Design
## Source of truth
Active, 2026-10-07. Frontend scope only; ../AGENTS.md and ../shared/api-contract.md, authoritative14:26 culture/camera extension (705d085c41807858807a5b088970e06b9184a40778fcbec89f3af7733a464e16). Existing photo/voice/map/cards remain. Root documents remain root-owned. User explicitly approved local camera preview and opt-in sampled-frame analysis over the earlier food-only scope.
## Brand
Warm, calm Korean travel companion. White and warm ivory, persimmon, deep forest. No claims of verified food safety.
## Product goals
Korean history and cultural context through photo/voice questions and camera preview; confirmed cultural starting points, nearby meals, grounded answers and saved result. Preview and automatic transmission have separate consent. Model input is sampled photos, not continuous video.
## Personas and jobs
English-speaking visitor exploring Korean heritage, streets and nearby food; Korean toggle for local questions.
## Information architecture
Single page: welcome, question/photo, location/map, answer/cards, evidence/download. Separate connection dialog.
## Design principles
Clear unknowns; explicit selected/demo location; freshness and permission before convenience. Gwanghwamun is Gyeongbokgung's main gate within the same complex, not a second palace or a separate long journey.
## Visual language
System fonts, generous whitespace, warm borders, soft corners, line icons. No invented restaurant imagery.
## Components
Header, local camera preview/capture, opt-in automatic companion, photo fallback, speech composer, curated starting-point selector, radius controls, Leaflet map, food/place confirmation, culture/menu/evidence cards, status dialog.
## Accessibility
Labeled controls, keyboard focus, 44px touch targets, polite live status, native dialog, reduced motion.
## Responsive behavior
Single column mobile; two-column workspace desktop, no horizontal scroll.
## Interaction states
Offline, waiting, upload, queued, running, confirmation, ready, stale, failure, map tile failure, voice unsupported; camera permission pending/denied, unavailable/busy device, capture readiness and stopped preview. Automatic frames wait20seconds after a completed response, never overlap and defer to manual input. Hidden tabs stop camera/automatic transmission; confirmation, error and photo limit stop automatic mode. Repeated automatic suggestions are not repeatedly spoken.
## Content voice
English primary; short friendly Korean. Internal infrastructure details only in connection dialog.
## Implementation constraints
React/TS/Vite, Leaflet1.9.4, credentials cookies, relative API; no mock replies in product. getUserMedia requests environment preference and audio:false only after Start. Captured JPEGs use the existing upload endpoint. Cultural confirmation uses catalog coordinates. Tests use explicitly synthetic streams/API fixtures and do not establish Android or model execution.
## Open questions
[ ] root: culture/camera worker revision, live model/OpenShell results and served frontend after integration; live validation waits for root GO.
[x] Android rear-camera preview and captured image persisting after Stop: user-reported physical hardware PASS on2026-10-07; no independent replay by this frontend worker.
[x] Actual Android Korean and English speech input: both PASS by the latest user report on2026-10-07. Earlier TTS confirmation remains separate and does not establish Android TTS.
[ ] Android TTS, Android background handling, automatic frame analysis and the integrated culture/camera/voice-to-model journey; runtime verification waits for root GO. Confirmation stops automatic mode; the demonstrated next frame requires user confirmation and re-enabling.
