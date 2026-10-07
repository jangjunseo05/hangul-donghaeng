# Design
## Source of truth
Active, 2026-10-07. Frontend scope only; ../AGENTS.md and ../shared/api-contract.md (e1233c6e82b987385722d2d682794aeb3149cb660edc0330d0e3e85de0fd5518). No prior UI/assets exist. Root documents remain root-owned.
## Brand
Warm, calm Korean travel companion. White and warm ivory, persimmon, deep forest. No claims of verified food safety.
## Product goals
Actual photo/voice questions, selected starting point, scoped catalog map, grounded answers and saved result.
## Personas and jobs
English-speaking visitor reading Hangul menus; Korean toggle for local questions.
## Information architecture
Single page: welcome, question/photo, location/map, answer/cards, evidence/download. Separate connection dialog.
## Design principles
Clear unknowns; explicit demo location; freshness and permission before convenience.
## Visual language
System fonts, generous whitespace, warm borders, soft corners, line icons. No invented restaurant imagery.
## Components
Header, photo picker, speech composer, radius controls, Leaflet map, answer, menu/evidence cards, status dialog.
## Accessibility
Labeled controls, keyboard focus, 44px touch targets, polite live status, native dialog, reduced motion.
## Responsive behavior
Single column mobile; two-column workspace desktop, no horizontal scroll.
## Interaction states
Offline, waiting, upload, queued, running, confirmation, ready, stale, failure, map tile failure, voice unsupported.
## Content voice
English primary; short friendly Korean. Internal infrastructure details only in connection dialog.
## Implementation constraints
React/TS/Vite, Leaflet1.9.4, credentials cookies, relative API; no mock replies in product.
## Open questions
[ ] root: actual model/OpenShell endpoint and served frontend; blocks product execution verification.
[ ] device tester: microphone/TTS availability and HTTPS; text fallback does not prove voice completion.
