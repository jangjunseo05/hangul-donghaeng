import { useState } from 'react'
import { ArrowLeft, ArrowUpRight, BookOpen, ChevronRight, Flag, Info, Landmark, MessageCircle, RotateCcw, Utensils } from 'lucide-react'
import MapView, { SEOCHON } from '../MapView'
import type { Guide } from '../useGuide'
import type { Location, Place } from '../types'
import type { NearbyPlace, NearbyResponse, NearbyTab, Tab } from '../contract'
import { loadCard, loadNearby } from '../tabsApi'
import { useLoaded } from './useLoaded'
import { BottomSheet } from '../components/shell'
import { PhraseCard, StoryCard } from '../components/cards'
import LocationControls from '../components/LocationControls'

type T = Guide['t']
const toMapPlace = (place: NearbyPlace): Place => ({ place_id: place.place_id, name: place.name_en && place.name_en !== place.name ? `${place.name_en} · ${place.name}` : place.name, lat: place.lat, lng: place.lng, distance_m: place.distance_m, source_id: place.source_id, catalog_version: 'nearby', kind: place.kind === 'restaurant' ? 'restaurant' : 'heritage' })
const osmLink = (place: NearbyPlace) => place.osm_url ?? `https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lng}#map=18/${place.lat}/${place.lng}`
const displayName = (place: NearbyPlace) => place.name_en && place.name_en !== place.name ? place.name_en : place.name

export function nearbyErrorText(code: string, t: T) {
  // Live servers also report upstream codes such as overpass_timeout / overpass_http_502; a client TIMEOUT is a slow map search too.
  if (code === 'nearby_timeout' || code === 'TIMEOUT' || code === 'overpass_timeout') return t('The map search took too long. Please try again.', '지도 검색이 오래 걸렸어요. 다시 시도해 주세요.')
  if (code === 'nearby_busy') return t('The map search is busy. Please try again in a moment.', '지도 검색이 붐벼요. 잠시 후 다시 시도해 주세요.')
  if (code === 'nearby_unavailable' || code === 'nearby_invalid_response' || code.startsWith('overpass_')) return t('Nearby places are unavailable right now.', '지금은 주변 장소를 불러올 수 없어요.')
  if (code === 'OFFLINE') return t('Your guide is not reachable. Check the connection.', '가이드에 연결할 수 없어요. 연결을 확인해 주세요.')
  return t('Nearby places could not be loaded.', '주변 장소를 불러오지 못했어요.')
}
export function FixtureTag({ t }: { t: T }) {
  return <p className="fixture-note"><BookOpen size={12}/>{t('Contract example (fixture) · this server has no live route yet', '계약 예시(fixture) · 이 서버에 아직 실제 경로가 없어요')}</p>
}

/** Search origin for the tabs: chosen location, otherwise the visibly labelled Seochon demo point. */
function useOrigin(g: Guide): { origin: Location; demo: boolean } {
  return g.location ? { origin: g.location, demo: false } : { origin: { ...SEOCHON }, demo: true }
}

function useNearby(g: Guide, tab: NearbyTab) {
  const { origin, demo } = useOrigin(g)
  const [retry, setRetry] = useState(0)
  // Tab routes need the session cookie: wait for it instead of failing with 401 on a fast first tap.
  const key = g.session ? `${tab}|${origin.lat.toFixed(5)}|${origin.lng.toFixed(5)}|${g.radius}|${retry}|${g.session}` : null
  const state = useLoaded<NearbyResponse>(key, signal => loadNearby(tab, origin, g.radius, signal))
  return { state, origin, demo, retry: () => setRetry(value => value + 1) }
}

