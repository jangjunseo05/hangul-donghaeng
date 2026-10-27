import { Info, Landmark, LoaderCircle, MapPin, Navigation } from 'lucide-react'
import MapView, { SEOCHON } from '../MapView'
import type { Location, Place, Radius } from '../types'
import type { Guide } from '../useGuide'
const EMPTY_PLACES: Place[] = []
export const isSeochonDemo = (location: Location | null) => Boolean(location && location.origin === 'selected' && location.lat === SEOCHON.lat && location.lng === SEOCHON.lng)

/** Starting point: device GPS, the labelled Seochon demo point, a confirmed map point, and the search radius. */
export default function LocationControls({ g, mapPicker = false }: { g: Guide; mapPicker?: boolean }) {
  const { t, mode, useMyLocation, locating, setMapPickerOpen, radius, changeRadius, location, anchor, mapPickerOpen, language, selectLocation, choosePlace, locationNotice, catalogFailed } = g
  if (mode !== 'real_place') return null
  const status = location
    ? anchor ? t('Selected starting point · ', '선택한 출발점 · ') + anchor.name
      : isSeochonDemo(location) ? t('Demo starting point · Seochon (not your GPS)', '데모 출발점 · 서촌 (내 GPS 아님)')
      : location.origin === 'gps' ? t('Using your location', '내 위치 사용 중') : t('Using your selected map point', '직접 고른 지도 지점 사용 중')
    : t('No starting point yet. Use your location or the Seochon demo point.', '아직 출발점이 없어요. 내 위치나 서촌 데모 지점을 쓰세요.')
  return <div className="location-toolbar">
    <div className="location-toolbar-actions">
      <button className="button button-light" onClick={useMyLocation} disabled={locating}>{locating ? <LoaderCircle size={15} className="spin"/> : <Navigation size={15}/>} {t('Use my location', '내 위치 사용')}</button>
      <button className="button button-light" onClick={() => selectLocation({ ...SEOCHON })}><Landmark size={15}/>{t('Seochon demo', '서촌 데모')}</button>
      {mapPicker && <button className="button button-light" aria-expanded={mapPickerOpen} onClick={() => setMapPickerOpen(value => !value)}><MapPin size={15}/>{t('Choose on map', '지도에서 선택')}</button>}
      <label className="compact-radius">{t('Within', '반경')}<select aria-label={t('Search radius', '검색 반경')} value={radius} onChange={event => changeRadius(Number(event.target.value) as Radius)}>{([500, 1000, 2000, 3000] as Radius[]).map(value => <option key={value} value={value}>{value / 1000} km</option>)}</select></label>
    </div>
    <small className="location-toolbar-status map-caption" role="status">{status}</small>
    {mapPicker && mapPickerOpen && <MapView location={location} places={EMPTY_PLACES} language={language} onLocation={selectLocation} onChoosePlace={choosePlace}/>}
    {locationNotice && <p className="inline-notice" role="status"><Info size={14}/>{locationNotice}</p>}
    {catalogFailed && <p className="inline-notice" role="status">{t('The place collection is unavailable. You can still choose a location on the map.', '수록 장소 정보를 불러오지 못했어요. 지도에서 위치를 직접 선택할 수 있어요.')}</p>}
  </div>
}
