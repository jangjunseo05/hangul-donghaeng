// DEVELOPMENT FIXTURES for the tab screens until the M2 contract lands.
// Story text: research report §3.3 (evidence ids from data/evidence.json). Route stop
// coordinates other than catalog places are approximate and for layout only.
import type { Language } from '../types'
import type { DraftPlace, LandmarkCard, NearbyResponse, Route } from '../draftTypes'

export const FIXTURE_LABEL = { en: 'Development fixture · contract pending', ko: '개발용 예시 데이터 · 계약 확정 전' }
const ORIGIN = { lat: 37.5759, lng: 126.9768, origin: 'selected' as const }

const landmarkPlaces: DraftPlace[] = [
  { place_id: 'local:gyeongbokgung', name: '경복궁', name_en: 'Gyeongbokgung Palace', kind: 'heritage', lat: 37.57590409118165, lng: 126.97684292625048, distance_m: 0, category: 'palace', source_id: 'visitseoul:gyeongbokgung-location', source_url: null, catalog_version: 'fixture' },
  { place_id: 'local:gwanghwamun', name: '광화문', name_en: 'Gwanghwamun Gate', kind: 'heritage', lat: 37.5760179589004, lng: 126.976788008924, distance_m: 14, category: 'gate', source_id: 'visitkorea:gwanghwamun-location', source_url: null, catalog_version: 'fixture' },
  { place_id: 'fixture:sample-museum', name: '예시 박물관', name_en: 'Sample Museum (fixture)', kind: 'attraction', lat: 37.5788, lng: 126.9787, distance_m: 360, category: 'museum', source_id: 'fixture-source', source_url: null, catalog_version: 'fixture' },
]
const foodPlaces: DraftPlace[] = [
  { place_id: 'local:tosokchon', name: '토속촌 삼계탕', name_en: 'Tosokchon Samgyetang', kind: 'restaurant', lat: 37.57760304027, lng: 126.971632166657, distance_m: 480, category: 'korean', source_id: 'visitseoul:tosokchon', source_url: null, catalog_version: 'fixture' },
  { place_id: 'fixture:noodle', name: '예시 국숫집', name_en: 'Sample Noodle House (fixture)', kind: 'restaurant', lat: 37.5772, lng: 126.9729, distance_m: 380, category: 'noodle', source_id: 'fixture-source', source_url: null, catalog_version: 'fixture' },
  { place_id: 'fixture:tea', name: '예시 찻집', name_en: 'Sample Tea Room (fixture)', kind: 'restaurant', lat: 37.5749, lng: 126.9739, distance_m: 290, category: 'cafe', source_id: 'fixture-source', source_url: null, catalog_version: 'fixture' },
]
export const fixtureNearby = (tab: 'food' | 'landmark'): NearbyResponse => ({
  tab, search_origin: ORIGIN, search_origin_label: 'Gyeongbokgung', provider: 'OpenStreetMap',
  places: tab === 'food' ? foodPlaces : landmarkPlaces,
  evidence: [{ id: 'fixture-source', source: 'https://example.com/fixture', as_of: null, type: 'example', dataset_id: 'test-only' }],
  error_code: null,
})

