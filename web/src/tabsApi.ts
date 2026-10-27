import { ApiError, getJson } from './api'
import type { Language, Location, Radius } from './types'
import type { LandmarkCard, NearbyResponse, NearbyTab, RoutesResponse } from './contract'
// Contract examples are imported directly from shared/examples (no copies). They are used only
// while a route is not implemented yet, and every such response is marked `fixture: true`.
import nearbyFood from '../../shared/examples/nearby.food.json'
import nearbyLandmark from '../../shared/examples/nearby.landmark.json'
import cardEn from '../../shared/examples/landmark-card.en.json'
import cardKo from '../../shared/examples/landmark-card.ko.json'
import routesEn from '../../shared/examples/routes.en.json'
import routesKo from '../../shared/examples/routes.ko.json'

export type Loaded<T> = { data: T; fixture: boolean }
/** Real contract responses that must not be replaced by a fixture. */
const CONTRACT_CODES = new Set(['CARD_NOT_FOUND'])
/** True when the route itself is missing (not yet implemented on this server), not a real answer. */
export function isUnimplemented(error: unknown) {
  return error instanceof ApiError && [404, 405, 501].includes(error.status) && !CONTRACT_CODES.has(error.code)
}
async function withFallback<T>(load: () => Promise<T>, fixture: () => T): Promise<Loaded<T>> {
  try { return { data: await load(), fixture: false } }
  catch (error) {
    if (isUnimplemented(error)) return { data: fixture(), fixture: true }
    throw error
  }
}

export const EXAMPLES = {
  nearby: { food: nearbyFood as NearbyResponse, landmark: nearbyLandmark as NearbyResponse },
  cards: [cardEn as LandmarkCard, cardKo as LandmarkCard],
  routes: { en: routesEn as RoutesResponse, ko: routesKo as RoutesResponse },
}

export function loadNearby(tab: NearbyTab, origin: Location, radius: Radius, signal?: AbortSignal) {
  const query = new URLSearchParams({ tab, lat: origin.lat.toFixed(6), lng: origin.lng.toFixed(6), radius_m: String(radius) })
  return withFallback(() => getJson<NearbyResponse>('/api/nearby?' + query, signal), () => EXAMPLES.nearby[tab])
}
/** Resolves `data: null` when the server says there is no card (404 CARD_NOT_FOUND). */
export async function loadCard(placeId: string, lang: Language, signal?: AbortSignal): Promise<Loaded<LandmarkCard | null>> {
  try {
    return await withFallback(() => getJson<LandmarkCard>(`/api/landmarks/${encodeURIComponent(placeId)}/card?lang=${lang}`, signal),
      () => EXAMPLES.cards.find(card => card.place_id === placeId && card.lang === lang) ?? EXAMPLES.cards.find(card => card.place_id === placeId) ?? null)
  } catch (error) {
    if (error instanceof ApiError && error.code === 'CARD_NOT_FOUND') return { data: null, fixture: false }
    throw error
  }
}
export function loadRoutes(lang: Language, near: Location | null, signal?: AbortSignal) {
  const query = new URLSearchParams({ lang })
  if (near) query.set('near', `${near.lat.toFixed(6)},${near.lng.toFixed(6)}`)
  return withFallback(() => getJson<RoutesResponse>('/api/routes?' + query, signal), () => EXAMPLES.routes[lang])
}
