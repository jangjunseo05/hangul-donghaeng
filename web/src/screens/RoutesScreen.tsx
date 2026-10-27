import { useMemo } from 'react'
import { Clock, Info, Play, Route as RouteIcon } from 'lucide-react'
import MapView from '../MapView'
import type { Guide } from '../useGuide'
import type { Place } from '../types'
import { fixtureRoute } from '../fixtures/tabs'
import { BottomSheet, FixtureNote } from '../components/shell'

/** One template route (fixture until the M2 contract); straight lines only. */
export default function RoutesScreen({ g }: { g: Guide }) {
  const { t, language, selectLocation } = g
  const route = useMemo(() => fixtureRoute(language), [language])
  const places = useMemo<Place[]>(() => route.stops.map(stop => ({ place_id: stop.place_id, name: stop.name, lat: stop.lat, lng: stop.lng, distance_m: 0, source_id: 'fixture-source', catalog_version: 'fixture', kind: stop.place_id === 'local:tosokchon' ? 'restaurant' : 'heritage' })), [route])
  const line = useMemo<[number, number][]>(() => route.stops.map(stop => [stop.lat, stop.lng]), [route])
  const minutes = route.stops.reduce((sum, stop) => sum + (stop.dwell_minutes ?? 0), 0)
  return <section className="tab-screen" aria-label={t('Routes', '루트')}>
    <div className="screen-map"><MapView location={null} places={places} language={language} onLocation={selectLocation} onChoosePlace={() => {}} route={line} showHint={false}/></div>
    <BottomSheet t={t} className="screen-sheet" title={<div className="sheet-heading between"><div><h2><RouteIcon size={17}/>{route.title}</h2><small>{route.title_local} · {Math.round(minutes / 6) / 10} h · {(route.straight_line_total_m / 1000).toFixed(1)} km</small></div><button type="button" className="button button-primary small" disabled title={t('Available after the route contract (M2)', '루트 계약 후 사용 가능(M2)')}><Play size={14}/>{t('Start', '시작')}</button></div>}>
      <ol className="route-timeline">{route.stops.map((stop, index) => <li key={stop.place_id}>
        <span className={'list-number' + (index === route.stops.length - 1 ? '' : ' green')}>{index + 1}</span>
        <div><strong>{stop.name} <span className="ko-name">{stop.name_local}</span></strong>{stop.note && <small>{stop.note}</small>}</div>
        {stop.dwell_minutes !== null && <span className="dwell"><Clock size={12}/>{stop.dwell_minutes} {t('min', '분')}</span>}
      </li>)}</ol>
      {route.disclaimers.map(text => <p key={text} className="scope-note"><Info size={12}/>{text}</p>)}
      <FixtureNote t={t}/>
    </BottomSheet>
  </section>
}
