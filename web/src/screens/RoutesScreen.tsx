import { useMemo, useState } from 'react'
import { AlertTriangle, ArrowLeft, Clock, Footprints, Info, Route as RouteIcon } from 'lucide-react'
import MapView from '../MapView'
import type { Guide } from '../useGuide'
import type { Place } from '../types'
import type { Route, RouteStop, RoutesResponse } from '../contract'
import { loadCard, loadRoutes } from '../tabsApi'
import { useLoaded } from './useLoaded'
import { BottomSheet } from '../components/shell'
import { SourceLine, StoryCard, VerificationBadge } from '../components/cards'
import { FixtureTag } from './places'

const RESTRICTION_EVIDENCE = 'seoul:bukchon-visit-restriction'
const totalMinutes = (route: Route) => Math.round((route.total_dwell_min_estimate + route.legs.reduce((sum, leg) => sum + leg.est_walk_min, 0)) / 5) * 5

/**
 * Visiting restriction for a route (decision 8). Order: the route's own dated `visit_note` (contract M2),
 * then the Bukchon card's `visit_note`, then an undated fallback that says to check on the day.
 */
function RestrictionNotice({ g, route }: { g: Guide; route: Route }) {
  const { t, language } = g
  const stop = route.stops.find(item => item.place_id === 'local:bukchon')
  const restricted = Boolean(route.visit_note) || route.evidence_ids.includes(RESTRICTION_EVIDENCE) || Boolean(stop)
  const card = useLoaded(!route.visit_note && restricted && stop?.has_card && g.session ? `${stop.place_id}|${language}|${g.session}` : null, signal => loadCard(stop!.place_id, language, signal))
  if (!restricted) return null
  const cardData = card.status === 'ready' ? card.data : null
  const note = route.visit_note ?? cardData?.visit_note ?? null
  return <div className="restriction-note" role="note"><AlertTriangle size={15}/><div>
    <strong>{stop ? t('Visiting hours are restricted in part of Bukchon', '북촌 일부 구역은 방문 시간이 제한돼요') : t('Check visiting rules before you go', '방문 전 규정을 확인하세요')}</strong>
    <p>{note?.text ?? t('Bukchon is a residential area. Part of it limits tourist visits at certain hours. Check the current rules on the day you visit.', '북촌은 주민이 사는 동네예요. 일부 구역은 정해진 시간에 관광객 방문을 제한해요. 방문일에 현재 규정을 확인하세요.')}</p>
    {note?.verification === 'model_unverified' && <VerificationBadge value="model_unverified" t={t}/>}
    <SourceLine ids={note?.evidence_ids ?? [RESTRICTION_EVIDENCE]} sources={cardData?.sources} t={t}/>
  </div></div>
}

function RouteDetail({ g, route, onStop }: { g: Guide; route: Route; onStop(stop: RouteStop): void }) {
  const { t } = g
  return <>
    <p className="route-summary">{route.summary}</p>
    <ol className="route-timeline">{route.stops.map((stop, index) => {
      const leg = route.legs[index]
      return <li key={stop.place_id}>
        <span className={'list-number' + (stop.kind === 'restaurant' ? '' : ' green')}>{stop.order}</span>
        <div>
          <button type="button" className="stop-name" disabled={!stop.has_card} onClick={() => onStop(stop)}><strong>{stop.name}</strong>{stop.has_card && <small className="story-link">{t('Story', '이야기')}</small>}</button>
          {stop.note && <small>{stop.note}</small>}
          {leg && <small className="leg"><Footprints size={12}/>{t(`${leg.straight_line_m} m straight line · about ${leg.est_walk_min} min walk (estimate)`, `직선 ${leg.straight_line_m} m · 도보 약 ${leg.est_walk_min}분 (추정)`)}{leg.note && <em> — {leg.note}</em>}</small>}
        </div>
        <span className="dwell"><Clock size={12}/>~{stop.dwell_min_estimate} {t('min', '분')}</span>
      </li>
    })}</ol>
    <RestrictionNotice g={g} route={route}/>
    <p className="scope-note route-note"><Info size={12}/>{route.ui_note}</p>
  </>
}

