import type { GuideResult } from '../types'
import type { Story } from './cards'

/**
 * Story for the answer sheet: `GuideResult.landmark_card` (contract) first. Older results without a card
 * fall back to culture claims in the first block only; the other blocks are left empty rather than invented.
 */
export function storyFromResult(result: GuideResult): Story | null {
  if (result.landmark_card) return result.landmark_card
  const culture = result.claims.filter(claim => claim.scope === 'culture')
  if (!culture.length) return null
  const evidence = [...new Set(culture.flatMap(claim => claim.evidence_ids))]
  const verification = evidence.length ? 'catalog' : 'model_unverified'
  return {
    name: result.scene.observed_place_name?.trim() || result.places.find(place => place.place_id === result.scene.confirmed_place_id)?.name || '',
    blocks: { what_it_is: { text: culture.map(claim => claim.text).join(' '), evidence_ids: evidence, verification } },
    verification, evidence_ids: evidence,
  }
}
