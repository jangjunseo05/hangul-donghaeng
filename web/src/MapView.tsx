import { useEffect, useRef, useState } from 'react'
import L from 'leaflet'
import { MapPin, RotateCcw } from 'lucide-react'
import type { Language, Location, Place } from './types'

export const SEOCHON = { lat: 37.5790, lng: 126.9730, origin: 'selected' as const }
type Props = { location: Location | null; places: Place[]; language: Language; onLocation: (location: Location) => void; onChoosePlace: (place: Place) => void }
export default function MapView({ location, places, language, onLocation, onChoosePlace }: Props) {
  const container = useRef<HTMLDivElement>(null)
  const map = useRef<L.Map | null>(null)
  const layer = useRef<L.LayerGroup | null>(null)
  const tiles = useRef<L.TileLayer | null>(null)
  const callbacks = useRef({ onLocation, onChoosePlace })
  callbacks.current = { onLocation, onChoosePlace }
  const [tileError, setTileError] = useState(false)
  const [tilesReady, setTilesReady] = useState(false)
  useEffect(() => {
    if (!container.current) return
    const instance = L.map(container.current, { zoomControl: false, scrollWheelZoom: false }).setView([SEOCHON.lat, SEOCHON.lng], 15)
    map.current = instance
    tiles.current = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener noreferrer">OpenStreetMap</a>' }).addTo(instance)
    tiles.current.on('tileerror', () => setTileError(true))
    tiles.current.on('tileload', () => setTilesReady(true))
    const loadingTimeout = window.setTimeout(() => setTileError(ready => ready || !container.current?.querySelector('.leaflet-tile-loaded')), 12000)
    L.control.zoom({ position: 'bottomright' }).addTo(instance)
    layer.current = L.layerGroup().addTo(instance)
    instance.on('click', (event: L.LeafletMouseEvent) => callbacks.current.onLocation({ lat: event.latlng.lat, lng: event.latlng.lng, origin: 'selected' }))
    const observer = new ResizeObserver(() => instance.invalidateSize())
    observer.observe(container.current)
    return () => { clearTimeout(loadingTimeout); observer.disconnect(); instance.remove(); map.current = null }
  }, [])
  useEffect(() => {
    if (!map.current || !layer.current) return
    layer.current.clearLayers()
    if (location) {
      L.marker([location.lat, location.lng], { icon: L.divIcon({ className: 'start-marker', html: '<span></span>', iconSize: [20, 20], iconAnchor: [10, 10] }) }).addTo(layer.current)
    }
    places.forEach((place, index) => {
      if (!Number.isFinite(place.lat) || !Number.isFinite(place.lng) || Math.abs(place.lat) > 90 || Math.abs(place.lng) > 180) return
      const popup = document.createElement('div')
      const title = document.createElement('strong')
      title.textContent = place.name
      const distance = document.createElement('p')
      distance.textContent = Math.round(place.distance_m) + ' m · ' + (language === 'ko' ? '직선거리' : 'straight-line distance')
      const button = document.createElement('button')
      button.type = 'button'
      button.textContent = language === 'ko' ? '이곳 자세히 보기' : 'Explore this place'
      button.addEventListener('click', () => callbacks.current.onChoosePlace(place))
      popup.append(title, distance, button)
      L.marker([place.lat, place.lng], { icon: L.divIcon({ className: 'place-marker', html: '<span>' + (index + 1) + '</span>', iconSize: [34, 40], iconAnchor: [17, 40] }) }).bindPopup(popup).addTo(layer.current!)
    })
    if (places.length) {
      const points: L.LatLngTuple[] = places.map(p => [p.lat, p.lng])
      if (location) points.push([location.lat, location.lng])
      map.current.fitBounds(L.latLngBounds(points), { padding: [55, 55], maxZoom: 16 })
    } else if (location) map.current.setView([location.lat, location.lng], 15)
  }, [location, places, language])
  return <div className="map-wrap"><div className="map-canvas" ref={container} aria-label={language === 'ko' ? '출발점을 선택할 수 있는 지도' : 'Map: click to choose a starting point'} />
    {!location && <div className="map-hint"><MapPin size={14} />{language === 'ko' ? '지도를 눌러 출발점을 정해 주세요' : 'Tap the map to choose your starting point'}</div>}
    {!tilesReady && !tileError && <div className="map-loading" role="status">{language === 'ko' ? '지도를 불러오고 있어요…' : 'Loading the map…'}</div>}
    {tileError && <div className="map-error" role="status"><span>{language === 'ko' ? '지도 배경을 불러오지 못했어요.' : 'The map background could not load.'}</span><button type="button" onClick={() => { setTileError(false); tiles.current?.redraw() }}><RotateCcw size={13} />{language === 'ko' ? '다시 시도' : 'Retry'}</button></div>}
  </div>
}
