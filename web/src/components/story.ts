import type { GuideResult } from '../types'
import type { LandmarkCard } from '../draftTypes'
import type { Story } from './cards'

/**
 * Story for the answer sheet. Prefers the draft `landmark` card (M2 contract);
 * until then the culture claims fill the first block. Other blocks stay empty rather than invented.
 */
export function storyFromResult(result: GuideResult & { landmark?: LandmarkCard | null }): Story | null {
  if (result.landmark) return result.landmark
  const culture = result.claims.filter(claim => claim.scope === 'culture')
  if (!culture.length) return null
  const evidence = [...new Set(culture.flatMap(claim => claim.evidence_ids))]
  return {
    name: result.scene.observed_place_name?.trim() || result.places.find(place => place.place_id === result.scene.confirmed_place_id)?.name || '',
    name_local: null,
    blocks: { what_it_is: culture.map(claim => claim.text).join(' '), why_it_matters: null, what_to_look_for: null, fun_fact: null },
    verification: evidence.length ? 'catalog' : 'model_unverified',
    evidence_ids: evidence,
  }
}
