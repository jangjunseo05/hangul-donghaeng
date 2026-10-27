// Phase-2 contract types — mirror of shared/models.py (shared/api-contract.md "2026-10-27 phase 2 extension").
// shared/ is owned by the backend; change these only when that contract changes.
import type { Evidence, Language, Location, Radius } from './types'

export type Tab = 'look' | 'landmarks' | 'eat' | 'routes'
export type Verification = 'catalog' | 'public_source' | 'model_unverified'
export const VERIFICATION_RANK: Record<Verification, number> = { catalog: 0, public_source: 1, model_unverified: 2 }

export type StoryBlock = { text: string; evidence_ids: string[]; verification: Verification; analogy?: boolean }
export type StoryBlocks = { what_it_is: StoryBlock; why_it_matters: StoryBlock; what_to_look_for: StoryBlock; fun_fact: StoryBlock | null }
/** Attribution for a cited record: link + licence only, never the quoted source text. */
export type CardSource = { id: string; url: string; title: string | null; license: string | null; verification: 'catalog' | 'public_source' }
export type LandmarkCard = {
  schema_version: 1; place_id: string | null; name: string; lang: Language;
  blocks: StoryBlocks; visit_note: StoryBlock | null; evidence_ids: string[]; verification: Verification; sources?: CardSource[];
}

export type NearbyTab = 'food' | 'landmark'
export type NearbyPlace = {
  place_id: string; name: string; name_en: string | null; kind: 'restaurant' | 'landmark'; category: string | null;
  lat: number; lng: number; distance_m: number; source_id: string; osm_url: string | null; has_card: boolean;
}
/** Decision 6 (M4): upstream Overpass codes are part of the contract alongside the nearby_* codes. */
export type NearbyErrorCode = 'nearby_timeout' | 'nearby_unavailable' | 'nearby_busy' | 'nearby_invalid_response' | `overpass_${string}`
export type NearbyResponse = {
  schema_version: 1; tab: NearbyTab; origin: Location; radius_m: Radius; places: NearbyPlace[];
  evidence: Evidence[]; attribution: string; unknowns: string[]; error_code: NearbyErrorCode | string | null;
}

export type RouteStop = { order: number; place_id: string; name: string; kind: 'restaurant' | 'heritage' | 'landmark'; lat: number; lng: number; dwell_min_estimate: number; note: string | null; has_card: boolean }
export type RouteLeg = { from_place_id: string; to_place_id: string; straight_line_m: number; est_walk_min: number; route_verified: false; note: string | null }
export type Route = {
  route_id: string; title: string; summary: string; stops: RouteStop[]; legs: RouteLeg[];
  total_straight_line_m: number; total_dwell_min_estimate: number; distance_basis: 'straight_line'; ui_note: string; evidence_ids: string[];
  /** Dated visiting restriction for the route (e.g. Bukchon); check again on the visit day. */
  visit_note?: StoryBlock | null;
}
export type RoutesResponse = { schema_version: 1; lang: Language; routes: Route[]; unknowns: string[] }

export type JobStage = 'observing' | 'matching' | 'writing'
export type PlaceSource = 'catalog' | 'osm' | 'model'
export type Confidence = 'high' | 'medium' | 'low'