type Nearby = ReturnType<typeof useNearby>
function NearbyList({ g, tab, nearby, onSelect }: { g: Guide; tab: NearbyTab; nearby: Nearby; onSelect(place: NearbyPlace, response: NearbyResponse, fixture: boolean): void }) {
  const { t } = g
  const { state, demo, retry } = nearby
  return <>
    <LocationControls g={g}/>
    {demo && <p className="scope-note demo-note"><Flag size={12}/>{t('Showing around the Seochon demo point until you choose a starting point.', '출발점을 고르기 전에는 서촌 데모 지점 주변을 보여줘요.')}</p>}
    {!g.session && <div className="note-box" role="status"><Info size={14}/><span>{t('Connecting to your guide…', '가이드에 연결하고 있어요…')}</span><button type="button" className="button button-light small" onClick={() => void g.reconnect()}><RotateCcw size={13}/>{t('Reconnect', '다시 연결')}</button></div>}
    {g.session && state.status === 'loading' && <div className="list-skeleton" aria-busy="true" aria-label={t('Loading nearby places', '주변 장소를 불러오는 중')}><i/><i/><i/></div>}
    {state.status === 'error' && <div className="note-box" role="alert"><Info size={14}/><span>{nearbyErrorText(state.code, t)}</span><button type="button" className="button button-light small" onClick={retry}><RotateCcw size={13}/>{t('Retry', '다시 시도')}</button></div>}
    {state.status === 'ready' && <>
      {state.data.error_code && <div className="note-box" role="alert"><Info size={14}/><span>{state.data.places.length ? t('The live map search failed, so only our checked places are shown.', '실시간 지도 검색에 실패해 검수된 장소만 보여드려요.') : nearbyErrorText(state.data.error_code, t)}</span><button type="button" className="button button-light small" onClick={retry}><RotateCcw size={13}/>{t('Retry', '다시 시도')}</button></div>}
      {!state.data.error_code && state.data.places.length === 0 && <p className="scope-note"><Info size={12}/>{t('Nothing found in this radius. Try a wider radius.', '이 반경에서는 찾지 못했어요. 반경을 넓혀 보세요.')}</p>}
      <ol className="sheet-list">{state.data.places.map((place, index) => <li key={place.place_id}><button type="button" onClick={() => onSelect(place, state.data, state.fixture)}>
        <span className={'list-number' + (tab === 'landmark' ? ' green' : '')}>{index + 1}</span>
        <span className="list-text"><strong>{displayName(place)}</strong><small>{place.name_en && place.name_en !== place.name ? place.name + ' · ' : ''}{Math.round(place.distance_m)} m · {t('straight-line', '직선거리')}{place.has_card ? ' · ' + t('story', '이야기') : ''}</small></span>
        <ChevronRight size={17}/></button></li>)}</ol>
      <p className="attribution-line"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">{state.data.attribution}</a></p>
      {state.data.unknowns.map(text => <p key={text} className="scope-note"><Info size={12}/>{text}</p>)}
      {state.fixture && <FixtureTag t={t}/>}
    </>}
  </>
}

function NearbyMap({ g, nearby, onSelect }: { g: Guide; nearby: Nearby; onSelect(place: NearbyPlace, response: NearbyResponse, fixture: boolean): void }) {
  const { state, origin } = nearby
  const places = state.status === 'ready' ? state.data.places : []
  return <MapView location={origin} places={places.map(toMapPlace)} language={g.language} onLocation={g.selectLocation} onChoosePlace={place => { const match = places.find(item => item.place_id === place.place_id); if (match && state.status === 'ready') onSelect(match, state.data, state.fixture) }}/>
}

type Selection = { place: NearbyPlace; response: NearbyResponse; fixture: boolean }
/** "Start from here" and "Ask the guide here" for a catalog place; plain map point for others. */
function PlaceActions({ g, place, onTab }: { g: Guide; place: NearbyPlace; onTab(tab: Tab): void }) {
  const { t, catalog, selectAnchor, selectLocation } = g
  const anchor = catalog?.places.find(item => item.place_id === place.place_id)
  return <div className="sheet-actions">
    <button type="button" className="button button-light" onClick={() => { if (anchor) selectAnchor(anchor, false); else selectLocation({ lat: place.lat, lng: place.lng, origin: 'selected' }); onTab('look') }}><Flag size={16}/>{t('Start from here', '여기를 출발점으로')}</button>
    {anchor && <button type="button" className="button button-primary" onClick={() => { selectAnchor(anchor, true); onTab('look') }}><MessageCircle size={16}/>{t('Ask the guide here', '여기서 가이드에게 묻기')}</button>}
  </div>
}

