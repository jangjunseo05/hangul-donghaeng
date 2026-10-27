import { useState } from 'react'
import { ArrowLeft, ArrowUpRight, ChevronRight, Info, Landmark, MapPin, MessageCircle, Utensils } from 'lucide-react'
import MapView from '../MapView'
import type { Guide } from '../useGuide'
import type { Place } from '../types'
import type { DraftPlace, Tab } from '../draftTypes'
import { fixtureNearby, fixtureStory } from '../fixtures/tabs'
import { BottomSheet, FixtureNote } from '../components/shell'
import { PhraseCard, StoryCard } from '../components/cards'
import LocationControls from '../components/LocationControls'

const toMapPlace = (place: DraftPlace): Place => ({ place_id: place.place_id, name: place.name, lat: place.lat, lng: place.lng, distance_m: place.distance_m, source_id: place.source_id, catalog_version: place.catalog_version, kind: place.kind === 'restaurant' ? 'restaurant' : 'heritage' })
const fromLive = (place: Place): DraftPlace => ({ place_id: place.place_id, name: place.name, name_en: null, kind: place.kind ?? 'restaurant', lat: place.lat, lng: place.lng, distance_m: place.distance_m, category: null, source_id: place.source_id, source_url: null, catalog_version: place.catalog_version })
const osmLink = (place: DraftPlace) => `https://www.openstreetmap.org/?mlat=${place.lat}&mlon=${place.lng}#map=18/${place.lat}/${place.lng}`

/** Live places from the current answer when present; otherwise the draft fixture. */
function usePlaces(g: Guide, kind: 'food' | 'landmark') {
  const live = (g.currentResult?.places ?? []).filter(place => kind === 'food' ? (place.kind ?? 'restaurant') === 'restaurant' : place.kind === 'heritage')
  if (live.length) return { places: live.map(fromLive), live: true, origin: g.currentResult?.search_origin ?? g.location }
  const fixture = fixtureNearby(kind)
  return { places: fixture.places, live: false, origin: g.location ?? fixture.search_origin }
}

function PlaceList({ places, onSelect, t, icon }: { places: DraftPlace[]; onSelect(place: DraftPlace): void; t: Guide['t']; icon: 'food' | 'landmark' }) {
  return <ol className="sheet-list">{places.map((place, index) => <li key={place.place_id}><button type="button" onClick={() => onSelect(place)}>
    <span className={'list-number' + (icon === 'landmark' ? ' green' : '')}>{index + 1}</span>
    <span className="list-text"><strong>{place.name_en && place.name_en !== place.name ? place.name_en : place.name}</strong><small>{place.name_en && place.name_en !== place.name ? place.name + ' · ' : ''}{Math.round(place.distance_m)} m · {t('straight-line', '직선거리')}</small></span>
    <ChevronRight size={17}/></button></li>)}</ol>
}

export function LandmarksScreen({ g, onTab }: { g: Guide; onTab(tab: Tab): void }) {
  const { t, language, speech, catalog, selectAnchor, selectLocation, choosePlace } = g
  const { places, live, origin } = usePlaces(g, 'landmark')
  const [selected, setSelected] = useState<DraftPlace | null>(null)
  const anchor = selected ? catalog?.places.find(place => place.place_id === selected.place_id) : undefined
  return <section className="tab-screen" aria-label={t('Landmarks', '랜드마크')}>
    <div className="screen-map"><MapView location={origin} places={places.map(toMapPlace)} language={language} onLocation={selectLocation} onChoosePlace={place => { const match = places.find(item => item.place_id === place.place_id); if (match) setSelected(match); else choosePlace(place) }}/></div>
    <BottomSheet t={t} className="screen-sheet" title={selected ? <button type="button" className="sheet-back" onClick={() => setSelected(null)}><ArrowLeft size={15}/>{t('All landmarks', '랜드마크 목록')}</button> : <div className="sheet-heading"><Landmark size={17}/><h2>{t('Landmarks around you', '주변 랜드마크')}</h2></div>}>
      {!selected && <><LocationControls g={g}/><PlaceList places={places} onSelect={setSelected} t={t} icon="landmark"/>{!live && <FixtureNote t={t}/>}</>}
      {selected && <>
        <StoryCard story={fixtureStory(selected.place_id, language, selected.name_en ?? selected.name)} t={t} speaking={speech.speaking} onListen={text => speech.read(text, language)} onStop={speech.stopReading}/>
        <div className="sheet-actions">
          {anchor && <button type="button" className="button button-primary" onClick={() => { selectAnchor(anchor, true); onTab('look') }}><MessageCircle size={16}/>{t('Ask the guide here', '여기서 가이드에게 묻기')}</button>}
          <button type="button" className="button button-light" onClick={() => onTab('eat')}><Utensils size={16}/>{t('Eat nearby', '근처 맛집')}</button>
        </div>
        <FixtureNote t={t}/>
      </>}
    </BottomSheet>
  </section>
}

export function EatScreen({ g }: { g: Guide }) {
  const { t, language, speech, selectLocation, choosePlace, currentResult } = g
  const { places, live, origin } = usePlaces(g, 'food')
  const [selected, setSelected] = useState<DraftPlace | null>(null)
  const phrase = live && currentResult?.order_ko ? currentResult.order_ko : '메뉴판 좀 보여 주세요.'
  return <section className="tab-screen" aria-label={t('Eat', '맛집')}>
    <div className="screen-map"><MapView location={origin} places={places.map(toMapPlace)} language={language} onLocation={selectLocation} onChoosePlace={place => { const match = places.find(item => item.place_id === place.place_id); if (match) setSelected(match); else choosePlace(place) }}/></div>
    <BottomSheet t={t} className="screen-sheet" title={selected ? <button type="button" className="sheet-back" onClick={() => setSelected(null)}><ArrowLeft size={15}/>{t('All places', '맛집 목록')}</button> : <div className="sheet-heading"><Utensils size={17}/><h2>{t(`${places.length} places to eat nearby`, `주변 맛집 ${places.length}곳`)}</h2></div>}>
      {!selected && <><LocationControls g={g}/><PlaceList places={places} onSelect={setSelected} t={t} icon="food"/>
        <p className="scope-note"><Info size={12}/>{t('From OpenStreetMap. Hours, ratings and allergy info are not checked.', 'OpenStreetMap 자료예요. 영업시간·평점·알레르기 정보는 확인하지 않아요.')}</p>{!live && <FixtureNote t={t}/>}</>}
      {selected && <div className="place-detail">
        <span className="overline">{t('Restaurant', '음식점')} · {Math.round(selected.distance_m)} m</span>
        <h2>{selected.name_en && selected.name_en !== selected.name ? selected.name_en : selected.name}</h2>
        {selected.name_en && selected.name_en !== selected.name && <p className="story-local">{selected.name}</p>}
        <PhraseCard ko={phrase} gloss={live ? null : 'Could I see the menu, please?'} t={t} language={language} onListen={(text, lang) => speech.read(text, lang)}/>
        <div className="note-box"><Info size={14}/><span>{t('Opening hours, menu and allergens are not verified. Please check at the shop.', '영업시간·메뉴·알레르기 정보는 확인되지 않았어요. 가게에서 확인해 주세요.')}</span></div>
        <div className="sheet-actions"><a className="button button-primary" href={osmLink(selected)} target="_blank" rel="noopener noreferrer"><MapPin size={16}/>{t('Open in OpenStreetMap', 'OpenStreetMap에서 보기')}<ArrowUpRight size={14}/></a></div>
        {!live && <FixtureNote t={t}/>}
      </div>}
    </BottomSheet>
  </section>
}
