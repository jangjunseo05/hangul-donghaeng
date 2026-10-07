export type Language = 'en' | 'ko'
export type DatasetMode = 'real_place' | 'fictional_task'
export type Location = { lat: number; lng: number; origin: 'gps' | 'selected' }
export type Radius = 500 | 1000 | 2000 | 3000
export type Place = { place_id: string; name: string; lat: number; lng: number; distance_m: number; source_id: string; catalog_version: string }
export type Evidence = { id: string; source: string; as_of: string | null; type: 'document' | 'live_statement' | 'example'; dataset_id: string }
export type GuideResult = {
  schema_version: 1; session_id: string; request_id: string; captured_at: string;
  dataset_mode: DatasetMode; status: 'need_confirmation' | 'ready' | 'failed';
  speech_text: string; response_language: Language;
  scene: { food_candidates: { id: string; name_ko: string; name_en: string }[]; confirmed_food_id: string | null; confirmed_shop_id: string | null };
  places: Place[];
  menus: { name_ko: string; description: string; evidence_ids: string[]; unknowns: string[] }[];
  claims: { text: string; scope: 'menu' | 'operation' | 'culture'; evidence_ids: string[] }[];
  evidence: Evidence[];
  conflicts: { evidence_ids: string[]; decision: string; reason: string }[];
  itinerary: { time: string; activity: string; buffer_minutes: number | null; evidence_ids: string[] }[];
  order_ko: string | null; unknowns: string[]; next_question: string | null; error_code: string | null;
}
export type GuideRequest = {
  schema_version: 1; session_id: string; question: string; photo_id: string | null;
  dataset_mode: DatasetMode; response_language: Language; location: Location | null;
  radius_m: Radius; confirmed_food_id: string | null; confirmed_shop_id: string | null;
}
export type Health = { status: string; worker_connected: boolean; model_configured: boolean; sandbox_verified: boolean; catalog_count: number; version: string }
export type Job = { request_id: string; status: 'queued' | 'running' | 'completed' | 'failed' | 'superseded'; result: GuideResult | null; error_code: string | null }