function LandmarkDetail({ g, selection, onTab }: { g: Guide; selection: Selection; onTab(tab: Tab): void }) {
  const { t, language, speech } = g
  const { place, response } = selection
  const card = useLoaded(place.has_card && g.session ? `${place.place_id}|${language}|${g.session}` : null, signal => loadCard(place.place_id, language, signal))
  return <div className="place-detail">
    {!place.has_card && <><span className="overline">{place.category ?? t('Landmark', '랜드마크')} · {Math.round(place.distance_m)} m</span><h2>{displayName(place)}</h2>{place.name_en && place.name_en !== place.name && <p className="story-local">{place.name}</p>}<p className="scope-note"><Info size={12}/>{t('No story card for this place yet. Ask the guide with your camera for an explanation.', '이 장소의 이야기 카드는 아직 없어요. 카메라로 가이드에게 물어보세요.')}</p></>}
    {place.has_card && card.status === 'loading' && <div className="story-skeleton" aria-busy="true"><i/><i/><i/><i/></div>}
    {place.has_card && card.status === 'error' && <div className="note-box" role="alert"><Info size={14}/><span>{t('The story card could not be loaded.', '이야기 카드를 불러오지 못했어요.')}</span></div>}
    {place.has_card && card.status === 'ready' && (card.data
      ? <StoryCard story={card.data} t={t} speaking={speech.speaking} onListen={text => speech.read(text, language)} onStop={speech.stopReading} evidence={response.evidence} fixture={card.fixture}/>
      : <p className="scope-note"><Info size={12}/>{t('No story card for this place yet.', '이 장소의 이야기 카드는 아직 없어요.')}</p>)}
    <PlaceActions g={g} place={place} onTab={onTab}/>
    <div className="sheet-actions"><button type="button" className="button button-light" onClick={() => onTab('eat')}><Utensils size={16}/>{t('Eat nearby', '근처 맛집')}</button><a className="button button-light" href={osmLink(place)} target="_blank" rel="noopener noreferrer">{t('OpenStreetMap', 'OpenStreetMap')}<ArrowUpRight size={14}/></a></div>
  </div>
}

function FoodDetail({ g, selection, onTab }: { g: Guide; selection: Selection; onTab(tab: Tab): void }) {
  const { t, language, speech } = g
  const { place, response } = selection
  return <div className="place-detail">
    <span className="overline">{t('Restaurant', '음식점')}{place.category ? ' · ' + place.category : ''} · {Math.round(place.distance_m)} m</span>
    <h2>{displayName(place)}</h2>
    {place.name_en && place.name_en !== place.name && <p className="story-local">{place.name}</p>}
    <PhraseCard ko="메뉴판 좀 보여 주세요." gloss="Could I see the menu, please?" t={t} language={language} onListen={(text, lang) => speech.read(text, lang)}/>
    <div className="note-box"><Info size={14}/><span>{response.unknowns[0] ?? t('Opening hours, menu and allergens are not verified. Please check at the shop.', '영업시간·메뉴·알레르기 정보는 확인되지 않았어요. 가게에서 확인해 주세요.')}</span></div>
    <div className="sheet-actions"><a className="button button-primary" href={osmLink(place)} target="_blank" rel="noopener noreferrer">{t('Open in OpenStreetMap', 'OpenStreetMap에서 보기')}<ArrowUpRight size={14}/></a></div>
    <PlaceActions g={g} place={place} onTab={onTab}/>
    <p className="attribution-line"><a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">{response.attribution}</a></p>
  </div>
}

function PlacesScreen({ g, tab, onTab }: { g: Guide; tab: NearbyTab; onTab(tab: Tab): void }) {
  const { t } = g
  const [selected, setSelected] = useState<Selection | null>(null)
  const nearby = useNearby(g, tab)
  const select = (place: NearbyPlace, response: NearbyResponse, fixture: boolean) => setSelected({ place, response, fixture })
  const landmark = tab === 'landmark'
  return <section className="tab-screen" aria-label={landmark ? t('Landmarks', '랜드마크') : t('Eat', '맛집')}>
    <div className="screen-map"><NearbyMap g={g} nearby={nearby} onSelect={select}/></div>
    <BottomSheet t={t} className="screen-sheet" title={selected
      ? <button type="button" className="sheet-back" onClick={() => setSelected(null)}><ArrowLeft size={15}/>{landmark ? t('All landmarks', '랜드마크 목록') : t('All places', '맛집 목록')}</button>
      : <div className="sheet-heading">{landmark ? <Landmark size={17}/> : <Utensils size={17}/>}<h2>{landmark ? t('Landmarks around you', '주변 랜드마크') : t('Places to eat nearby', '주변 맛집')}</h2></div>}>
      {!selected && <NearbyList g={g} tab={tab} nearby={nearby} onSelect={select}/>}
      {selected && (landmark ? <LandmarkDetail g={g} selection={selected} onTab={onTab}/> : <FoodDetail g={g} selection={selected} onTab={onTab}/>)}
      {selected?.fixture && <FixtureTag t={t}/>}
    </BottomSheet>
  </section>
}
export const LandmarksScreen = ({ g, onTab }: { g: Guide; onTab(tab: Tab): void }) => <PlacesScreen g={g} tab="landmark" onTab={onTab}/>
export const EatScreen = ({ g, onTab }: { g: Guide; onTab(tab: Tab): void }) => <PlacesScreen g={g} tab="food" onTab={onTab}/>