const stories: Record<string, Record<Language, LandmarkCard>> = {
  'local:gyeongbokgung': {
    en: { place_id: 'local:gyeongbokgung', name: 'Gyeongbokgung Palace', name_local: '경복궁', lang: 'en', verification: 'catalog', evidence_ids: ['visitseoul:gyeongbokgung-culture'], visitor_tips: ['Opening days and hours change — check on the day of your visit.'], blocks: {
      what_it_is: 'Gyeongbokgung is a royal palace built in 1395 for Joseon, the kingdom that ruled Korea before modern times.',
      why_it_matters: 'It was the main palace — think of it as the "headquarters" where the king lived and ran the country.',
      what_to_look_for: 'Walk in through the big front gate, Gwanghwamun, and notice how the halls line up one behind another.',
      fun_fact: 'Its west gate, Yeongchumun, opened to the public only in December 2018, linking the palace to the Seochon neighborhood.' } },
    ko: { place_id: 'local:gyeongbokgung', name: '경복궁', name_local: 'Gyeongbokgung Palace', lang: 'ko', verification: 'catalog', evidence_ids: ['visitseoul:gyeongbokgung-culture'], visitor_tips: ['개방일과 시간은 바뀔 수 있어요. 방문 당일 확인해 주세요.'], blocks: {
      what_it_is: '경복궁은 1395년에 지은 조선 왕조의 궁궐이에요. 조선은 근대 이전 한국을 다스린 나라예요.',
      why_it_matters: '조선의 중심 궁궐이었어요. 왕이 살면서 나라를 다스린 "본부" 같은 곳이라고 생각하면 쉬워요.',
      what_to_look_for: '정문인 광화문으로 들어가서 건물들이 앞뒤로 줄지어 선 모습을 보세요.',
      fun_fact: '서쪽 문인 영추문은 2018년 12월에야 일반에 열려 서촌 동네와 이어졌어요.' } },
  },
  'local:gwanghwamun': {
    en: { place_id: 'local:gwanghwamun', name: 'Gwanghwamun Gate', name_local: '광화문', lang: 'en', verification: 'catalog', evidence_ids: ['visitkorea:gwanghwamun-culture'], visitor_tips: [], blocks: {
      what_it_is: "Gwanghwamun is the main south gate of Gyeongbokgung Palace — the palace's front door.",
      why_it_matters: 'It shows how royal rank shaped everyday movement: the middle arch was for the king, and the side arches for the crown prince and officials.',
      what_to_look_for: "Count the three arched openings and look at the center one — the king's path.",
      fun_fact: 'After restoration work, the gate reopened to the public on 15 August 2010.' } },
    ko: { place_id: 'local:gwanghwamun', name: '광화문', name_local: 'Gwanghwamun Gate', lang: 'ko', verification: 'catalog', evidence_ids: ['visitkorea:gwanghwamun-culture'], visitor_tips: [], blocks: {
      what_it_is: '광화문은 경복궁의 남쪽 정문, 즉 궁궐의 "현관"이에요.',
      why_it_matters: '신분에 따라 지나가는 문이 달랐어요. 가운데 문은 왕이, 양옆 문은 왕세자와 신하들이 썼다고 해요.',
      what_to_look_for: '아치 모양 문 세 개를 찾아보고, 왕이 다니던 가운데 문을 보세요.',
      fun_fact: '복원 공사를 마치고 2010년 8월 15일에 다시 공개됐어요.' } },
  },
}
export function fixtureStory(placeId: string, lang: Language, fallbackName: string): LandmarkCard {
  return stories[placeId]?.[lang] ?? {
    place_id: placeId, name: fallbackName, name_local: null, lang, verification: 'model_unverified', evidence_ids: [], visitor_tips: [],
    blocks: { what_it_is: lang === 'ko' ? '아직 확인된 설명이 없어요. 계약 확정 후 공개 자료(OSM·위키백과)로 채워져요.' : 'No checked explanation yet. After the contract lands this is filled from public sources (OSM, Wikipedia).', why_it_matters: null, what_to_look_for: null, fun_fact: null },
  }
}

export const fixtureRoute = (lang: Language): Route => ({
  route_id: 'fixture:palace-in-a-nutshell',
  title: lang === 'ko' ? '궁궐 한 바퀴' : 'Palace in a nutshell', title_local: lang === 'ko' ? 'Palace in a nutshell' : '궁궐 한 바퀴',
  stops: [
    { place_id: 'local:gwanghwamun', name: lang === 'ko' ? '광화문' : 'Gwanghwamun', name_local: lang === 'ko' ? 'Gwanghwamun' : '광화문', lat: 37.5760, lng: 126.9768, dwell_minutes: 15, note: lang === 'ko' ? '궁궐의 정문에서 시작해요' : 'Start at the palace front door' },
    { place_id: 'fixture:heungnyemun', name: lang === 'ko' ? '흥례문' : 'Heungnyemun', name_local: lang === 'ko' ? 'Heungnyemun' : '흥례문', lat: 37.5773, lng: 126.9770, dwell_minutes: 10, note: lang === 'ko' ? '두 번째 문' : 'The second gate' },
    { place_id: 'fixture:geunjeongjeon', name: lang === 'ko' ? '근정전' : 'Geunjeongjeon', name_local: lang === 'ko' ? 'Geunjeongjeon' : '근정전', lat: 37.5786, lng: 126.9770, dwell_minutes: 20, note: lang === 'ko' ? '큰 의식을 치르던 건물' : 'Where big royal ceremonies were held' },
    { place_id: 'local:tosokchon', name: lang === 'ko' ? '토속촌 삼계탕' : 'Tosokchon Samgyetang', name_local: lang === 'ko' ? 'Tosokchon Samgyetang' : '토속촌 삼계탕', lat: 37.57760304027, lng: 126.971632166657, dwell_minutes: 45, note: lang === 'ko' ? '점심: 삼계탕' : 'Lunch: chicken & ginseng soup' },
  ],
  straight_line_total_m: 1250,
  disclaimers: [lang === 'ko' ? '거리는 직선거리 합계예요. 실제 도보 경로가 아니에요.' : 'Distance is the sum of straight lines, not a walking route.'],
})
