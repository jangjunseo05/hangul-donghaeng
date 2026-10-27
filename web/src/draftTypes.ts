// DRAFT types for the tab screens (backend report §5, phase-2 rule 6).
// Not yet part of shared/api-contract.md: M2 replaces these with the agreed contract.
import type { Evidence, Language, Location, Radius } from './types'

export type Tab = 'look' | 'landmarks' | 'eat' | 'routes'
export type Verification = 'catalog' | 'public_source' | 'model_unverified'
export type DraftPlaceKind = 'restaurant' | 'heritage' | 'attraction'

export type DraftPlace = {
  place_id: string; name: string; name_en: string | null; kind: DraftPlaceKind;
  lat: number; lng: number; distance_m: number; category: string | null;
  source_id: string; source_url: string | null; catalog_version: string;
}
/** GET /api/nearby?tab=food|landmark&lat&lng&origin&radius_m (draft) */
export type NearbyResponse = {
  tab: 'food' | 'landmark'; search_origin: Location; search_origin_label: string | null;
  provider: 'OpenStreetMap'; places: DraftPlace[]; evidence: Evidence[]; error_code: string | null;
}
/** Four-block explanation for first-time visitors (research report §3). */
export type StoryBlocks = { what_it_is: string; why_it_matters: string | null; what_to_look_for: string | null; fun_fact: string | null }
export type LandmarkCard = {
  place_id: string; name: string; name_local: string | null; lang: Language;
  blocks: StoryBlocks; visitor_tips: string[]; evidence_ids: string[]; verification: Verification;
}
export type RouteStop = { place_id: string; name: string; name_local: string | null; lat: number; lng: number; dwell_minutes: number | null; note: string | null }
export type Route = {
  route_id: string; title: string; title_local: string | null; stops: RouteStop[];
  straight_line_total_m: number; disclaimers: string[];
}
export type NearbyQuery = { tab: 'food' | 'landmark'; location: Location; radius: Radius }
