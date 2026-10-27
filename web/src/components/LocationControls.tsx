import { Info, LoaderCircle, MapPin, Navigation } from 'lucide-react'
import MapView from '../MapView'
import type { Place, Radius } from '../types'
import type { Guide } from '../useGuide'
const EMPTY_PLACES: Place[] = []

/** GPS / map point / radius (moved from the former composer panel). */
export default function LocationControls({ g }: { g: Guide }) {
  const { t, mode, useMyLocation, locating, currentResult, answer, setMapPickerOpen, radius, changeRadius, location, anchor, mapPickerOpen, language, selectLocation, choosePlace, locationNotice, catalogFailed } = g
  return <>
          {mode === 'real_place' && <div className="location-toolbar">
            <div className="location-toolbar-actions"><button className="button button-light" onClick={useMyLocation} disabled={locating}>{locating ? <LoaderCircle size={15} className="spin"/> : <Navigation size={15}/>} {t('Use my location', '내 위치 사용')}</button><button className="button button-light" onClick={() => { if (currentResult?.places.length) answer.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }); else setMapPickerOpen(value => !value) }}><MapPin size={15}/>{t('Choose on map', '지도에서 선택')}</button><label className="compact-radius">{t('Within', '반경')}<select aria-label={t('Search radius', '검색 반경')} value={radius} onChange={event => changeRadius(Number(event.target.value) as Radius)}>{([500, 1000, 2000, 3000] as Radius[]).map(value => <option key={value} value={value}>{value / 1000} km</option>)}</select></label></div>
            <small className="location-toolbar-status">{location ? anchor ? t('Selected starting point · ', '선택한 출발점 · ') + anchor.name : location.origin === 'gps' ? t('Using your permitted location', '허용한 내 위치 사용 중') : t('Using your selected map point', '직접 선택한 지도 지점 사용 중') : t('No location selected. Choose one when asking about nearby places.', '위치 미선택 · 주변 장소가 필요할 때 직접 선택해 주세요.')}</small>
            {mapPickerOpen && !currentResult?.places.length && <MapView location={location} places={EMPTY_PLACES} language={language} onLocation={selectLocation} onChoosePlace={choosePlace}/>}
            {locationNotice && <p className="inline-notice" role="status"><Info size={14}/>{locationNotice}</p>}
            {catalogFailed && <p className="inline-notice" role="status">{t('The place collection is unavailable. You can still choose a location on the map.', '수록 장소 정보를 불러오지 못했어요. 지도에서 위치를 직접 선택할 수 있어요.')}</p>}
          </div>}
  </>
}