/** Template routes from GET /api/routes (straight lines only; route_verified is always false). */
export default function RoutesScreen({ g }: { g: Guide }) {
  const { t, language, speech, location, selectLocation } = g
  const state = useLoaded<RoutesResponse>(g.session ? `${language}|${location?.lat ?? ''}|${location?.lng ?? ''}|${g.session}` : null, signal => loadRoutes(language, location, signal))
  const [chosen, setChosen] = useState<string | null>(null)
  const [storyStop, setStoryStop] = useState<RouteStop | null>(null)
  const routes = state.status === 'ready' ? state.data.routes : []
  const route = routes.find(item => item.route_id === chosen) ?? routes[0]
  const places = useMemo<Place[]>(() => (route?.stops ?? []).map(stop => ({ place_id: stop.place_id, name: stop.name, lat: stop.lat, lng: stop.lng, distance_m: 0, source_id: 'route', catalog_version: 'route', kind: stop.kind === 'restaurant' ? 'restaurant' : 'heritage' })), [route])
  const line = useMemo<[number, number][]>(() => (route?.stops ?? []).map(stop => [stop.lat, stop.lng]), [route])
  const card = useLoaded(storyStop && g.session ? `${storyStop.place_id}|${language}|${g.session}` : null, signal => loadCard(storyStop!.place_id, language, signal))
  return <section className="tab-screen" aria-label={t('Routes', '루트')}>
    <div className="screen-map"><MapView location={null} places={places} language={language} onLocation={selectLocation} onChoosePlace={place => { const stop = route?.stops.find(item => item.place_id === place.place_id); if (stop?.has_card) setStoryStop(stop) }} route={line} showHint={false}/></div>
    <BottomSheet t={t} className="screen-sheet" title={storyStop
      ? <button type="button" className="sheet-back" onClick={() => setStoryStop(null)}><ArrowLeft size={15}/>{t('Back to route', '루트로 돌아가기')}</button>
      : <div className="sheet-heading between"><div><h2><RouteIcon size={17}/>{route?.title ?? t('Walking routes', '산책 루트')}</h2>{route && <small>{t(`about ${totalMinutes(route)} min · ${(route.total_straight_line_m / 1000).toFixed(1)} km straight line`, `약 ${totalMinutes(route)}분 · 직선 ${(route.total_straight_line_m / 1000).toFixed(1)} km`)}</small>}</div></div>}>
      {storyStop && (card.status === 'loading' ? <div className="story-skeleton" aria-busy="true"><i/><i/><i/><i/></div>
        : card.status === 'ready' && card.data ? <StoryCard story={card.data} t={t} speaking={speech.speaking} onListen={text => speech.read(text, language)} onStop={speech.stopReading} fixture={card.fixture}/>
        : <p className="scope-note"><Info size={12}/>{t('No story card for this stop yet.', '이 정류장의 이야기 카드는 아직 없어요.')}</p>)}
      {!storyStop && <>
        {state.status === 'loading' && <div className="list-skeleton" aria-busy="true"><i/><i/><i/></div>}
        {state.status === 'error' && <div className="note-box" role="alert"><Info size={14}/><span>{t('Routes could not be loaded.', '루트를 불러오지 못했어요.')}</span></div>}
        {state.status === 'ready' && routes.length === 0 && <p className="scope-note"><Info size={12}/>{t('No template route starts near here. Routes cover the Gyeongbokgung area for now.', '이 근처에서 시작하는 루트가 없어요. 지금은 경복궁 일대만 있어요.')}</p>}
        {routes.length > 1 && <div className="seg" role="tablist" aria-label={t('Choose a route', '루트 선택')}>{routes.map(item => <button type="button" role="tab" key={item.route_id} aria-selected={item.route_id === route?.route_id} className={item.route_id === route?.route_id ? 'on' : ''} onClick={() => setChosen(item.route_id)}>{item.title}</button>)}</div>}
        {route && <RouteDetail g={g} route={route} onStop={setStoryStop}/>}
        {state.status === 'ready' && state.data.unknowns.map(text => <p key={text} className="scope-note"><Info size={12}/>{text}</p>)}
        {state.status === 'ready' && state.fixture && <FixtureTag t={t}/>}
      </>}
    </BottomSheet>
  </section>
}
