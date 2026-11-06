import type { Confidence, JobStage, LandmarkCard, PlaceSource } from './contract'
export type Language = 'en' | 'ko'
export type DatasetMode = 'real_place' | 'fictional_task'
export type Location = { lat: number; lng: number; origin: 'gps' | 'selected' }
export type Radius = 500 | 1000 | 2000 | 3000
export type PlaceKind = 'restaurant' | 'heritage'
export type InteractionMode = 'ask' | 'observe'
export type Place = { place_id: string; name: string; lat: number; lng: number; distance_m: number; source_id: string; catalog_version: string; kind?: PlaceKind }
export type CatalogPlace = Omit<Place, 'distance_m' | 'kind'> & { name_en: string; kind: PlaceKind }
export type Catalog = { catalog_count: number; scope_label: string; catalog_version: string; places: CatalogPlace[] }
export type Candidate = { id: string; name_ko: string; name_en: string }
export type Evidence = { id: string; source: string; as_of: string | null; type: 'document' | 'live_statement' | 'example'; dataset_id: string }
export type GuideResult = {
  schema_version: 1; session_id: string; request_id: string; captured_at: string;
  dataset_mode: DatasetMode; status: 'need_confirmation' | 'ready' | 'failed';
  speech_text: string; response_language: Language;
  scene: { food_candidates: Candidate[]; confirmed_food_id: string | null; confirmed_shop_id: string | null; place_candidates?: Candidate[]; confirmed_place_id?: string | null; observed_place_name?: string | null; observed_place_source?: PlaceSource | null; observed_place_confidence?: Confidence | null };
  search_origin?: Location | null;
  search_origin_label?: string | null;
  places: Place[];
  menus: { name_ko: string; description: string; evidence_ids: string[]; unknowns: string[] }[];
  claims: { text: string; scope: 'menu' | 'operation' | 'culture'; evidence_ids: string[] }[];
  evidence: Evidence[];
  conflicts: { evidence_ids: string[]; decision: string; reason: string }[];
  itinerary: { time: string; activity: string; buffer_minutes: number | null; evidence_ids: string[] }[];
  order_ko: string | null; unknowns: string[]; next_question: string | null; error_code: string | null;
  landmark_card?: LandmarkCard | null;
}
export type GuideRequest = {
  schema_version: 1; session_id: string; question: string; photo_id: string | null;
  dataset_mode: DatasetMode; response_language: Language; location: Location | null;
  radius_m: Radius; confirmed_food_id: string | null; confirmed_shop_id: string | null;
  confirmed_place_id?: string | null; interaction_mode?: InteractionMode;
}
/** Stored OpenShell deployment evidence summarized by the broker; describes a past deployment, not the running worker. */
export type SandboxEvidence = { scope: 'stored_deployment_evidence'; runtime: string; worker: string | null; captured_at: string | null; policy_hash: string | null; policy_loaded: boolean; boundary_verdict: string | null; boundary_sandbox?: string | null; boundary_checks_passed: number; boundary_checks_total: number; policy_read_only?: string[]; policy_read_write?: string[]; policy_network_allow?: string[] }
export type Health = { status: string; worker_connected: boolean; model_configured: boolean; sandbox_verified: boolean; sandbox_evidence?: SandboxEvidence | null; catalog_count: number; version: string }
/** One broker-observed step (shared/api-contract.md "Agent trace"). */
export type TraceEvent = { t_ms: number; kind: 'broker' | 'sandbox' | 'stage' | 'tool' | 'check'; name: string; ok: boolean; detail: string | null }
export type Job = { request_id: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'superseded'; stage?: JobStage | null; trace?: TraceEvent[]; result: GuideResult | null; error_code: string | null }

/** F2 source review mode (shared/api-contract.md "Source review mode"); draft. */
export type ReviewExclusion = 'irrelevant' | 'not_selected' | 'outdated' | 'conflict_superseded' | 'untrusted_instruction' | 'unreadable'
export type ReviewSource = { id: string; path: string; sha256: string; as_of: string | null; verdict: 'used' | 'excluded'; reason: ReviewExclusion | null; note: string | null }
export type ReviewQuote = { source_id: string; text: string }
export type ReviewClaim = { text: string; source_ids: string[]; quotes: ReviewQuote[] }
export type ReviewConflict = { source_ids: string[]; quotes: ReviewQuote[]; reason: string; resolution: string }
/** verified_input is set by the broker only: true when it re-read and verified the demo files itself. */
export type ReviewResult = { status: 'answered' | 'insufficient_evidence'; question: string; condition: string | null; input_label: string; sources: ReviewSource[]; claims: ReviewClaim[]; conflicts: ReviewConflict[]; unknowns: string[]; verified_input: boolean }
export type ReviewInputs = { input_label: string; sources: { id: string; path: string; sha256: string; bytes: number; as_of: string | null }[] }
export type ReviewJob = { request_id: string; status: Job['status']; trace?: TraceEvent[]; result: ReviewResult | null; error_code: string | null }

/** F3 sandbox probe (shared/api-contract.md "Sandbox probe"); draft. */
export type ProbeAttemptId = 'read_outside_allowlist' | 'write_code_dir' | 'egress_unlisted_host' | 'broker_unlisted_path'
export type ProbeAttempt = { id: ProbeAttemptId; expected: 'denied'; observed: 'denied' | 'allowed' | 'error'; detail: string | null; broker_received: number | null }
export type ProbeResult = { run_context: string; finished_at: string; attempts: ProbeAttempt[] }
export type ProbeJob = { request_id: string; status: Job['status']; trace?: TraceEvent[]; result: ProbeResult | null; error_code: string | null }
